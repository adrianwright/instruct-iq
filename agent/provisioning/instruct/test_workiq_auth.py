import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
import sys

import httpx
import pytest

from app.instruct_workiq import WorkContextError

spec = importlib.util.spec_from_file_location("instruct_workiq_auth", Path(__file__).with_name("workiq_auth.py"))
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


def test_public_metadata_pins_resource_scope_tenant_and_device_endpoint():
    def respond(request):
        data = ({
            "resource": auth.MCP_ENDPOINT, "scopes_supported": [auth.SCOPE],
            "authorization_servers": ["https://login.microsoftonline.com/organizations/v2.0"],
        } if request.url.host == "workiq.svc.cloud.microsoft" else {
            "issuer": auth.AUTHORITY + "/v2.0",
            "device_authorization_endpoint": auth.AUTHORITY + "/oauth2/v2.0/devicecode",
            "token_endpoint": auth.AUTHORITY + "/oauth2/v2.0/token",
        })
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert auth.discover(client)["scope"] == auth.SCOPE


def test_unknown_metadata_refuses_auth_instead_of_guessing_scope():
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"scopes_supported": ["unknown"]}),
    )) as client:
        with pytest.raises(WorkContextError, match="metadata_requires_review"):
            auth.discover(client)


def test_device_code_rejection_is_terminal_and_does_not_print_secrets():
    class Denied:
        def initiate_device_flow(self, scopes):
            assert scopes == [auth.SCOPE]
            return {"error": "unauthorized_client", "error_codes": [700016],
                    "error_description": "sensitive-upstream"}

    with pytest.raises(WorkContextError, match="700016") as error:
        auth.begin(Denied())
    assert "sensitive-upstream" not in str(error.value)


def test_actual_microsoft_device_verification_uri_is_supported():
    class Accepted:
        def initiate_device_flow(self, scopes):
            return {"device_code": "private-device-credential", "user_code": "PUBLIC123",
                    "verification_uri": "https://login.microsoft.com/device"}

    flow = auth.begin(Accepted())
    assert flow["verification_uri"] == "https://login.microsoft.com/device"


@pytest.mark.parametrize("claims", [
    {}, {"tid": "wrong", "oid": auth.OWNER_ID, "aud": auth.CLIENT_ID},
    {"tid": auth.TENANT_ID, "oid": "wrong", "aud": auth.CLIENT_ID},
    {"tid": auth.TENANT_ID, "oid": auth.OWNER_ID, "aud": "wrong"},
])
def test_wrong_or_absent_identity_never_reaches_mcp(claims):
    with pytest.raises(WorkContextError, match="identity_not_verified"):
        auth.require_identity({"access_token": "secret", "id_token_claims": claims})


def test_success_requires_real_target_identity_from_msal_response():
    assert auth.require_identity({
        "access_token": "secret", "id_token_claims": {
            "tid": auth.TENANT_ID, "oid": auth.OWNER_ID, "aud": auth.CLIENT_ID,
        },
    }) == (auth.TENANT_ID, auth.OWNER_ID)


@pytest.mark.asyncio
async def test_bounded_self_chat_resolver_never_selects_colleagues():
    calls = []

    async def call(name, arguments):
        calls.append((name, arguments))
        return {"results": [{"statusCode": 200, "data": {"value": [
            {"id": "shared", "chatType": "oneOnOne", "members": [
                {"userId": auth.OWNER_ID, "tenantId": auth.TENANT_ID},
                {"userId": "colleague", "tenantId": auth.TENANT_ID},
            ]},
            {"id": "owned-self", "chatType": "oneOnOne", "members": [
                {"userId": auth.OWNER_ID, "tenantId": auth.TENANT_ID},
            ]},
        ]}}]}

    session = auth.DelegatedSession(auth.TENANT_ID, auth.OWNER_ID, call)
    assert await auth.resolve_self_chat(session) == "owned-self"
    assert calls == [("fetch", {"entityUrls": ["/me/chats?$expand=members"]})]


@pytest.mark.asyncio
async def test_seed_mode_keeps_authenticated_session_open_through_readback(monkeypatch):
    events = []

    @asynccontextmanager
    async def transport(*args, **kwargs):
        events.append("transport_open")
        yield None, None, None
        events.append("transport_close")

    class Session:
        async def __aenter__(self):
            events.append("session_open")
            return self

        async def __aexit__(self, *args):
            events.append("session_close")

        async def initialize(self):
            events.append("initialize")

        async def call_tool(self, name, arguments):
            events.append("profile")
            return {"results": [{"statusCode": 200, "data": {"id": auth.OWNER_ID}}]}

    async def seed_and_readback(session, target):
        assert "session_close" not in events
        events.extend(["seed", "readback"])
        return {"status": "native_seed_verified", "sources": [{"id": str(i)} for i in range(4)]}

    monkeypatch.setattr("mcp.client.streamable_http.streamablehttp_client", transport)
    monkeypatch.setattr("mcp.ClientSession", lambda *args: Session())
    monkeypatch.setattr(auth, "seed_and_readback", seed_and_readback)
    await auth.verify_and_seed({
        "access_token": "memory-only", "id_token_claims": {
            "tid": auth.TENANT_ID, "oid": auth.OWNER_ID, "aud": auth.CLIENT_ID,
        },
    }, None, seed_requested=True)
    assert events == ["transport_open", "session_open", "initialize", "profile",
                      "seed", "readback", "session_close", "transport_close"]


def test_main_seed_flag_cannot_accidentally_run_verification_only(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(sys, "argv", ["workiq_auth.py", "--seed"])
    monkeypatch.setattr(auth, "discover", lambda client: {"tenantId": auth.TENANT_ID, "scope": auth.SCOPE})
    monkeypatch.setattr(auth, "public_application", lambda: SimpleNamespace(
        acquire_token_by_device_flow=lambda flow: {"access_token": "never-print-this"},
    ))
    monkeypatch.setattr(auth, "begin", lambda app: {
        "verification_uri": "https://login.microsoft.com/device", "user_code": "TESTONLY",
    })

    async def verify(result, target, *, seed_requested):
        calls.append(seed_requested)

    monkeypatch.setattr(auth, "verify_and_seed", verify)
    assert auth.main() == 0 and calls == [True]
    assert "never-print-this" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_real_sdk_task_group_preserves_safe_inner_diagnostic():
    import anyio
    from mcp import ClientSession

    incoming_send, incoming_receive = anyio.create_memory_object_stream(1)
    outgoing_send, outgoing_receive = anyio.create_memory_object_stream(1)
    try:
        with pytest.raises(BaseExceptionGroup) as error:
            async with ClientSession(incoming_receive, outgoing_send):
                raise WorkContextError("self_chat_collection_shape_unconfirmed")
        auth._stage = "self_chat_metadata_read"
        report = auth.diagnostic(error.value)
        assert report["stage"] == "self_chat_metadata_read"
        assert report["errors"] == [{"code": "self_chat_collection_shape_unconfirmed"}]
        assert not report["authorizationFailureObserved"]
    finally:
        await incoming_send.aclose()
        await outgoing_receive.aclose()


def test_nested_errors_report_observed_status_only_without_bodies():
    request = httpx.Request("GET", "https://workiq.svc.cloud.microsoft/mcp")
    error = httpx.HTTPStatusError("TOKEN never expose", request=request,
                                  response=httpx.Response(403, request=request))
    report = auth.diagnostic(ExceptionGroup("SECRET group", [ExceptionGroup("inner", [error])]))
    assert report["errors"] == [{"type": "HTTPStatusError", "httpStatus": 403}]
    assert report["authorizationFailureObserved"]
    assert "TOKEN" not in str(report) and "SECRET" not in str(report)


def test_permission_denial_does_not_hold_or_retry_credentials(monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda _: pytest.fail("must stop immediately"))
    report = auth.diagnostic(WorkContextError("workiq_access_denied"))
    assert auth.hold_memory_session(
        {"access_token": "secret"}, self_chat_id=None, seed_requested=True,
        failure=report,
    ) == 1


def test_memory_hold_requires_explicit_nonsecret_control_and_reuses_same_result(monkeypatch, capsys):
    import json

    reads = iter([
        {"authControl": {"requestId": "old"}},
        {"sources": [], "pending": None,
         "authControl": {"requestId": "new", "command": "resume-seed"}},
    ])
    monkeypatch.setattr(auth, "CONTROL_MANIFEST", SimpleNamespace(
        read_text=lambda **kwargs: json.dumps(next(reads)),
    ))
    monkeypatch.setattr(auth.time, "sleep", lambda _: None)
    result = {"access_token": "keep-only-in-memory"}
    seen = []

    async def verify(actual, target, *, seed_requested):
        assert actual is result and seed_requested
        seen.append(actual)

    monkeypatch.setattr(auth, "verify_and_seed", verify)
    assert auth.hold_memory_session(
        result, self_chat_id=None, seed_requested=True,
        failure={"authorizationFailureObserved": False},
    ) == 0
    assert seen == [result]
    assert "keep-only-in-memory" not in capsys.readouterr().out


def test_memory_hold_cannot_replay_pending_native_write(monkeypatch):
    import json

    reads = iter([
        {"authControl": {"requestId": "old"}},
        {"sources": [], "pending": {"key": "discussion"},
         "authControl": {"requestId": "retry", "command": "resume-seed"}},
        {"authControl": {"requestId": "close", "command": "close"}},
    ])
    monkeypatch.setattr(auth, "CONTROL_MANIFEST", SimpleNamespace(
        read_text=lambda **kwargs: json.dumps(next(reads)),
    ))
    monkeypatch.setattr(auth.time, "sleep", lambda _: None)
    monkeypatch.setattr(auth, "verify_and_seed", lambda *a, **k: pytest.fail("no replay"))
    assert auth.hold_memory_session(
        {"access_token": "secret"}, self_chat_id=None, seed_requested=True,
        failure={"authorizationFailureObserved": False},
    ) == 1
