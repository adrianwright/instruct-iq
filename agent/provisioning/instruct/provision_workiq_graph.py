"""Provision only the explicitly approved Instruct IQ delegated Graph seeder."""
from __future__ import annotations

import json
import subprocess
import shutil
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

_settings = Settings()
TENANT = _settings.INSTRUCT_WORKIQ_TENANT_ID
SUBSCRIPTION = _settings.INSTRUCT_WORKIQ_SUBSCRIPTION_ID
OPERATOR = _settings.INSTRUCT_WORKIQ_OPERATOR_ID
GRAPH_APP = "00000003-0000-0000-c000-000000000000"
DEFAULT_ROLE = "00000000-0000-0000-0000-000000000000"
SCOPES = ("User.Read", "Chat.Read", "ChatMessage.Send", "Calendars.ReadWrite")
NAME = "Instruct IQ synthetic M365 seeder"
ROOT = Path(__file__).resolve().parents[3]
APP_MANIFEST = ROOT / ".local" / "instruct-iq-deployment" / "workiq-graph-app.json"


class ProvisionError(RuntimeError):
    pass


def save(value: dict[str, Any], path: Path = APP_MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class AzureDirectory:
    def __init__(self):
        self._token = None

    def cli(self, args: list[str]) -> Any:
        result = subprocess.run([shutil.which("az") or "az", *args, "--output", "json", "--only-show-errors"],
                                capture_output=True, text=True, shell=False)
        if result.returncode:
            # Never print raw CLI output, which can contain upstream bodies.
            raise ProvisionError("directory_operation_failed_no_retry")
        return json.loads(result.stdout) if result.stdout.strip() else None

    def request(self, method: str, path: str, body: Any = None) -> Any:
        # Directory provisioning only: never shared with the seed public client.
        # Native Python HTTP avoids az.cmd interpreting OData '&' as shell commands.
        if self._token is None:
            token = self.cli(["account", "get-access-token", "--resource",
                              "https://graph.microsoft.com", "--tenant", TENANT])
            if token.get("tenant") != TENANT:
                raise ProvisionError("directory_token_tenant_mismatch")
            self._token = token["accessToken"]
        response = httpx.request(
            method, "https://graph.microsoft.com/v1.0" + path, json=body,
            headers={"Authorization": f"Bearer {self._token}"}, timeout=30, follow_redirects=False,
        )
        if response.status_code >= 300:
            raise ProvisionError(f"directory_http_{response.status_code}_terminal_no_retry")
        return response.json() if response.content else None


def provision(directory: Any, manifest_path: Path = APP_MANIFEST) -> dict[str, Any]:
    _settings.validate_instruct_workiq_configuration(
        "INSTRUCT_WORKIQ_TENANT_ID", "INSTRUCT_WORKIQ_SUBSCRIPTION_ID",
        "INSTRUCT_WORKIQ_OPERATOR_ID",
    )
    account = directory.cli(["account", "show"])
    if account.get("tenantId") != TENANT or account.get("id") != SUBSCRIPTION:
        raise ProvisionError("approved_azure_context_required")
    resource = directory.cli(["ad", "sp", "show", "--id", GRAPH_APP])
    available = {s["value"]: s["id"] for s in resource.get("oauth2PermissionScopes", [])
                 if s.get("isEnabled")}
    if not set(SCOPES) <= available.keys():
        raise ProvisionError("approved_delegated_scope_not_found")
    required = [{"resourceAppId": GRAPH_APP, "resourceAccess": [
        {"id": available[s], "type": "Scope"} for s in SCOPES
    ]}]
    if manifest_path.exists():
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (metadata.get("tenantId") != TENANT or metadata.get("operatorId") != OPERATOR
                or metadata.get("scopes") != list(SCOPES) or metadata.get("pending")):
            raise ProvisionError("provision_manifest_requires_reconciliation")
    else:
        metadata = {"tenantId": TENANT, "operatorId": OPERATOR, "scopes": list(SCOPES),
                    "displayName": NAME, "pending": None}
    if not metadata.get("appObjectId"):
        from urllib.parse import quote

        existing = directory.request("GET", "/applications?$filter=" +
                                     quote(f"displayName eq '{NAME}'") + "&$select=id,appId&$top=2")
        if existing.get("value"):
            raise ProvisionError("existing_named_app_not_adopted")
        metadata["pending"] = "application_create"
        save(metadata, manifest_path)
        app = directory.request("POST", "/applications", {
            "displayName": NAME, "signInAudience": "AzureADMyOrg",
            "isFallbackPublicClient": True, "requiredResourceAccess": required,
        })
        metadata.update(appObjectId=app["id"], clientId=app["appId"], pending=None)
        save(metadata, manifest_path)
    app = directory.request("GET", f"/applications/{metadata['appObjectId']}")
    if (app.get("appId") != metadata["clientId"] or app.get("displayName") != NAME
            or app.get("signInAudience") != "AzureADMyOrg"
            or app.get("isFallbackPublicClient") is not True
            or app.get("passwordCredentials") or app.get("keyCredentials")):
        raise ProvisionError("dedicated_public_app_state_mismatch")
    actual_permissions = {
        (r["resourceAppId"], p["id"], p["type"])
        for r in app.get("requiredResourceAccess", []) for p in r.get("resourceAccess", [])
    }
    expected_permissions = {(GRAPH_APP, available[s], "Scope") for s in SCOPES}
    if actual_permissions != expected_permissions:
        raise ProvisionError("unexpected_app_permissions")
    if not metadata.get("servicePrincipalId"):
        metadata["pending"] = "service_principal_create"
        save(metadata, manifest_path)
        principal = directory.request("POST", "/servicePrincipals", {
            "appId": metadata["clientId"], "appRoleAssignmentRequired": True,
        })
        metadata.update(servicePrincipalId=principal["id"], pending=None)
        save(metadata, manifest_path)
    principal_id = metadata["servicePrincipalId"]
    principal = directory.request("GET", f"/servicePrincipals/{principal_id}")
    if (principal.get("appId") != metadata["clientId"]
            or principal.get("appRoleAssignmentRequired") is not True):
        raise ProvisionError("restricted_service_principal_required")
    # No app-only permissions, groups or other users may be assigned.
    application_roles = directory.request("GET", f"/servicePrincipals/{principal_id}/appRoleAssignments")
    if application_roles.get("value"):
        raise ProvisionError("unexpected_application_permissions")
    assignments = directory.request("GET", f"/servicePrincipals/{principal_id}/appRoleAssignedTo")
    rows = assignments.get("value", [])
    if assignments.get("@odata.nextLink") or any(
        r.get("principalId") != OPERATOR or r.get("appRoleId") != DEFAULT_ROLE
        or r.get("resourceId") != principal_id for r in rows
    ) or len(rows) > 1:
        raise ProvisionError("unexpected_operator_assignments")
    if not rows:
        metadata["pending"] = "operator_assignment"
        save(metadata, manifest_path)
        directory.request("POST", f"/servicePrincipals/{principal_id}/appRoleAssignedTo", {
            "principalId": OPERATOR, "resourceId": principal_id, "appRoleId": DEFAULT_ROLE,
        })
        metadata["pending"] = None
        save(metadata, manifest_path)
    grants = directory.request("GET", f"/servicePrincipals/{principal_id}/oauth2PermissionGrants")
    rows = grants.get("value", [])
    if grants.get("@odata.nextLink") or len(rows) > 1 or any(
        r.get("resourceId") != resource["id"] or r.get("consentType") != "Principal"
        or r.get("principalId") != OPERATOR or set(r.get("scope", "").split()) != set(SCOPES)
        for r in rows
    ):
        raise ProvisionError("unexpected_delegated_consent")
    if not rows:
        metadata["pending"] = "operator_delegated_consent"
        save(metadata, manifest_path)
        grant = directory.request("POST", "/oauth2PermissionGrants", {
            "clientId": principal_id, "consentType": "Principal", "principalId": OPERATOR,
            "resourceId": resource["id"], "scope": " ".join(SCOPES),
        })
        metadata.update(consentGrantId=grant["id"], pending=None)
        save(metadata, manifest_path)
    else:
        metadata["consentGrantId"] = rows[0]["id"]
    # Verify the restricted assignment and user-only consent after provisioning.
    assignment = directory.request("GET", f"/servicePrincipals/{principal_id}/appRoleAssignedTo")
    consent = directory.request("GET", f"/oauth2PermissionGrants/{metadata['consentGrantId']}")
    if (len(assignment.get("value", [])) != 1
            or assignment["value"][0].get("principalId") != OPERATOR
            or consent.get("consentType") != "Principal" or consent.get("principalId") != OPERATOR
            or set(consent.get("scope", "").split()) != set(SCOPES)):
        raise ProvisionError("operator_restriction_verification_failed")
    metadata["status"] = "provisioned_operator_only_delegated"
    save(metadata, manifest_path)
    return metadata


if __name__ == "__main__":
    try:
        print(json.dumps(provision(AzureDirectory()), indent=2))
    except ProvisionError as error:
        raise SystemExit(str(error))
