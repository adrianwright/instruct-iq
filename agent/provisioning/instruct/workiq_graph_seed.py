"""Approved Graph-only native synthetic seed; isolated public client, no MCP calls."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import msal

from provision_workiq_graph import APP_MANIFEST, OPERATOR, ROOT, SCOPES, TENANT

MANIFEST = ROOT / ".local" / "instruct-iq-deployment" / "workiq.json"
FIXTURE = ROOT / "data" / "instruct" / "work" / "evidence.json"
MARKER = "Instruct IQ synthetic demo"


class SeedError(RuntimeError):
    pass


def save(value: dict[str, Any], path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def progress(stage: str) -> None:
    print(json.dumps({"status": "graph_seed_progress", "stage": stage}), flush=True)


@dataclass(repr=False)
class Graph:
    token: str = field(repr=False)
    http: Any = field(default_factory=lambda: httpx.Client(timeout=30, follow_redirects=False), repr=False)

    def __repr__(self):
        return "Graph(delegated_memory_only=True)"

    def request(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        if not path.startswith(("/me", "/chats/")) or path.startswith("//"):
            raise SeedError("graph_resource_not_approved")
        try:
            response = self.http.request(
                method, "https://graph.microsoft.com/v1.0" + path,
                headers={"Authorization": f"Bearer {self.token}"}, json=body,
            )
        except httpx.HTTPError:
            raise SeedError("graph_transport_outcome_unconfirmed_no_replay") from None
        if response.status_code >= 300:
            # Emit only known machine codes, never a response body or free-form message.
            known_codes = {
                "BadRequest", "InvalidRequest", "InvalidUri", "Request_BadRequest",
                "ErrorInvalidIdMalformed", "Authorization_RequestDenied", "Forbidden",
                "AccessDenied", "InvalidAuthenticationToken", "UnknownError",
                "NotFound", "TooManyRequests",
            }
            try:
                code = response.json().get("error", {}).get("code")
            except (ValueError, AttributeError):
                code = None
            suffix = "_code_" + code if isinstance(code, str) and code in known_codes else ""
            raise SeedError(f"graph_http_{response.status_code}_terminal_no_retry{suffix}")
        try:
            result = response.json()
        except ValueError:
            raise SeedError("graph_json_response_unconfirmed") from None
        if not isinstance(result, dict):
            raise SeedError("graph_response_shape_unconfirmed")
        return result


def verified_claims(result: dict[str, Any], app: dict[str, Any]) -> None:
    claims = result.get("id_token_claims", {})
    granted = {s.removeprefix("https://graph.microsoft.com/") for s in result.get("scope", "").split()}
    if (
        not TENANT or not OPERATOR
        or app.get("tenantId") != TENANT or app.get("operatorId") != OPERATOR
        or app.get("status") != "provisioned_operator_only_delegated"
        or app.get("pending") or app.get("scopes") != list(SCOPES)
        or not result.get("access_token") or claims.get("tid") != TENANT
        or claims.get("oid") != OPERATOR or claims.get("aud") != app.get("clientId")
        or not set(SCOPES) <= granted
        or not granted <= set(SCOPES) | {"openid", "profile", "email"}
    ):
        raise SeedError("approved_operator_client_and_scopes_required")


def link(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlparse(value)
        return (url.scheme == "https" and not url.username and not url.password
                and url.port in (None, 443)
                and url.hostname in {"teams.microsoft.com", "outlook.office.com", "outlook.office365.com"})
    except ValueError:
        return False


def seed(graph: Graph, app: dict[str, Any], *, manifest_path: Path = MANIFEST) -> dict[str, Any]:
    progress("operator_profile")
    profile = graph.request("GET", "/me?$select=id,userPrincipalName,mail")
    if profile.get("id") != OPERATOR:
        raise SeedError("signed_in_operator_mismatch")
    progress("operator_self_chat_resolution")
    chats = graph.request("GET", "/me/chats?$expand=members&$top=25")
    matches = []
    for chat in chats.get("value", []):
        members = chat.get("members", [])
        if (chat.get("chatType") == "oneOnOne" and len(members) == 1
                and members[0].get("userId") == OPERATOR and members[0].get("tenantId") == TENANT):
            matches.append(chat)
    if len(matches) != 1 or not matches[0].get("id"):
        raise SeedError("exact_operator_self_chat_not_found_in_bounded_page")
    chat_id = matches[0]["id"]
    chat_path = "/chats/" + quote(chat_id, safe="")
    members = graph.request("GET", chat_path + "/members").get("value", [])
    if (len(members) != 1 or members[0].get("userId") != OPERATOR
            or members[0].get("tenantId") != TENANT):
        raise SeedError("exact_self_chat_ownership_unverified")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if manifest.get("pending"):
        raise SeedError("pending_native_write_requires_reconciliation_no_replay")
    if manifest and (manifest.get("tenantId") != TENANT or manifest.get("ownerId") != OPERATOR
                     or manifest.get("classId") != fixture["classId"]):
        raise SeedError("native_manifest_identity_mismatch")
    if manifest.get("sources") and (
        manifest.get("transport") != "microsoft_graph"
        or manifest.get("seedClientId") != app["clientId"] or manifest.get("selfChatId") != chat_id
    ):
        raise SeedError("native_manifest_provenance_mismatch")
    manifest.update(
        tenantId=TENANT, ownerId=OPERATOR, classId=fixture["classId"],
        marker=MARKER, transport="microsoft_graph", seedClientId=app["clientId"],
        selfChatId=chat_id, scenarioDate=fixture["scenarioDate"],
        approval="Explicit isolated Graph seed architecture and four operator-only delegated scopes",
    )
    sources = manifest.setdefault("sources", [])
    keys = [s.get("key") for s in sources]
    if len(keys) != len(set(keys)) or not set(keys) <= {"discussion", "recap", "resource", "agenda"}:
        raise SeedError("native_manifest_source_set_invalid")

    def verify(source: dict[str, Any]) -> dict[str, Any]:
        key, identifier = source["key"], source["id"]
        expected_path = ("/me/events/" if key == "agenda" else chat_path + "/messages/") + quote(identifier, safe="")
        if source["path"] != expected_path:
            raise SeedError("native_source_path_mismatch")
        row = graph.request("GET", expected_path)
        url = row.get("webLink") if key == "agenda" else row.get("webUrl")
        if (row.get("id") != identifier or MARKER not in row.get("body", {}).get("content", "")
                or not row.get("createdDateTime") or not link(url)):
            raise SeedError("native_source_readback_unverified")
        if key == "agenda":
            own_address = (profile.get("mail") or profile.get("userPrincipalName", "")).casefold()
            if (row.get("attendees") or row.get("sensitivity") != "private"
                    or not row.get("isOrganizer")
                    or row.get("organizer", {}).get("emailAddress", {}).get("address", "").casefold() != own_address):
                raise SeedError("private_event_ownership_unverified")
        elif row.get("from", {}).get("user", {}).get("id") != OPERATOR:
            raise SeedError("native_message_author_mismatch")
        return {**source, "url": url, "createdDateTime": row["createdDateTime"]}

    for source in sources:
        verify(source)
    for key in ("discussion", "recap", "resource", "agenda"):
        if key in keys:
            continue
        body: dict[str, Any] = {"body": {"contentType": "text", "content": fixture[key]}}
        parent = chat_path + "/messages"
        if key == "agenda":
            parent = "/me/events"
            start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(
                hour=15, minute=0, second=0, microsecond=0)
            body.update(subject=f"{MARKER} — proposed science-team planning agenda",
                        sensitivity="private", attendees=[], showAs="free",
                        transactionId=str(uuid.uuid5(uuid.NAMESPACE_URL,
                            f"instruct-iq-science-7a-work-v1:{TENANT}:{OPERATOR}:{app['clientId']}:agenda")),
                        start={"dateTime": start.replace(tzinfo=None).isoformat(), "timeZone": "UTC"},
                        end={"dateTime": (start + timedelta(minutes=30)).replace(tzinfo=None).isoformat(), "timeZone": "UTC"})
        manifest.update(status="graph_seed_pending_native_write", pending={"key": key, "parent": parent})
        save(manifest, manifest_path)
        progress("native_write_" + key)
        created = graph.request("POST", parent, body)
        identifier = created.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise SeedError("native_write_identity_unconfirmed_no_replay")
        manifest["pending"]["id"] = identifier
        save(manifest, manifest_path)
        source = {"key": key, "id": identifier, "path": parent + "/" + quote(identifier, safe="")}
        progress("native_readback_" + key)
        sources.append(verify(source))
        manifest.update(pending=None, status="graph_native_seed_partial")
        save(manifest, manifest_path)
    progress("all_exact_sources_readback")
    for source in sources:
        verify(source)
    manifest.update(status="native_seed_verified", pending=None)
    save(manifest, manifest_path)
    return manifest


def main() -> int:
    if not TENANT or not OPERATOR:
        raise SystemExit("Dedicated instructional tenant and operator configuration required")
    app = json.loads(APP_MANIFEST.read_text(encoding="utf-8"))
    if app.get("status") != "provisioned_operator_only_delegated" or app.get("pending"):
        raise SystemExit("Dedicated approved Graph application must be provisioned first")
    existing = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    if existing.get("pending"):
        raise SystemExit("Pending native write: reconcile; no sign-in started")
    application = msal.PublicClientApplication(
        app["clientId"], authority=f"https://login.microsoftonline.com/{TENANT}",
        token_cache=msal.TokenCache(), exclude_scopes=["offline_access"],
    )
    flow = application.initiate_device_flow(scopes=["https://graph.microsoft.com/" + s for s in SCOPES])
    if not flow.get("device_code") or flow.get("verification_uri") not in {
        "https://login.microsoft.com/device", "https://microsoft.com/devicelogin",
    }:
        print(json.dumps({"status": "not_ready", "reason": "dedicated_device_flow_not_accepted",
                          "errorCodes": flow.get("error_codes", [])}), flush=True)
        return 1
    print(json.dumps({"status": "waiting_for_graph_demo_signin",
                      "verificationUri": flow["verification_uri"], "userCode": flow["user_code"],
                      "expiresIn": flow.get("expires_in"), "tenantId": TENANT,
                      "operatorId": OPERATOR, "clientId": app["clientId"], "scopes": SCOPES}), flush=True)
    result = application.acquire_token_by_device_flow(flow)
    try:
        verified_claims(result, app)
    except SeedError as error:
        print(json.dumps({"status": "not_ready", "reason": str(error)}), flush=True)
        return 1
    with httpx.Client(timeout=30, follow_redirects=False) as http:
        graph = Graph(result["access_token"], http)
        deadline = time.monotonic() + 600
        seen = set()
        while True:
            try:
                manifest = seed(graph, app)
                print(json.dumps({"status": manifest["status"], "nativeSources": manifest["sources"],
                                  "transport": "microsoft_graph", "workiqRetrievalVerified": False}), flush=True)
                return 0
            except SeedError as error:
                code = str(error)
            except Exception as error:
                code = "graph_seed_exception_" + type(error).__name__
            print(json.dumps({"status": "not_ready", "reason": code}), flush=True)
            if "http_401" in code or "http_403" in code:
                return 1
            print(json.dumps({"status": "credentials_retained_in_memory", "secondsMaximum": 600,
                              "control": "workiq-graph-app.json authControl unique requestId / resume-seed or close",
                              "automaticRetry": False}), flush=True)
            while time.monotonic() < deadline:
                time.sleep(1)
                control = json.loads(APP_MANIFEST.read_text(encoding="utf-8")).get("authControl", {})
                request_id = control.get("requestId")
                if not request_id or request_id in seen:
                    continue
                seen.add(request_id)
                if control.get("command") == "close":
                    return 1
                if control.get("command") == "resume-seed":
                    state = json.loads(MANIFEST.read_text(encoding="utf-8"))
                    if state.get("pending"):
                        print(json.dumps({"status": "resume_refused", "reason": "pending_native_write_no_replay"}), flush=True)
                        continue
                    break
            else:
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
