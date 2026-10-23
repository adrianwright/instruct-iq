import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app import instruct_workiq_a2a as work
from app.auth import AuthenticatedUser
from app.config import Settings
from app.instruct_workiq import API_CLIENT_ID, MARKER, TENANT_ID
from app.workiq import (
    WorkIQAnswer, WorkIQAttribution, WorkIQProtocolError, WorkIQTokenExchangeError,
)

OWNER = "demo-operator"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("INSTRUCT_WORKIQ_API_CLIENT_ID", ""),
    ("INSTRUCT_WORKIQ_API_CLIENT_ID", "legacy-client"),
    ("INSTRUCT_WORKIQ_TENANT_ID", ""),
    ("INSTRUCT_WORKIQ_TENANT_ID", "another-tenant"),
])
async def test_missing_or_unrelated_dedicated_boundary_never_connects(
    configuration, monkeypatch, field, value,
):
    settings, _, _ = configuration
    setattr(settings, field, value)
    monkeypatch.setattr(work, "WorkIQClient", lambda *_: pytest.fail("must not connect"))
    result = await retrieve(configuration)
    assert result["state"] == "unavailable"
    assert "configuration is incomplete" in result["reason"]


@pytest.fixture
def configuration():
    manifest = {
        "tenantId": TENANT_ID, "ownerId": OWNER, "classId": "class-science-7a",
        "selfChatId": "verified-chat", "marker": MARKER, "pending": None,
        "status": "native_seed_verified",
        "sources": [{
            "key": key, "id": key, "createdDateTime": "2026-10-15T20:00:00Z",
            "path": f"/me/events/{key}" if key == "agenda"
                    else f"/chats/verified-chat/messages/{key}",
            "url": f"https://outlook.office.com/calendar/item/{key}" if key == "agenda"
                   else f"https://teams.microsoft.com/l/message/verified-chat/{key}",
        } for key in ("discussion", "recap", "resource", "agenda")],
    }
    settings = Settings(
        _env_file=None, APP_ENVIRONMENT="test", AZURE_TENANT_ID=TENANT_ID,
        INSTRUCT_WORKIQ_ENABLED=True, INSTRUCT_WORKIQ_MANIFEST_JSON=json.dumps(manifest),
        WORK_IQ_CLIENT_ID=API_CLIENT_ID,
        WORK_IQ_SCOPE="api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask",
        WORK_IQ_KEY_VAULT_URL="https://instruct-test.vault.azure.net/",
        WORK_IQ_CLIENT_CERTIFICATE_SECRET_NAME="instruct-workiq-obo",
    )
    user = AuthenticatedUser("caller-assertion", TENANT_ID, "pairwise-subject",
                             frozenset({"access_as_user"}), {"oid": OWNER})
    return settings, user, manifest


def answer(manifest):
    return WorkIQAnswer(
        "A fictional team suggested checking graph explanations.", "task", None, 12,
        (WorkIQAttribution("Untrusted title", manifest["sources"][0]["url"]),),
    )


async def retrieve(configuration):
    settings, user, _ = configuration
    return await work.retrieve(
        settings=settings, user=user, class_id="class-science-7a",
        query="What did the team discuss?",
    )


@pytest.mark.asyncio
async def test_dedicated_caller_obo_and_cited_summary(configuration, monkeypatch):
    settings, user, manifest = configuration
    seen = []

    class Client:
        def __init__(self, configured):
            assert configured.WORK_IQ_CLIENT_ID == API_CLIENT_ID

        def ask(self, **kwargs):
            seen.append(kwargs)
            return answer(manifest)

    monkeypatch.setattr(work, "WorkIQClient", Client)
    result = await retrieve(configuration)
    assert result["state"] == "succeeded"
    assert seen[0]["user_assertion"] == user.access_token
    assert all(s["url"] in seen[0]["question"] for s in manifest["sources"])
    assert "Untrusted title" not in json.dumps(result)
    assert result["facts"][0]["kind"] == "work_iq_summary"
    assert "not a verbatim" in result["facts"][0]["notice"]
    assert result["facts"][0]["evidenceRefs"] == ["work-discussion"]
    assert result["evidenceRefs"][0]["locator"] == manifest["sources"][0]["url"]


def test_three_manually_created_messages_require_native_readback(configuration):
    settings, user, manifest = configuration
    manifest["origin"] = "user_created_teams_self_chat"
    manifest["sources"].pop()
    settings.INSTRUCT_WORKIQ_MANIFEST_JSON = json.dumps(manifest)
    with pytest.raises(ValueError, match="source identity"):
        work.verified_sources(settings, user, "class-science-7a")
    for source in manifest["sources"]:
        source["contentVerified"] = True
    settings.INSTRUCT_WORKIQ_MANIFEST_JSON = json.dumps(manifest)
    assert len(work.verified_sources(settings, user, "class-science-7a")) == 3


@pytest.mark.parametrize("query", [
    "",
    "?context=%7B%22contextType%22%3A%22chat%22%7D",
    "?tenantId=" + TENANT_ID + "&context=%7b%22contextType%22%3a%22chat%22%2c%22oid%22%3a%228%3aorgid%3ademo-operator%22%7d",
])
def test_equivalent_native_teams_links_bind_to_same_entity(query):
    assert work.citation_key(
        "https://teams.microsoft.com/l/message/48%3Anotes/1000000000001" + query,
        owner=OWNER, tenant=TENANT_ID,
    ) == ("teams", "48:notes", "1000000000001")


@pytest.mark.parametrize("query", [
    "?tenantId=another-tenant",
    "?context=%7B%22contextType%22%3A%22chat%22%2C%22oid%22%3A%228%3Aorgid%3Aother%22%7D",
    "?context=not-json",
    "?context=%7B%22contextType%22%3A%22channel%22%7D",
    "?tenantId=" + TENANT_ID + "&tenantId=another-tenant",
    "?messageId=different",
])
def test_foreign_or_ambiguous_teams_context_is_not_canonicalized(query):
    assert work.citation_key(
        "https://teams.microsoft.com/l/message/48:notes/1000000000001" + query,
        owner=OWNER, tenant=TENANT_ID,
    ) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "disabled", "other_app", "other_endpoint", "other_scope", "other_owner", "other_tenant",
    "no_assertion", "no_scope", "pending", "missing_source", "unverified", "bad_url",
    "bad_path", "duplicate_url", "wrong_class", "invalid_manifest",
])
async def test_configuration_and_manifest_fail_closed(configuration, monkeypatch, change):
    settings, user, manifest = configuration
    if change == "disabled":
        settings.INSTRUCT_WORKIQ_ENABLED = False
    elif change == "other_app":
        settings.WORK_IQ_CLIENT_ID = "unrelated-registration"
    elif change == "other_endpoint":
        settings.WORK_IQ_ENDPOINT = "https://unrelated.invalid/a2a/"
    elif change == "other_scope":
        settings.WORK_IQ_SCOPE = "different-scope"
    elif change == "other_owner":
        manifest["ownerId"] = "other"
    elif change == "other_tenant":
        user = replace(user, tenant_id="other")
    elif change == "no_assertion":
        user = replace(user, access_token="")
    elif change == "no_scope":
        user = replace(user, scopes=frozenset())
    elif change == "pending":
        manifest["pending"] = {"key": "agenda"}
    elif change == "missing_source":
        manifest["sources"].pop()
    elif change == "unverified":
        manifest["status"] = "native_seed_partial"
    elif change == "bad_url":
        manifest["sources"][0]["url"] = "https://attacker.invalid/"
    elif change == "bad_path":
        manifest["sources"][0]["path"] = "/me/messages/unrelated"
    elif change == "duplicate_url":
        manifest["sources"][0]["url"] = manifest["sources"][1]["url"]
    elif change == "wrong_class":
        manifest["classId"] = "other"
    settings.INSTRUCT_WORKIQ_MANIFEST_JSON = (
        "[]" if change == "invalid_manifest" else json.dumps(manifest)
    )
    monkeypatch.setattr(work, "WorkIQClient", lambda _: pytest.fail("No downstream call authorized"))
    result = await retrieve((settings, user, manifest))
    assert result["state"] == "unavailable" and not result["facts"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["no_citations", "outside_citation", "long", "failed"])
async def test_upstream_failures_never_become_empty_success(configuration, monkeypatch, invalid):
    *_, manifest = configuration

    def ask(**kwargs):
        if invalid == "failed":
            raise WorkIQTokenExchangeError("private detail must not escape")
        value = answer(manifest)
        if invalid == "no_citations":
            return replace(value, attributions=())
        if invalid == "outside_citation":
            return replace(value, attributions=(
                WorkIQAttribution("Other", "https://teams.microsoft.com/l/message/other/private"),
            ))
        return replace(value, text="x" * 12001)

    monkeypatch.setattr(work, "WorkIQClient", lambda _: SimpleNamespace(ask=ask))
    result = await retrieve(configuration)
    assert result["state"] in {"failed", "unavailable"} and not result["facts"]
    assert "private detail" not in json.dumps(result)


@pytest.mark.asyncio
async def test_protocol_diagnostics_do_not_log_upstream_message(configuration, monkeypatch, caplog):
    def ask(**kwargs):
        raise WorkIQProtocolError(
            "private upstream content", reason="json_rpc_error", rpc_code=-32000,
        )

    monkeypatch.setattr(work, "WorkIQClient", lambda _: SimpleNamespace(ask=ask))
    result = await retrieve(configuration)
    assert result["state"] == "failed" and not result["facts"]
    assert "reason=json_rpc_error rpc_code=-32000" in caplog.text
    assert "private upstream content" not in caplog.text + json.dumps(result)


def test_workiq_and_chat_timeouts_allow_longer_live_retrieval():
    settings = Settings(_env_file=None)
    assert settings.INSTRUCT_WORKIQ_TIMEOUT_SECONDS == 120
    assert settings.INSTRUCT_CHAT_TIMEOUT_SECONDS == 180
    assert Settings(_env_file=None, INSTRUCT_WORKIQ_TIMEOUT_SECONDS=180)
    with pytest.raises(ValueError):
        Settings(_env_file=None, INSTRUCT_WORKIQ_TIMEOUT_SECONDS=181)
