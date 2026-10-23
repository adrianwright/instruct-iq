import importlib.util
import json
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

HERE = Path(__file__).parent
for name in ("provision_workiq_graph", "workiq_graph_seed", "workiq_graph_verify"):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
verifier = sys.modules["workiq_graph_verify"]


@pytest.fixture
def scratch():
    path = verifier.ROOT / ".local" / ("manual-verification-test-" + uuid.uuid4().hex)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path)


def candidates(chat_id="48:notes"):
    context = quote(json.dumps({"contextType": "chat", "oid": "8:orgid:" + verifier.OPERATOR}))
    ids = ("1000000000001", "1000000000002", "1000000000003")
    return {
        "tenantId": verifier.TENANT, "ownerId": verifier.OPERATOR,
        "classId": verifier.CLASS_ID, "marker": verifier.MARKER, "selfChatId": chat_id,
        "origin": "user_created_teams_self_chat", "pending": None,
        "sources": [{
            "key": key, "id": identifier, "path": f"/chats/{chat_id}/messages/{identifier}",
            "url": f"https://teams.microsoft.com/l/message/{chat_id}/{identifier}?context={context}",
        } for key, identifier in zip(("discussion", "recap", "resource"), ids)],
    }


def application():
    return {
        "tenantId": verifier.TENANT, "operatorId": verifier.OPERATOR,
        "clientId": "dedicated-client", "scopes": list(verifier.SCOPES),
        "status": "provisioned_operator_only_delegated", "pending": None,
    }


class Native:
    def __init__(self, candidate):
        self.calls = []
        self.candidate = candidate
        self.member = verifier.OPERATOR
        self.sender = verifier.OPERATOR
        self.fail_key = None
        self.deny = False
        self.returned_url = None

    def respond(self, request):
        self.calls.append((request.method, request.url.path, str(request.url.query)))
        assert request.method == "GET"
        path = request.url.path.removeprefix("/v1.0")
        if path == "/me":
            data = {"id": verifier.OPERATOR}
        elif path == f"/chats/{self.candidate['selfChatId']}/members":
            data = {"value": [{"userId": self.member, "tenantId": verifier.TENANT}]}
        else:
            source, = [s for s in self.candidate["sources"] if s["path"] == path]
            if self.deny:
                return httpx.Response(403, json={"error": {"message": "SECRET body"}})
            key = source["key"]
            content = f"<p>{verifier.MARKER} | {verifier.CLASS_ID} | {key}</p>"
            if self.fail_key == key:
                content = "unrelated content"
            data = {
                "id": source["id"], "from": {"user": {"id": self.sender}},
                "body": {"content": content}, "createdDateTime": "2026-10-15T20:33:00.123Z",
            }
            if self.returned_url:
                data["webUrl"] = self.returned_url
        return httpx.Response(200, json=data)


def test_notes_alias_exact_four_gets_without_unsupported_members_probe(scratch):
    candidate = candidates()
    server = Native(candidate)
    path = scratch / "verified.json"
    with httpx.Client(transport=httpx.MockTransport(server.respond)) as client:
        graph = verifier.ReadOnlyGraph("memory-only", candidate, client)
        result = verifier.verify(graph, candidate, application(), manifest_path=path)
        assert result == verifier.verify(graph, candidate, application(), manifest_path=path)
    assert len(server.calls) == 8
    assert [c[1] for c in server.calls[:4]] == [
        "/v1.0/me",
        *(f"/v1.0{s['path']}" for s in candidate["sources"]),
    ]
    assert result["status"] == "native_seed_verified"
    assert result["nativeWritesByAssistant"] == 0 and result["pending"] is None
    assert len(result["sources"]) == 3
    assert [s["url"] for s in result["sources"]] == [s["url"] for s in candidate["sources"]]
    assert all(s["contentVerified"] and s["createdDateTime"] for s in result["sources"])
    assert all("text" not in s and "body" not in s for s in result["sources"])


@pytest.mark.parametrize("failure", ["member", "sender", "labels", "returned_url"])
def test_wrong_ownership_labels_or_native_url_never_persists_verification(scratch, failure):
    candidate = candidates("ordinary-self-chat" if failure == "member" else "48:notes")
    server = Native(candidate)
    if failure == "member":
        server.member = "other"
    elif failure == "sender":
        server.sender = "other"
    elif failure == "labels":
        server.fail_key = "resource"
    else:
        server.returned_url = candidate["sources"][0]["url"].replace("48:notes", "other-chat")
    path = scratch / "verified.json"
    with httpx.Client(transport=httpx.MockTransport(server.respond)) as client:
        with pytest.raises(verifier.SeedError):
            verifier.verify(verifier.ReadOnlyGraph("secret", candidate, client),
                            candidate, application(), manifest_path=path)
    assert not path.exists()


def test_denial_terminal_no_retry_or_content_leak(scratch):
    candidate = candidates()
    server = Native(candidate)
    server.deny = True
    with httpx.Client(transport=httpx.MockTransport(server.respond)) as client:
        with pytest.raises(verifier.SeedError, match="graph_http_403_terminal_no_retry") as error:
            verifier.verify(verifier.ReadOnlyGraph("secret", candidate, client),
                            candidate, application(), manifest_path=scratch / "verified.json")
    assert len(server.calls) == 2
    assert "SECRET" not in str(error.value)


def test_read_only_transport_refuses_post_history_or_other_entity():
    candidate = candidates()
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("no network"))) as client:
        graph = verifier.ReadOnlyGraph("secret", candidate, client)
        for method, path in (
            ("POST", "/me/events"), ("GET", "/chats/48:notes/messages"),
            ("GET", "/me/chats"), ("GET", "/chats/48:notes/messages/9999999999999"),
            ("GET", "/chats/48:notes/members"),
        ):
            with pytest.raises(verifier.SeedError, match="read_only_exact_source"):
                graph.request(method, path)


def test_tampered_supplied_url_owner_or_class_fails_before_auth():
    for field, bad in (("ownerId", "wrong"), ("classId", "wrong")):
        with pytest.raises(verifier.SeedError):
            verifier.validate_candidates({**candidates(), field: bad})
    candidate = candidates()
    candidate["sources"][0]["url"] = candidate["sources"][0]["url"].replace(
        verifier.OPERATOR, "other-owner")
    with pytest.raises(verifier.SeedError):
        verifier.validate_candidates(candidate)


def test_main_requests_only_two_read_scopes_and_runs_all_reads_same_memory_session(scratch, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["workiq_graph_verify.py"])
    candidate = candidates()
    app = application()
    for name, content in (("candidate.json", candidate), ("app.json", app)):
        (scratch / name).write_text(json.dumps(content))
    monkeypatch.setattr(verifier, "CANDIDATE", scratch / "candidate.json")
    monkeypatch.setattr(verifier, "APP_MANIFEST", scratch / "app.json")
    monkeypatch.setattr(verifier, "MANIFEST", scratch / "verified.json")
    server = Native(candidate)
    real_client = httpx.Client
    monkeypatch.setattr(verifier.httpx, "Client", lambda **kwargs:
                        real_client(transport=httpx.MockTransport(server.respond), **kwargs))
    calls = []

    class Public:
        def get_accounts(self):
            return []

        def initiate_device_flow(self, scopes):
            calls.append(scopes)
            return {"device_code": "never-print-device", "user_code": "TESTONLY",
                    "verification_uri": "https://login.microsoft.com/device", "expires_in": 900}

        def acquire_token_by_device_flow(self, flow):
            return {
                "access_token": "never-print-token", "scope": "User.Read Chat.Read",
                "id_token_claims": {"tid": verifier.TENANT, "oid": verifier.OPERATOR, "aud": app["clientId"]},
            }

    monkeypatch.setattr(verifier, "cached_application", lambda app: Public())
    assert verifier.main() == 0
    assert calls == [["https://graph.microsoft.com/User.Read", "https://graph.microsoft.com/Chat.Read"]]
    assert len(server.calls) == 4
    output = capsys.readouterr().out
    assert "never-print-token" not in output and "never-print-device" not in output


def test_ordinary_chat_still_requires_exact_membership_before_three_messages(scratch):
    candidate = candidates("ordinary-self-chat")
    server = Native(candidate)
    with httpx.Client(transport=httpx.MockTransport(server.respond)) as client:
        verifier.verify(verifier.ReadOnlyGraph("secret", candidate, client),
                        candidate, application(), manifest_path=scratch / "verified.json")
    assert len(server.calls) == 5
    assert server.calls[1][1] == "/v1.0/chats/ordinary-self-chat/members"


def test_dpapi_application_uses_dedicated_encrypted_cache_with_refresh_support(scratch, monkeypatch):
    import msal_extensions

    captured = {}

    def persistence(location, entropy):
        captured.update(location=location, entropy=entropy)
        return type("Encrypted", (), {"is_encrypted": True})()

    monkeypatch.setattr(msal_extensions, "FilePersistenceWithDataProtection", persistence)
    monkeypatch.setattr(msal_extensions, "PersistedTokenCache", lambda value: "encrypted-cache")
    monkeypatch.setattr(verifier.msal, "PublicClientApplication",
                        lambda client, **kwargs: captured.update(client=client, **kwargs))
    verifier.cached_application(application(), cache_path=scratch / "dedicated.bin")
    assert captured["token_cache"] == "encrypted-cache"
    assert captured["authority"].endswith(verifier.TENANT)
    assert captured["entropy"].startswith("Instruct IQ:")
    assert "exclude_scopes" not in captured
    assert "AMC IQ" not in captured["location"]


def test_cache_reuse_requires_matching_account_and_revalidates_token_claims():
    app = application()
    token = {
        "access_token": "secret", "scope": "User.Read Chat.Read",
        "id_token_claims": {"tid": verifier.TENANT, "oid": verifier.OPERATOR, "aud": app["clientId"]},
    }

    class Cache:
        def get_accounts(self):
            return [{"local_account_id": verifier.OPERATOR, "realm": verifier.TENANT}]

        def acquire_token_silent_with_error(self, scopes, account):
            assert scopes == ["https://graph.microsoft.com/User.Read", "https://graph.microsoft.com/Chat.Read"]
            return token

    assert verifier.cached_result(Cache(), app) is token
    token["id_token_claims"]["oid"] = "wrong"
    with pytest.raises(verifier.SeedError, match="operator_token"):
        verifier.cached_result(Cache(), app)


def test_cache_wrong_owner_never_acquires_or_starts_device_auth():
    class WrongCache:
        def get_accounts(self):
            return [{"local_account_id": "wrong", "realm": verifier.TENANT}]

        def acquire_token_silent_with_error(self, *args, **kwargs):
            pytest.fail("wrong-account token must not be used")

        def initiate_device_flow(self, *args, **kwargs):
            pytest.fail("must not initiate new sign-in")

    with pytest.raises(verifier.SeedError, match="cache_operator_mismatch"):
        verifier.cached_result(WrongCache(), application())


def test_silent_only_does_not_start_signin_without_a_cached_account(scratch, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["workiq_graph_verify.py", "--silent-only"])
    for name, data in (("candidate.json", candidates()), ("app.json", application())):
        (scratch / name).write_text(json.dumps(data))
    monkeypatch.setattr(verifier, "CANDIDATE", scratch / "candidate.json")
    monkeypatch.setattr(verifier, "APP_MANIFEST", scratch / "app.json")
    monkeypatch.setattr(verifier, "MANIFEST", scratch / "verified.json")

    class EmptyCache:
        def get_accounts(self):
            return []

        def initiate_device_flow(self, **kwargs):
            pytest.fail("silent-only means no device flow")

    monkeypatch.setattr(verifier, "cached_application", lambda app: EmptyCache())
    assert verifier.main() == 1
    assert "dedicated_cached_signin_required" in capsys.readouterr().out


def test_graph_safe_error_code_distinguishes_bad_request_without_body_leak():
    candidate = candidates()
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(400, json={
            "error": {"code": "BadRequest", "message": "SECRET unsafe body"},
        }),
    )) as client:
        graph = verifier.ReadOnlyGraph("SECRET token", candidate, client)
        with pytest.raises(verifier.SeedError, match="http_400.*code_BadRequest") as error:
            graph.request("GET", "/me?$select=id")
    assert "SECRET" not in str(error.value)


def test_real_windows_dpapi_roundtrip_never_persists_plaintext(scratch):
    from msal_extensions import FilePersistenceWithDataProtection

    path = scratch / "synthetic-only-dpapi.bin"
    persistence = FilePersistenceWithDataProtection(str(path), entropy="Instruct IQ:test-only")
    placeholder = "synthetic-access-and-refresh-placeholder-not-real"
    persistence.save(placeholder)
    assert persistence.is_encrypted and persistence.load() == placeholder
    assert placeholder.encode() not in path.read_bytes()


def test_default_cache_path_is_new_app_specific_under_instruct_iq(scratch, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(scratch))
    client = "6005dd0c-5765-528d-b564-97b82d97e24d"
    assert verifier.default_cache_path(client) == scratch / "Instruct IQ" / "msal" / (client + ".bin")
