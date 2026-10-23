import importlib.util
import json
import shutil
import sys
import uuid
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).parent
for name in ("provision_workiq_graph", "workiq_graph_seed"):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
provisioning = sys.modules["provision_workiq_graph"]
native = sys.modules["workiq_graph_seed"]


@pytest.fixture
def scratch():
    path = native.ROOT / ".local" / ("graph-seed-test-" + uuid.uuid4().hex)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path)


def app():
    return {"clientId": "new-dedicated-client", "tenantId": native.TENANT,
            "operatorId": native.OPERATOR, "scopes": list(native.SCOPES),
            "status": "provisioned_operator_only_delegated", "pending": None}


class Native:
    def __init__(self):
        self.writes = []
        self.rows = {}
        self.members = [{"userId": native.OPERATOR, "tenantId": native.TENANT}]
        self.profile = native.OPERATOR
        self.deny = False
        self.timeout = False

    def request(self, method, path, body=None):
        if method == "POST":
            self.writes.append((path, body))
            if self.deny:
                raise native.SeedError("graph_http_403_terminal_no_retry")
            if self.timeout:
                raise native.SeedError("graph_transport_outcome_unconfirmed_no_replay")
            identifier = str(len(self.writes))
            row = {**body, "id": identifier, "createdDateTime": "2026-10-15T21:00:00Z"}
            if path == "/me/events":
                row.update(webLink="https://outlook.office.com/event/" + identifier,
                           isOrganizer=True, organizer={"emailAddress": {"address": "demo@example.invalid"}})
            else:
                row.update(webUrl="https://teams.microsoft.com/l/message/" + identifier,
                           **{"from": {"user": {"id": native.OPERATOR}}})
            self.rows[path + "/" + identifier] = row
            return row
        if path.startswith("/me?"):
            return {"id": self.profile, "mail": "demo@example.invalid"}
        if path.startswith("/me/chats?"):
            return {"value": [{"id": "actual-returned-self", "chatType": "oneOnOne",
                               "members": self.members}]}
        if path.endswith("/members"):
            return {"value": self.members}
        return self.rows[path]


def test_guarded_graph_seed_idempotency_native_readback_and_private_event(scratch):
    graph = Native()
    path = scratch / "workiq.json"
    first = native.seed(graph, app(), manifest_path=path)
    second = native.seed(graph, app(), manifest_path=path)
    assert len(graph.writes) == 4
    assert first["sources"] == second["sources"]
    assert second["status"] == "native_seed_verified" and second["pending"] is None
    assert second["transport"] == "microsoft_graph"
    assert {s["key"] for s in second["sources"]} == {"discussion", "recap", "resource", "agenda"}
    assert all(s["id"] and s["url"] and s["createdDateTime"] for s in second["sources"])
    assert second["selfChatId"] == "actual-returned-self"
    event = graph.writes[-1][1]
    assert event["attendees"] == [] and event["sensitivity"] == "private"
    assert event["transactionId"]
    assert "2026-10-16" != second["sources"][0]["createdDateTime"][:10]


@pytest.mark.parametrize("failure", ["profile", "shared_chat"])
def test_wrong_operator_or_nonself_target_never_writes(scratch, failure):
    graph = Native()
    if failure == "profile":
        graph.profile = "wrong"
    else:
        graph.members.append({"userId": "colleague", "tenantId": native.TENANT})
    with pytest.raises(native.SeedError):
        native.seed(graph, app(), manifest_path=scratch / "workiq.json")
    assert graph.writes == []


@pytest.mark.parametrize("failure", ["deny", "timeout"])
def test_denied_or_ambiguous_graph_write_never_replays(scratch, failure):
    graph = Native()
    setattr(graph, failure, True)
    path = scratch / "workiq.json"
    with pytest.raises(native.SeedError):
        native.seed(graph, app(), manifest_path=path)
    assert json.loads(path.read_text())["pending"]["key"] == "discussion"
    with pytest.raises(native.SeedError, match="no_replay"):
        native.seed(graph, app(), manifest_path=path)
    assert len(graph.writes) == 1


def test_claims_require_dedicated_client_tenant_operator_and_only_approved_scopes():
    result = {"access_token": "secret", "scope": " ".join(native.SCOPES),
              "id_token_claims": {"tid": native.TENANT, "oid": native.OPERATOR,
                                  "aud": app()["clientId"]}}
    native.verified_claims(result, app())
    for key in ("tid", "oid", "aud"):
        bad = {**result, "id_token_claims": {**result["id_token_claims"], key: "wrong"}}
        with pytest.raises(native.SeedError):
            native.verified_claims(bad, app())
    with pytest.raises(native.SeedError):
        native.verified_claims({**result, "scope": result["scope"] + " Mail.Send"}, app())
    assert "secret" not in repr(native.Graph("secret"))


def test_graph_http_denial_has_safe_status_and_no_retry_or_redirect():
    calls = []

    def deny(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"message": "SECRET body"}})

    with httpx.Client(transport=httpx.MockTransport(deny)) as client:
        graph = native.Graph("SECRET token", client)
        with pytest.raises(native.SeedError, match="graph_http_403_terminal_no_retry") as error:
            graph.request("POST", "/me/events", {})
    assert len(calls) == 1 and "SECRET" not in str(error.value)


class Directory:
    def __init__(self):
        self.app = None
        self.sp = None
        self.assignments = []
        self.grants = []
        self.calls = []

    def cli(self, args):
        if args[:2] == ["account", "show"]:
            return {"tenantId": provisioning.TENANT, "id": provisioning.SUBSCRIPTION}
        return {"id": "graph-resource", "oauth2PermissionScopes": [
            {"value": s, "id": "scope-" + s, "isEnabled": True} for s in provisioning.SCOPES
        ]}

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/applications?"):
            return {"value": []}
        if path == "/applications":
            self.app = {**body, "id": "owned-app", "appId": "new-dedicated-client"}
            return self.app
        if path == "/applications/owned-app":
            return self.app
        if path == "/servicePrincipals":
            self.sp = {**body, "id": "owned-sp"}
            return self.sp
        if path == "/servicePrincipals/owned-sp":
            return self.sp
        if path.endswith("/appRoleAssignments"):
            return {"value": []}
        if path.endswith("/appRoleAssignedTo"):
            if method == "POST":
                self.assignments.append(body)
                return body
            return {"value": self.assignments}
        if path.startswith("/servicePrincipals/") and path.endswith("/oauth2PermissionGrants"):
            return {"value": self.grants}
        if path == "/oauth2PermissionGrants":
            row = {**body, "id": "operator-consent"}
            self.grants.append(row)
            return row
        if path == "/oauth2PermissionGrants/operator-consent":
            return self.grants[0]
        pytest.fail(f"unapproved directory request {method} {path}")


def test_provision_exact_four_scopes_single_user_consent_no_credentials_and_idempotency(scratch):
    directory = Directory()
    path = scratch / "app.json"
    first = provisioning.provision(directory, path)
    second = provisioning.provision(directory, path)
    assert first == second
    assert sum(c[0] == "POST" and c[1] == "/applications" for c in directory.calls) == 1
    assert directory.sp["appRoleAssignmentRequired"] is True
    assert directory.assignments[0]["principalId"] == native.OPERATOR
    assert directory.grants[0]["consentType"] == "Principal"
    assert directory.grants[0]["principalId"] == native.OPERATOR
    assert set(directory.grants[0]["scope"].split()) == set(native.SCOPES)
    assert all(p["type"] == "Scope" for p in directory.app["requiredResourceAccess"][0]["resourceAccess"])
    assert "passwordCredentials" not in directory.app and "keyCredentials" not in directory.app


def test_provision_refuses_unexpected_consent_without_rewriting_it(scratch):
    directory = Directory()
    path = scratch / "app.json"
    provisioning.provision(directory, path)
    directory.grants[0]["consentType"] = "AllPrincipals"
    before = len(directory.calls)
    with pytest.raises(provisioning.ProvisionError, match="unexpected_delegated_consent"):
        provisioning.provision(directory, path)
    assert all(method == "GET" for method, _, _ in directory.calls[before:])
