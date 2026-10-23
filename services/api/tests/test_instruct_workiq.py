from types import SimpleNamespace

import pytest

from app.instruct_workiq import (
    DelegatedSession, MARKER, TENANT_ID, WorkContextError,
    caller_mcp_session, query_collaboration_context, source_url,
)

OWNER = "ba12c12b-23b2-5b85-a3fe-89361cf8a461"
CLASS = "class-science-7a"


@pytest.mark.asyncio
async def test_missing_dedicated_identity_refuses_exchange_and_owner_read(monkeypatch):
    from app import instruct_workiq

    async def forbidden(*args, **kwargs):
        pytest.fail("missing configuration must not access an upstream service")

    monkeypatch.setattr(instruct_workiq, "TENANT_ID", "")
    monkeypatch.setattr(instruct_workiq, "API_CLIENT_ID", "")
    with pytest.raises(WorkContextError, match="workiq_auth_not_configured"):
        async with caller_mcp_session(user=user(), token_exchange=forbidden):
            pytest.fail("must not connect")
    with pytest.raises(WorkContextError, match="workiq_identity_mismatch"):
        await instruct_workiq.verify_owner(DelegatedSession("", OWNER, forbidden), OWNER)


def user(token="assertion", tenant=TENANT_ID):
    return SimpleNamespace(
        access_token=token, tenant_id=tenant, claims={"oid": OWNER},
        scopes=frozenset({"access_as_user"}),
    )


def manifest():
    return {
        "tenantId": TENANT_ID, "ownerId": OWNER, "classId": CLASS,
        "sources": [{"id": "native-id", "key": "discussion",
                     "path": "/chats/self/messages/native-id",
                     "url": "https://teams.microsoft.com/l/message/native-id"}],
    }


@pytest.mark.asyncio
async def test_caller_required_missing_configuration_and_no_fallback():
    for u, message in ((user(""), "caller_token_required"),
                       (user(), "workiq_auth_not_configured"),
                       (user(tenant="wrong"), "identity_mismatch")):
        with pytest.raises(WorkContextError, match=message):
            async with caller_mcp_session(user=u):
                pytest.fail("must not connect")


@pytest.mark.asyncio
async def test_obo_uses_caller_dedicated_app_and_redacts_error():
    calls = []

    async def exchange(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("SECRET upstream assertion")

    with pytest.raises(WorkContextError, match="workiq_delegation_failed") as error:
        async with caller_mcp_session(user=user(), token_exchange=exchange):
            pytest.fail("must not connect")
    assert "SECRET" not in str(error.value)
    assert calls[0]["user_assertion"] == "assertion"
    assert calls[0]["client_id"] == "242fb8bd-1383-55d3-a6ff-c5ef09ff0de2"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_exact_native_context_with_citations_and_nonpolicy_authority():
    calls = []

    async def call(name, arguments):
        calls.append((name, arguments))
        path = arguments["entityUrls"][0]
        row = ({"id": OWNER} if path.startswith("/me?") else
               {"id": "native-id", "body": {"content": MARKER + " graph reading"}})
        return {"results": [{"statusCode": 200, "data": row}]}

    result = await query_collaboration_context(
        session=DelegatedSession(TENANT_ID, OWNER, call), user=user(),
        class_id=CLASS, authorized_class_ids=frozenset({CLASS}),
        manifest=manifest(), query="graph reading",
    )
    assert result["status"] == "available"
    assert result["evidence"][0]["url"] == manifest()["sources"][0]["url"]
    assert "not_curriculum_policy" in result["evidence"][0]["authority"]
    assert len(calls) == 2 and all(c[0] == "fetch" for c in calls)


@pytest.mark.asyncio
async def test_scope_absence_auth_and_denied_source_have_explicit_states():
    kwargs = dict(session=None, user=user(), class_id=CLASS,
                  authorized_class_ids=frozenset({CLASS}), manifest=manifest(), query="graphs")
    assert (await query_collaboration_context(**kwargs))["status"] == "auth_required"
    kwargs["authorized_class_ids"] = frozenset()
    with pytest.raises(WorkContextError, match="scope_denied"):
        await query_collaboration_context(**kwargs)
    kwargs["authorized_class_ids"] = frozenset({CLASS})
    calls = []

    async def deny(name, arguments):
        calls.append(name)
        return {"results": [{"statusCode": 403}]}

    kwargs["session"] = DelegatedSession(TENANT_ID, OWNER, deny)
    with pytest.raises(WorkContextError, match="read_failed"):
        await query_collaboration_context(**kwargs)
    assert calls == ["fetch"]


@pytest.mark.parametrize("url", [
    "https://evil.example/test", "https://teams.microsoft.com@evil.example/a",
    "https://teams.microsoft.com:bad/a", "javascript:alert(1)",
])
def test_unsafe_citation_urls_rejected(url):
    assert not source_url(url)


def test_explicit_tool_policy_denial_is_preserved_without_raw_body():
    from app.instruct_workiq import tool_data

    with pytest.raises(WorkContextError, match="workiq_access_denied") as error:
        tool_data({"error": {"code": "AccessDenied", "message": "secret raw body"}})
    assert "secret" not in str(error.value)


def test_real_sdk_text_and_structured_wrappers_preserve_documented_fetch_shape():
    import json
    from mcp.types import CallToolResult, TextContent
    from app.instruct_workiq import fetched, tool_data

    payload = {"results": [{"statusCode": 200, "data": {"id": OWNER}}]}
    text = CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))])
    structured = CallToolResult(content=[], structuredContent=payload)
    assert fetched(text) == fetched(structured) == [{"id": OWNER}]
    # Documented jsonschema/YAML output decoding, not a claimed live seed schema.
    schema = CallToolResult(content=[TextContent(
        type="text", text="type: object\nproperties:\n  body:\n    type: object\n",
    )])
    assert tool_data(schema)["properties"]["body"]["type"] == "object"


@pytest.mark.asyncio
async def test_source_permission_error_never_searches_or_falls_back():
    calls = []

    async def call(name, arguments):
        calls.append((name, arguments))
        if len(calls) == 1:
            return {"results": [{"statusCode": 200, "data": {"id": OWNER}}]}
        return {"results": [{"statusCode": 403}]}

    with pytest.raises(WorkContextError, match="read_failed"):
        await query_collaboration_context(
            session=DelegatedSession(TENANT_ID, OWNER, call), user=user(),
            class_id=CLASS, authorized_class_ids=frozenset({CLASS}),
            manifest=manifest(), query="graph reading",
        )
    assert len(calls) == 2
    assert all(name == "fetch" for name, _ in calls)


@pytest.mark.asyncio
async def test_not_seeded_and_pending_are_not_successful_answers():
    async def call(name, arguments):
        return {"results": [{"statusCode": 200, "data": {"id": OWNER}}]}

    kwargs = dict(session=DelegatedSession(TENANT_ID, OWNER, call), user=user(),
                  class_id=CLASS, authorized_class_ids=frozenset({CLASS}),
                  manifest={**manifest(), "sources": []}, query="graphs")
    assert (await query_collaboration_context(**kwargs))["status"] == "not_seeded"
    kwargs["manifest"]["pending"] = {"key": "discussion"}
    assert (await query_collaboration_context(**kwargs))["status"] == "incomplete"
