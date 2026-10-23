import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

SPEC = importlib.util.spec_from_file_location("instruct_obo_provision", Path(__file__).with_name("workiq_obo.py"))
provisioner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provisioner)


def configuration(monkeypatch, tmp_path, *, wrong_context=False):
    import base64
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Instruct IQ test")])
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=180))
        .sign(key, hashes.SHA256())
    )
    cer = base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()
    vault = {
        "id": "/subscriptions/approved/resourceGroups/rg-instruct-iq/providers/Microsoft.KeyVault/vaults/instruct-test",
        "name": provisioner.VAULT, "tags": {"project": "instruct-iq"},
        "properties": {"tenantId": provisioner.TENANT, "enableRbacAuthorization": True,
                       "vaultUri": "https://instruct-test.vault.azure.net/"},
    }
    calls = []

    def az(*args):
        calls.append(args)
        if args[:2] == ("account", "show"):
            return {"tenantId": "wrong" if wrong_context else provisioner.TENANT,
                    "id": provisioner.SUBSCRIPTION}
        if args[:3] == ("ad", "signed-in-user", "show"):
            return {"id": provisioner.OWNER}
        if args[:3] == ("ad", "app", "show"):
            return {"id": "dedicated-api-object", "displayName": "Instruct IQ isolated API",
                    "requiredResourceAccess": [], "keyCredentials": []}
        if args[:3] == ("ad", "sp", "show"):
            if args[-1] == provisioner.API:
                return {"id": "dedicated-api-service"}
            return {"id": "workiq-service", "oauth2PermissionScopes": [{
                "value": "WorkIQAgent.Ask", "id": "resolved-scope", "isEnabled": True,
            }]}
        if args[:2] == ("keyvault", "list"):
            return [vault]
        if args[:2] == ("keyvault", "show"):
            return vault
        if args[:3] == ("keyvault", "certificate", "list"):
            return [{"id": "https://instruct-test.vault.azure.net/certificates/" + provisioner.CERTIFICATE}]
        if args[:3] == ("keyvault", "certificate", "show"):
            return {"cer": cer, "id": "certificate/version"}
        if args[:3] == ("role", "assignment", "create"):
            return {"id": "assignment"}
        pytest.fail(f"Unexpected Azure operation: {args}")

    def graph(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return {"value": []}
        return {}

    monkeypatch.setattr(provisioner, "az", az)
    monkeypatch.setattr(provisioner, "graph", graph)
    monkeypatch.setattr(provisioner, "OUTPUT", tmp_path / "obo.json")
    return calls


def test_only_dedicated_app_operator_consent_and_public_certificate(monkeypatch, tmp_path):
    assert 3 <= len(provisioner.VAULT) <= 24
    calls = configuration(monkeypatch, tmp_path)
    result = provisioner.provision()
    grants = [call[2] for call in calls if call[:2] == ("POST", "oauth2PermissionGrants")]
    assert grants == [{
        "clientId": "dedicated-api-service", "resourceId": "workiq-service",
        "consentType": "Principal", "principalId": provisioner.OWNER, "scope": "WorkIQAgent.Ask",
    }]
    assert result["clientId"] == provisioner.API
    assert result["status"] == "configured_not_live_verified"
    assert "PRIVATE KEY" not in provisioner.OUTPUT.read_text()
    assert not any(call[:3] == ("keyvault", "secret", "show") for call in calls)
    secret_grant = [call for call in calls if call[:3] == ("role", "assignment", "create")][-1]
    assert secret_grant[-1].endswith("/secrets/" + provisioner.CERTIFICATE)


def test_wrong_tenant_has_no_mutations(monkeypatch, tmp_path):
    calls = configuration(monkeypatch, tmp_path, wrong_context=True)
    with pytest.raises(RuntimeError, match="tenant/subscription"):
        provisioner.provision()
    assert calls == [("account", "show")]
