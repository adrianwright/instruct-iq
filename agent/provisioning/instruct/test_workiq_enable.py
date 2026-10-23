import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("instruct_workiq_enable", ROOT / "workiq_enable.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_enable_refuses_unconfigured_or_foreign_resource_before_live_access(monkeypatch):
    from app.config import SettingsConfigurationError

    monkeypatch.setattr(
        module, "_settings",
        module._settings.model_copy(update={"INSTRUCT_WORKIQ_API_RESOURCE_ID": ""}),
    )
    with pytest.raises(SettingsConfigurationError, match="INSTRUCT_WORKIQ_API_RESOURCE_ID"):
        module.enable()
    monkeypatch.setattr(
        module, "_settings",
        module._settings.model_copy(update={"INSTRUCT_WORKIQ_API_RESOURCE_ID": "configured"}),
    )
    monkeypatch.setattr(module, "RESOURCE", "/subscriptions/another/resourceGroups/other")
    with pytest.raises(RuntimeError, match="outside the approved scope"):
        module.enable()


def manifest():
    return {
        "status": "native_seed_verified", "pending": None,
        "tenantId": module.TENANT, "ownerId": module.OWNER,
        "classId": "class-science-7a", "origin": "user_created_teams_self_chat",
        "sources": [{
            "key": key, "url": "supplied-" + key, "nativeWebUrl": "native-" + key,
            "contentVerified": True,
        } for key in ("discussion", "recap", "resource")],
    }


def test_uses_verified_native_links_without_changing_supplied_manifest():
    original = manifest()
    configured = module.runtime_manifest(original)
    assert configured["sources"][0]["url"] == "native-discussion"
    assert configured["sources"][0]["suppliedUrl"] == "supplied-discussion"
    assert original["sources"][0]["url"] == "supplied-discussion"


@pytest.mark.parametrize("change", ["pending", "status", "owner", "count", "unverified"])
def test_unverified_or_foreign_inventory_cannot_be_enabled(change):
    value = manifest()
    if change == "pending":
        value["pending"] = {"key": "discussion"}
    elif change == "status":
        value["status"] = "user_supplied_links_pending_native_readback"
    elif change == "owner":
        value["ownerId"] = "another-user"
    elif change == "count":
        value["sources"].pop()
    else:
        value["sources"][0]["contentVerified"] = False
    with pytest.raises(RuntimeError, match="native readback"):
        module.runtime_manifest(value)
