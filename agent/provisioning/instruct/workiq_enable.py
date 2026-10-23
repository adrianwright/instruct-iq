"""Enable only the verified manual-source Work IQ adapter on the isolated API."""
from __future__ import annotations

import copy
import json

import httpx
from azure.identity import AzureCliCredential

from app.config import Settings
from workiq_obo import API, OWNER, ROOT, SUBSCRIPTION, TENANT

_settings = Settings()
RESOURCE = _settings.INSTRUCT_WORKIQ_API_RESOURCE_ID
EXPECTED_IMAGE = _settings.INSTRUCT_WORKIQ_EXPECTED_IMAGE


def runtime_manifest(manifest: dict) -> dict:
    if (
        manifest.get("status") != "native_seed_verified" or manifest.get("pending")
        or manifest.get("tenantId") != TENANT or manifest.get("ownerId") != OWNER
        or manifest.get("classId") != "class-science-7a"
        or manifest.get("origin") != "user_created_teams_self_chat"
        or len(manifest.get("sources", [])) != 3
        or any(s.get("contentVerified") is not True for s in manifest["sources"])
    ):
        raise RuntimeError("The three manual sources require complete native readback")
    configured = copy.deepcopy(manifest)
    for source in configured["sources"]:
        # The verifier binds this service-returned link to the exact supplied entity.
        if source.get("nativeWebUrl"):
            source["suppliedUrl"] = source["url"]
            source["url"] = source["nativeWebUrl"]
    return configured


def enable() -> None:
    _settings.validate_instruct_workiq_configuration(
        "INSTRUCT_WORKIQ_TENANT_ID", "INSTRUCT_WORKIQ_SUBSCRIPTION_ID",
        "INSTRUCT_WORKIQ_OPERATOR_ID", "INSTRUCT_WORKIQ_API_CLIENT_ID",
        "INSTRUCT_WORKIQ_API_RESOURCE_ID", "INSTRUCT_WORKIQ_EXPECTED_IMAGE",
    )
    prefix = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-instruct-iq"
        "/providers/Microsoft.App/containerApps/"
    )
    if not RESOURCE.startswith(prefix) or "/" in RESOURCE[len(prefix):] or RESOURCE == prefix:
        raise RuntimeError("Dedicated container app resource is outside the approved scope")
    directory = ROOT / ".local" / "instruct-iq-deployment"
    manifest = runtime_manifest(json.loads((directory / "workiq.json").read_text(encoding="utf-8")))
    obo = json.loads((directory / "workiq-obo.json").read_text(encoding="utf-8"))
    if (obo.get("status") != "configured_not_live_verified"
            or obo.get("clientId") != API or obo.get("tenantId") != TENANT):
        raise RuntimeError("Dedicated OBO certificate configuration is required")
    with AzureCliCredential(tenant_id=TENANT) as credential:
        token = credential.get_token("https://management.azure.com/.default")
        with httpx.Client(
            headers={"Authorization": f"Bearer {token.token}"},
            timeout=120, follow_redirects=False,
        ) as client:
            url = "https://management.azure.com" + RESOURCE + "?api-version=2024-03-01"
            response = client.get(url)
            response.raise_for_status()
            resource = response.json()
            template = resource["properties"]["template"]
            container, = template["containers"]
            if container["name"] != "api" or container["image"] != EXPECTED_IMAGE:
                raise RuntimeError("The validated Work IQ API image must be deployed first")
            environment = {entry["name"]: entry for entry in container["env"]}
            environment["INSTRUCT_WORKIQ_ENABLED"] = {
                "name": "INSTRUCT_WORKIQ_ENABLED", "value": "true",
            }
            environment["INSTRUCT_WORKIQ_MANIFEST_JSON"] = {
                "name": "INSTRUCT_WORKIQ_MANIFEST_JSON", "value": json.dumps(manifest),
            }
            for name, value in (
                ("INSTRUCT_WORKIQ_TENANT_ID", TENANT),
                ("INSTRUCT_WORKIQ_API_CLIENT_ID", API),
            ):
                environment[name] = {"name": name, "value": value}
            container["env"] = list(environment.values())
            response = client.patch(url, json={"properties": {"template": template}})
            response.raise_for_status()
    print(json.dumps({
        "status": "workiq_configuration_submitted_live_retrieval_unverified",
        "verifiedSources": len(manifest["sources"]), "nativeWrites": 0,
    }))


if __name__ == "__main__":
    enable()
