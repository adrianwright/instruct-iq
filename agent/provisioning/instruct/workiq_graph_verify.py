"""Read only three user-supplied native Teams sources; never seed or enumerate."""
from __future__ import annotations

import html
import argparse
import json
import os
import re
import time
import uuid
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import msal

from provision_workiq_graph import APP_MANIFEST, OPERATOR, ROOT, SCOPES, TENANT
from workiq_graph_seed import Graph, SeedError, save

CANDIDATE = ROOT / ".local" / "instruct-iq-deployment" / "workiq-manual-sources.json"
MANIFEST = ROOT / ".local" / "instruct-iq-deployment" / "workiq.json"
READ_SCOPES = ("User.Read", "Chat.Read")
CLASS_ID = "class-science-7a"
MARKER = "Instruct IQ synthetic demo"


def url_identity(url: Any, *, chat_id: str, message_id: str, require_context: bool) -> None:
    if not isinstance(url, str):
        raise SeedError("manual_source_url_missing")
    try:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname != "teams.microsoft.com"
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or unquote(parsed.path) != f"/l/message/{chat_id}/{message_id}"):
            raise ValueError()
        query = parse_qs(parsed.query)
        if query.get("tenantId") and query["tenantId"] != [TENANT]:
            raise ValueError()
        contexts = query.get("context", [])
        if require_context and len(contexts) != 1:
            raise ValueError()
        if contexts:
            if len(contexts) != 1:
                raise ValueError()
            context = json.loads(contexts[0])
            if require_context and context.get("oid") != "8:orgid:" + OPERATOR:
                raise ValueError()
            if context.get("oid") not in (None, "8:orgid:" + OPERATOR):
                raise ValueError()
            if context.get("contextType") not in (None, "chat"):
                raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise SeedError("manual_source_url_identity_mismatch") from None


def validate_candidates(candidate: dict[str, Any]) -> None:
    if (
        not TENANT or not OPERATOR
        or candidate.get("tenantId") != TENANT or candidate.get("ownerId") != OPERATOR
        or candidate.get("classId") != CLASS_ID or candidate.get("marker") != MARKER
        or candidate.get("origin") != "user_created_teams_self_chat"
        or candidate.get("pending") is not None
    ):
        raise SeedError("manual_candidate_scope_mismatch")
    chat_id = candidate.get("selfChatId")
    if not isinstance(chat_id, str) or not re.fullmatch(r"[A-Za-z0-9:@._-]+", chat_id):
        raise SeedError("exact_supplied_chat_required")
    sources = candidate.get("sources", [])
    if (len(sources) != 3 or {s.get("key") for s in sources} != {"discussion", "recap", "resource"}
            or len({s.get("id") for s in sources}) != 3):
        raise SeedError("exact_three_unique_manual_sources_required")
    for source in sources:
        identifier = source.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"\d{13,20}", identifier):
            raise SeedError("manual_message_identity_invalid")
        if source.get("path") != f"/chats/{chat_id}/messages/{identifier}":
            raise SeedError("manual_source_path_identity_mismatch")
        url_identity(source.get("url"), chat_id=chat_id, message_id=identifier, require_context=True)


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


class ReadOnlyGraph(Graph):
    def __init__(self, token: str, candidate: dict[str, Any], http: Any):
        super().__init__(token, http)
        validate_candidates(candidate)
        self.allowed = {
            "/me?$select=id",
            *(source["path"] for source in candidate["sources"]),
        }
        if candidate["selfChatId"] != "48:notes":
            self.allowed.add(f"/chats/{candidate['selfChatId']}/members")

    def request(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        if method != "GET" or body is not None or path not in self.allowed:
            raise SeedError("read_only_exact_source_operation_required")
        return super().request(method, path)


def claims_verified(result: dict[str, Any], app: dict[str, Any]) -> None:
    claims = result.get("id_token_claims", {})
    granted = {s.removeprefix("https://graph.microsoft.com/") for s in result.get("scope", "").split()}
    if (
        not TENANT or not OPERATOR
        or app.get("tenantId") != TENANT or app.get("operatorId") != OPERATOR
        or app.get("status") != "provisioned_operator_only_delegated" or app.get("pending")
        or app.get("scopes") != list(SCOPES) or not result.get("access_token")
        or claims.get("tid") != TENANT or claims.get("oid") != OPERATOR
        or claims.get("aud") != app.get("clientId")
        or not set(READ_SCOPES) <= granted
        or not granted <= set(SCOPES) | {"openid", "profile", "email"}
    ):
        raise SeedError("manual_verifier_operator_token_or_read_scopes_invalid")


def default_cache_path(client_id: str) -> Path:
    try:
        uuid.UUID(client_id)
    except ValueError:
        raise SeedError("dedicated_cache_client_id_invalid") from None
    local = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not local:
        raise SeedError("windows_dpapi_cache_required_no_plaintext_fallback")
    return Path(local) / "Instruct IQ" / "msal" / (client_id + ".bin")


def cached_application(app: dict[str, Any], *, cache_path: Path | None = None) -> Any:
    from msal_extensions import FilePersistenceWithDataProtection, PersistedTokenCache

    path = cache_path or default_cache_path(app["clientId"])
    if os.name != "nt":
        raise SeedError("windows_dpapi_cache_required_no_plaintext_fallback")
    path.parent.mkdir(parents=True, exist_ok=True)
    persistence = FilePersistenceWithDataProtection(
        str(path), entropy=f"Instruct IQ:{TENANT}:{app['clientId']}",
    )
    if not persistence.is_encrypted:
        raise SeedError("encrypted_persistence_required")
    # MSAL's normal OIDC offline_access permits encrypted refresh-token reuse.
    # No additional Graph workload permission or plaintext serialization is used.
    return msal.PublicClientApplication(
        app["clientId"], authority=f"https://login.microsoftonline.com/{TENANT}",
        token_cache=PersistedTokenCache(persistence),
    )


def cached_result(application: Any, app: dict[str, Any]) -> dict[str, Any] | None:
    accounts = application.get_accounts()
    matches = [account for account in accounts
               if account.get("local_account_id") == OPERATOR and account.get("realm") == TENANT]
    if len(matches) > 1 or (accounts and not matches):
        raise SeedError("dedicated_cache_operator_mismatch")
    if not matches:
        return None
    result = application.acquire_token_silent_with_error(
        ["https://graph.microsoft.com/" + scope for scope in READ_SCOPES], account=matches[0],
    )
    if result and result.get("access_token"):
        claims_verified(result, app)
        return result
    if result and result.get("error") in {"access_denied", "unauthorized_client"}:
        raise SeedError("cached_authorization_denied_no_interactive_fallback")
    return None


def verify(graph: ReadOnlyGraph, candidate: dict[str, Any], app: dict[str, Any],
           *, manifest_path: Path = MANIFEST) -> dict[str, Any]:
    validate_candidates(candidate)
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("pending"):
            raise SeedError("existing_native_pending_requires_reconciliation")
    print(json.dumps({"status": "manual_read_progress", "stage": "operator_profile"}), flush=True)
    if graph.request("GET", "/me?$select=id").get("id") != OPERATOR:
        raise SeedError("manual_verifier_actual_operator_mismatch")
    if candidate["selfChatId"] == "48:notes":
        # AMC's proven notes-message route is per signed-in user, not an ordinary
        # chat resource with a supported /members metadata route.
        print(json.dumps({"status": "manual_read_progress", "stage": "signed_in_notes_alias"}), flush=True)
    else:
        print(json.dumps({"status": "manual_read_progress", "stage": "exact_chat_membership"}), flush=True)
        members = graph.request("GET", f"/chats/{candidate['selfChatId']}/members").get("value", [])
        if (
            len(members) != 1 or members[0].get("userId") != OPERATOR
            or members[0].get("tenantId") != TENANT
        ):
            raise SeedError("manual_verifier_self_chat_ownership_unverified")
    verified = []
    for source in candidate["sources"]:
        print(json.dumps({"status": "manual_read_progress", "stage": source["key"]}), flush=True)
        row = graph.request("GET", source["path"])
        parser = Text()
        parser.feed(row.get("body", {}).get("content", ""))
        text = html.unescape(" ".join(parser.parts))
        if (
            row.get("id") != source["id"]
            or row.get("from", {}).get("user", {}).get("id") != OPERATOR
            or MARKER.casefold() not in text.casefold()
            or not re.search(r"(?<![\w-])" + re.escape(CLASS_ID) + r"(?![\w-])", text)
            or not re.search(r"\b" + source["key"] + r"\b", text, re.IGNORECASE)
        ):
            raise SeedError("manual_message_identity_author_or_labels_unverified")
        timestamp = row.get("createdDateTime")
        try:
            if not isinstance(timestamp, str) or datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError()
        except ValueError:
            raise SeedError("manual_native_creation_timestamp_unverified") from None
        native_url = row.get("webUrl")
        if native_url:
            url_identity(native_url, chat_id=candidate["selfChatId"],
                         message_id=source["id"], require_context=False)
        verified.append({
            "key": source["key"], "id": source["id"], "path": source["path"],
            "url": source["url"], "createdDateTime": timestamp, "contentVerified": True,
            **({"nativeWebUrl": native_url} if native_url else {}),
        })
    manifest = {
        "schemaVersion": 1, "status": "native_seed_verified",
        "origin": "user_created_teams_self_chat", "transport": "microsoft_graph",
        "tenantId": TENANT, "ownerId": OPERATOR, "classId": CLASS_ID,
        "marker": MARKER, "selfChatId": candidate["selfChatId"],
        "sources": verified, "pending": None, "nativeWritesByAssistant": 0,
        "verificationClientId": app["clientId"], "verificationMode": "read_only_exact_three",
    }
    # Commit verification metadata only after all three native reads pass.
    save(manifest, manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silent-only", action="store_true",
                        help="Use only the dedicated DPAPI cache; never initiate device sign-in")
    args = parser.parse_args()
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    validate_candidates(candidate)
    existing = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    if existing.get("pending"):
        raise SystemExit("Existing pending mutation: no new sign-in")
    app = json.loads(APP_MANIFEST.read_text(encoding="utf-8"))
    if app.get("status") != "provisioned_operator_only_delegated" or app.get("pending"):
        raise SystemExit("Dedicated app not verified: no sign-in")
    try:
        application = cached_application(app)
        result = cached_result(application, app)
        if result is None:
            if args.silent_only:
                print(json.dumps({"status": "not_ready", "reason": "dedicated_cached_signin_required"}), flush=True)
                return 1
            flow = application.initiate_device_flow(scopes=[
                "https://graph.microsoft.com/" + scope for scope in READ_SCOPES
            ])
            if not flow.get("device_code") or flow.get("verification_uri") not in {
                "https://login.microsoft.com/device", "https://microsoft.com/devicelogin",
            }:
                print(json.dumps({"status": "not_ready", "reason": "readonly_device_flow_not_accepted",
                                  "errorCodes": flow.get("error_codes", [])}), flush=True)
                return 1
            print(json.dumps({
                "status": "waiting_for_readonly_manual_verification_signin",
                "verificationUri": flow["verification_uri"], "userCode": flow["user_code"],
                "expiresIn": flow.get("expires_in"), "tenantId": TENANT, "operatorId": OPERATOR,
                "clientId": app["clientId"], "requestedScopes": READ_SCOPES,
                "mode": "read_only_exact_three_messages_no_seeding",
                "cache": "dedicated_windows_dpapi_encrypted",
            }), flush=True)
            result = application.acquire_token_by_device_flow(flow)
        claims_verified(result, app)
    except SeedError as error:
        print(json.dumps({"status": "not_ready", "reason": str(error)}), flush=True)
        return 1
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        graph = ReadOnlyGraph(result["access_token"], candidate, client)
        deadline = time.monotonic() + 600
        previous = json.loads(APP_MANIFEST.read_text(encoding="utf-8")).get("authControl", {}).get("requestId")
        seen = {previous}
        while True:
            try:
                manifest = verify(graph, candidate, app, manifest_path=MANIFEST)
                print(json.dumps({"status": manifest["status"], "sources": manifest["sources"],
                                  "nativeWritesByAssistant": 0, "workiqRetrievalVerified": False}), flush=True)
                return 0
            except SeedError as error:
                code = str(error)
            except Exception as error:
                code = "manual_read_exception_" + type(error).__name__
            print(json.dumps({"status": "not_ready", "reason": code}), flush=True)
            if "http_401" in code or "http_403" in code:
                return 1
            print(json.dumps({"status": "readonly_credentials_retained_in_memory",
                              "maximumSeconds": 600, "automaticRetry": False,
                              "control": "workiq-graph-app.json authControl: unique requestId; "
                                         "resume-manual-verification or close"}), flush=True)
            while time.monotonic() < deadline:
                time.sleep(1)
                control = json.loads(APP_MANIFEST.read_text(encoding="utf-8")).get("authControl", {})
                request_id = control.get("requestId")
                if not request_id or request_id in seen:
                    continue
                seen.add(request_id)
                if control.get("command") == "close":
                    return 1
                if control.get("command") == "resume-manual-verification":
                    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
                    validate_candidates(candidate)
                    graph = ReadOnlyGraph(result["access_token"], candidate, client)
                    break
            else:
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
