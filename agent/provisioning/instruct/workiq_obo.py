"""Provision only the approved Instruct IQ API's delegated Work IQ boundary."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from app.config import Settings

_settings = Settings()
TENANT = _settings.INSTRUCT_WORKIQ_TENANT_ID
SUBSCRIPTION = _settings.INSTRUCT_WORKIQ_SUBSCRIPTION_ID
OWNER = _settings.INSTRUCT_WORKIQ_OPERATOR_ID
API = _settings.INSTRUCT_WORKIQ_API_CLIENT_ID
IDENTITY = _settings.INSTRUCT_WORKIQ_IDENTITY_PRINCIPAL_ID
WORKIQ = "fdcc1f02-fc51-4226-8753-f668596af7f7"
VAULT = _settings.INSTRUCT_WORKIQ_VAULT_NAME
CERTIFICATE = "instruct-workiq-obo"
ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / ".local" / "instruct-iq-deployment" / "workiq-obo.json"


def az(*args: str):
    executable = shutil.which("az")
    if not executable:
        raise RuntimeError("Azure CLI is required")
    result = subprocess.run(
        [executable, *args, "--only-show-errors", "--output", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        # Commands never retrieve private material or access tokens.
        raise RuntimeError(result.stderr.strip() or "Azure CLI operation failed")
    return json.loads(result.stdout) if result.stdout.strip() else None


def graph(method: str, path: str, body: dict | None = None):
    args = ["rest", "--method", method, "--url", "https://graph.microsoft.com/v1.0/" + path]
    if body is None:
        return az(*args)
    with tempfile.TemporaryDirectory(prefix="instruct-public-config-") as directory:
        public_config = Path(directory) / "body.json"
        public_config.write_text(json.dumps(body), encoding="utf-8")
        return az(*args, "--headers", "Content-Type=application/json", "--body", "@" + str(public_config))


def checkpoint(result: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def provision() -> dict:
    _settings.validate_instruct_workiq_configuration(
        "INSTRUCT_WORKIQ_TENANT_ID", "INSTRUCT_WORKIQ_SUBSCRIPTION_ID",
        "INSTRUCT_WORKIQ_OPERATOR_ID", "INSTRUCT_WORKIQ_API_CLIENT_ID",
        "INSTRUCT_WORKIQ_IDENTITY_PRINCIPAL_ID", "INSTRUCT_WORKIQ_VAULT_NAME",
    )
    account = az("account", "show")
    if account["tenantId"] != TENANT or account["id"] != SUBSCRIPTION:
        raise RuntimeError("Approved Instruct IQ tenant/subscription required")
    if az("ad", "signed-in-user", "show")["id"] != OWNER:
        raise RuntimeError("Approved demo administrator required")
    app = az("ad", "app", "show", "--id", API)
    if app["displayName"] != "Instruct IQ isolated API":
        raise RuntimeError("Dedicated API registration ownership mismatch")
    service = az("ad", "sp", "show", "--id", API)
    downstream = az("ad", "sp", "show", "--id", WORKIQ)
    scope, = [s for s in downstream["oauth2PermissionScopes"]
              if s["value"] == "WorkIQAgent.Ask" and s["isEnabled"]]
    required = app.get("requiredResourceAccess", [])
    if required and required != [{"resourceAppId": WORKIQ,
                                  "resourceAccess": [{"id": scope["id"], "type": "Scope"}]}]:
        raise RuntimeError("Unexpected API downstream permissions require review")
    graph("PATCH", "applications/" + app["id"], {
        "requiredResourceAccess": [{"resourceAppId": WORKIQ,
                                   "resourceAccess": [{"id": scope["id"], "type": "Scope"}]}],
    })
    grants = graph("GET", f"servicePrincipals/{service['id']}/oauth2PermissionGrants")["value"]
    matching = [g for g in grants if g["resourceId"] == downstream["id"]]
    if any(g["scope"] != "WorkIQAgent.Ask" or g["consentType"] != "Principal"
           or g.get("principalId") != OWNER for g in matching):
        raise RuntimeError("Unexpected Work IQ grant requires review")
    if not matching:
        graph("POST", "oauth2PermissionGrants", {
            "clientId": service["id"], "resourceId": downstream["id"],
            "consentType": "Principal", "principalId": OWNER, "scope": "WorkIQAgent.Ask",
        })
    result = {
        "tenantId": TENANT, "clientId": API, "operatorId": OWNER,
        "endpoint": "https://workiq.svc.cloud.microsoft/a2a/",
        "scope": "api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask",
        "certificateSecretName": CERTIFICATE,
        "status": "operator_delegated_consent_configured_certificate_pending",
    }
    checkpoint(result)
    print(json.dumps({"status": "workiq_operator_delegated_consent_configured"}), flush=True)

    vaults = az("keyvault", "list", "--resource-group", "rg-instruct-iq")
    existing = [v for v in vaults if v["name"] == VAULT]
    if existing:
        vault = az("keyvault", "show", "--name", VAULT)
        if (vault.get("tags", {}).get("project") != "instruct-iq"
                or vault["properties"]["tenantId"] != TENANT
                or not vault["properties"].get("enableRbacAuthorization")):
            raise RuntimeError("Dedicated Key Vault ownership/configuration mismatch")
    else:
        vault = az(
            "keyvault", "create", "--name", VAULT, "--resource-group", "rg-instruct-iq",
            "--location", "centralus", "--enable-rbac-authorization", "true",
            "--enable-purge-protection", "true", "--retention-days", "7",
            "--tags", "project=instruct-iq",
        )
    officer = "a4417e6f-fecd-4de8-b567-7b0420556985"
    az("role", "assignment", "create", "--assignee-object-id", OWNER,
       "--assignee-principal-type", "User", "--role", officer, "--scope", vault["id"])
    result.update(vaultUrl=vault["properties"]["vaultUri"],
                  status="certificate_officer_assigned_certificate_pending")
    checkpoint(result)
    print(json.dumps({"status": "dedicated_key_vault_configured", "vault": VAULT}), flush=True)
    certificates = az("keyvault", "certificate", "list", "--vault-name", VAULT)
    if not any(c["id"].rsplit("/", 1)[-1] == CERTIFICATE for c in certificates):
        policy = {
            "issuerParameters": {"name": "Self"},
            "keyProperties": {"exportable": True, "keyType": "RSA", "keySize": 2048,
                              "reuseKey": False},
            "secretProperties": {"contentType": "application/x-pkcs12"},
            "x509CertificateProperties": {
                "subject": "CN=Instruct IQ Work IQ OBO", "validityInMonths": 6,
                "keyUsage": ["digitalSignature"], "ekus": ["1.3.6.1.5.5.7.3.2"],
            },
        }
        with tempfile.TemporaryDirectory(prefix="instruct-certificate-policy-") as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            az("keyvault", "certificate", "create", "--vault-name", VAULT,
               "--name", CERTIFICATE, "--policy", "@" + str(path))
    certificate = az("keyvault", "certificate", "show", "--vault-name", VAULT,
                     "--name", CERTIFICATE)
    public_der = base64.b64decode(certificate["cer"], validate=True)
    parsed = x509.load_der_x509_certificate(public_der)
    fingerprint = base64.b64encode(parsed.fingerprint(hashes.SHA1())).decode("ascii")
    keys = app.get("keyCredentials", [])
    if any(k.get("displayName") != CERTIFICATE for k in keys):
        raise RuntimeError("Unexpected API certificate requires review")
    if not any(k.get("customKeyIdentifier") == fingerprint for k in keys):
        if keys:
            raise RuntimeError("Existing OBO certificate differs; explicit rotation required")
        graph("PATCH", "applications/" + app["id"], {"keyCredentials": [{
            "type": "AsymmetricX509Cert", "usage": "Verify", "key": certificate["cer"],
            "displayName": CERTIFICATE,
            "startDateTime": parsed.not_valid_before_utc.isoformat(),
            "endDateTime": parsed.not_valid_after_utc.isoformat(),
        }]})
    secret_scope = vault["id"] + "/secrets/" + CERTIFICATE
    az("role", "assignment", "create", "--assignee-object-id", IDENTITY,
       "--assignee-principal-type", "ServicePrincipal",
       "--role", "4633458b-17de-408a-b874-0445c86b69e6", "--scope", secret_scope)
    result.update(certificateId=certificate["id"], managedIdentitySecretScope=secret_scope,
                  status="configured_not_live_verified")
    checkpoint(result)
    return result


if __name__ == "__main__":
    print(json.dumps(provision(), indent=2))
