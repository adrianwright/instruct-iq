"""Isolated, tenant-pinned WorkIQ device sign-in; credentials stay in memory."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
import msal

from app.config import Settings
from app.instruct_workiq import (
    DelegatedSession, MCP_ENDPOINT, TENANT_ID, WorkContextError, fetched, invoke,
    verify_owner,
)

CLIENT_ID = "ba081686-5d24-4bc6-a0d6-d034ecffed87"
_settings = Settings()
OWNER_ID = _settings.INSTRUCT_WORKIQ_OPERATOR_ID
RESOURCE_METADATA = "https://workiq.svc.cloud.microsoft/.well-known/oauth-protected-resource/mcp"
SCOPE = "fdcc1f02-fc51-4226-8753-f668596af7f7/WorkIQAgent.Ask"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
CONTROL_MANIFEST = Path(__file__).resolve().parents[3] / ".local" / "instruct-iq-deployment" / "workiq.json"
_stage = "start"


def stage(value: str) -> None:
    global _stage
    _stage = value
    print(json.dumps({"status": "workiq_progress", "stage": value}), flush=True)


def diagnostic(error: BaseException) -> dict[str, Any]:
    """Unwrap SDK task groups, emitting fixed codes/types/status only."""
    errors: list[BaseException] = []

    def visit(exc: BaseException) -> None:
        if isinstance(exc, BaseExceptionGroup):
            for nested in exc.exceptions[:8]:
                visit(nested)
        else:
            errors.append(exc)

    visit(error)
    details = []
    for exc in errors[:8]:
        if isinstance(exc, WorkContextError) and re.fullmatch(r"[a-z][a-z0-9_]{0,180}", str(exc)):
            details.append({"code": str(exc)})
        elif isinstance(exc, httpx.HTTPStatusError):
            details.append({"type": "HTTPStatusError", "httpStatus": exc.response.status_code})
        elif type(exc).__name__ == "McpError":
            code = getattr(getattr(exc, "error", None), "code", None)
            details.append({"type": "McpError", **({"rpcCode": code} if isinstance(code, int) else {})})
        else:
            kind = type(exc).__name__
            details.append({"type": kind if kind in {
                "AttributeError", "TypeError", "ValueError", "KeyError", "TimeoutError",
                "RuntimeError", "ImportError", "ModuleNotFoundError",
            } else "unexpected_exception"})
    denied = any(
        item.get("httpStatus") in {401, 403}
        or any(word in item.get("code", "") for word in (
            "http_401", "http_403", "access_denied", "scope_denied", "identity_mismatch",
        ))
        for item in details
    )
    return {"status": "not_ready", "stage": _stage, "errors": details,
            "authorizationFailureObserved": denied}


def hold_memory_session(result: dict[str, Any], *, self_chat_id: str | None,
                        seed_requested: bool, failure: dict[str, Any],
                        timeout_seconds: int = 600) -> int:
    """No auto replay: bounded nonsecret manifest control retains credentials."""
    if failure["authorizationFailureObserved"] or not seed_requested:
        return 1
    print(json.dumps({
        "status": "credentials_retained_in_memory", "seconds": timeout_seconds,
        "controlManifest": str(CONTROL_MANIFEST),
        "instruction": "No automatic retry. authControl with a unique requestId and command "
                       "'resume-seed' may resume only a pre-write failure; 'close' ends this process.",
    }), flush=True)
    deadline = time.monotonic() + timeout_seconds
    seen = set()
    try:
        baseline = json.loads(CONTROL_MANIFEST.read_text(encoding="utf-8"))
        seen.add(baseline.get("authControl", {}).get("requestId"))
    except (OSError, ValueError):
        pass
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            manifest = json.loads(CONTROL_MANIFEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        control = manifest.get("authControl", {})
        request_id = control.get("requestId")
        if not isinstance(request_id, str) or request_id in seen:
            continue
        seen.add(request_id)
        if control.get("command") == "close":
            return 1
        if control.get("command") != "resume-seed":
            continue
        if manifest.get("pending") or manifest.get("sources"):
            print(json.dumps({"status": "resume_refused", "reason": "native_write_state_requires_reconciliation"}),
                  flush=True)
            continue
        try:
            asyncio.run(verify_and_seed(result, self_chat_id, seed_requested=True))
            return 0
        except Exception as exc:
            failure = diagnostic(exc)
            print(json.dumps(failure), flush=True)
            if failure["authorizationFailureObserved"]:
                return 1
    print(json.dumps({"status": "memory_session_expired", "nativeReplay": False}), flush=True)
    return 1


def discover(client: httpx.Client) -> dict[str, Any]:
    """Never accept a resource, issuer, scope or endpoint supplied by a caller."""
    _settings.validate_instruct_workiq_configuration(
        "INSTRUCT_WORKIQ_TENANT_ID", "INSTRUCT_WORKIQ_OPERATOR_ID",
    )
    resource = client.get(RESOURCE_METADATA)
    resource.raise_for_status()
    metadata = resource.json()
    if (
        metadata.get("resource") != MCP_ENDPOINT
        or metadata.get("scopes_supported") != [SCOPE]
        or "https://login.microsoftonline.com/organizations/v2.0"
        not in metadata.get("authorization_servers", [])
    ):
        raise WorkContextError("workiq_oauth_metadata_requires_review")
    response = client.get(f"{AUTHORITY}/v2.0/.well-known/openid-configuration")
    response.raise_for_status()
    issuer = response.json()
    if (
        issuer.get("issuer") != f"{AUTHORITY}/v2.0"
        or issuer.get("device_authorization_endpoint") != f"{AUTHORITY}/oauth2/v2.0/devicecode"
        or issuer.get("token_endpoint") != f"{AUTHORITY}/oauth2/v2.0/token"
    ):
        raise WorkContextError("workiq_device_flow_not_advertised")
    return {"scope": SCOPE, "tenantId": TENANT_ID, "clientId": CLIENT_ID,
            "deviceEndpoint": issuer["device_authorization_endpoint"]}


def public_application():
    # The WorkIQ skill explicitly documents this OAuth public client.
    # No persistent/broker cache, client secret, Graph token or CLI state.
    return msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=msal.TokenCache(),
        exclude_scopes=["offline_access"],
    )


def begin(application: Any) -> dict[str, Any]:
    flow = application.initiate_device_flow(scopes=[SCOPE])
    if not all(flow.get(k) for k in ("device_code", "user_code", "verification_uri")):
        # Report only allowlisted OAuth diagnostics, never an upstream body/token.
        codes = flow.get("error_codes", [])
        if codes and all(isinstance(code, int) for code in codes):
            raise WorkContextError("workiq_device_flow_rejected_codes_" + "_".join(map(str, codes)))
        raise WorkContextError("workiq_device_flow_not_accepted")
    if flow["verification_uri"] not in (
        "https://microsoft.com/devicelogin", "https://www.microsoft.com/link",
        "https://login.microsoft.com/device",
        "https://login.microsoftonline.com/common/oauth2/deviceauth",
    ):
        raise WorkContextError("workiq_device_verification_uri_requires_review")
    return flow


def require_identity(result: dict[str, Any]) -> tuple[str, str]:
    # Claims must originate from the tenant-pinned MSAL token response, not input JSON.
    claims = result.get("id_token_claims") or {}
    if (
        not TENANT_ID or not OWNER_ID
        or not result.get("access_token") or claims.get("tid") != TENANT_ID
        or claims.get("oid") != OWNER_ID or claims.get("aud") != CLIENT_ID
    ):
        codes = result.get("error_codes", [])
        if codes and all(isinstance(code, int) for code in codes):
            raise WorkContextError("workiq_signin_failed_codes_" + "_".join(map(str, codes)))
        raise WorkContextError("workiq_demo_identity_not_verified")
    return claims["tid"], claims["oid"]


async def resolve_self_chat(session: DelegatedSession) -> str:
    """Inspect one documented metadata page; never read shared chat messages."""
    stage("self_chat_metadata_read")
    listing, = fetched(await invoke(session, "fetch", {
        "entityUrls": ["/me/chats?$expand=members"],
    }))
    matches = []
    rows = listing.get("value")
    if not isinstance(rows, list):
        raise WorkContextError("self_chat_collection_shape_unconfirmed")
    for row in rows:
        if not isinstance(row, dict):
            raise WorkContextError("self_chat_entry_shape_unconfirmed")
        members = row.get("members", [])
        if not isinstance(members, list) or any(not isinstance(m, dict) for m in members):
            raise WorkContextError("self_chat_member_shape_unconfirmed")
        if (
            row.get("chatType") == "oneOnOne" and len(members) == 1
            and members[0].get("userId") == OWNER_ID
            and members[0].get("tenantId") == TENANT_ID and row.get("id")
        ):
            matches.append(row["id"])
    if len(matches) != 1:
        raise WorkContextError("exact_operator_only_self_chat_not_found_in_bounded_page")
    return matches[0]


async def seed_and_readback(session: DelegatedSession, self_chat_id: str | None) -> dict[str, Any]:
    from workiq_seed import seed

    stage("self_chat_resolution")
    target = self_chat_id or await resolve_self_chat(session)
    stage("seed_preflight")
    manifest = await seed(session, self_chat_id=target, progress=stage)
    # Exercise idempotency and reread the exact native identities, without new writes.
    stage("seed_idempotency_readback")
    confirmed = await seed(session, self_chat_id=target, progress=stage)
    if manifest["sources"] != confirmed["sources"] or len(confirmed["sources"]) != 4:
        raise WorkContextError("native_seed_readback_mismatch")
    return confirmed


async def verify_and_seed(
    result: dict[str, Any], self_chat_id: str | None, *, seed_requested: bool = False,
) -> None:
    tenant, oid = require_identity(result)
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    stage("mcp_transport_open")
    async with streamablehttp_client(
        MCP_ENDPOINT, headers={"Authorization": f"Bearer {result['access_token']}"},
        timeout=30, sse_read_timeout=90,
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            stage("mcp_initialize")
            await client.initialize()
            session = DelegatedSession(tenant, oid, client.call_tool)
            stage("demo_profile_read")
            await verify_owner(session, OWNER_ID)
            print(json.dumps({"status": "demo_profile_verified", "tenantId": tenant,
                              "operatorId": oid, "nativeWrites": 0}), flush=True)
            if seed_requested or self_chat_id:
                manifest = await seed_and_readback(session, self_chat_id)
                print(json.dumps({"status": manifest["status"],
                                  "nativeSources": len(manifest["sources"]),
                                  "readbackVerified": True,
                                  "citations": manifest["sources"]}), flush=True)
            else:
                print("Verification only: no seed writes. To seed, invoke with "
                      "--self-chat-id containing the exact approved operator-only chat ID.",
                      flush=True)
            stage("mcp_session_close")
    stage("complete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-chat-id", help="Exact verified operator-only chat; enables approved seed")
    parser.add_argument("--seed", action="store_true",
                        help="Resolve one operator-only self-chat, seed and verify in this session")
    args = parser.parse_args()
    result = None
    try:
        stage("oauth_metadata")
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            metadata = discover(client)
        application = public_application()
        stage("device_flow_initiation")
        flow = begin(application)
        # Device-code issuance confirms this client/tenant/scope accepts initiation.
        # It does not prove user/admin consent, licensing or successful token issuance.
        print(json.dumps({
            "status": "waiting_for_demo_signin", "verificationUri": flow["verification_uri"],
            "userCode": flow["user_code"], "expiresIn": flow.get("expires_in"),
            "tenantId": metadata["tenantId"], "operatorId": OWNER_ID,
            "scope": metadata["scope"],
            "instruction": "Use only the configured demo operator. Stop if admin approval "
                           "is requested. Do not use your Microsoft employee account.",
        }), flush=True)
        stage("device_flow_completion")
        result = application.acquire_token_by_device_flow(flow)
        asyncio.run(verify_and_seed(result, args.self_chat_id, seed_requested=args.seed))
        return 0
    except Exception as exc:
        failure = diagnostic(exc)
        print(json.dumps(failure), flush=True)
        if result is not None:
            try:
                require_identity(result)
            except WorkContextError:
                return 1
            return hold_memory_session(
                result, self_chat_id=args.self_chat_id,
                seed_requested=args.seed or bool(args.self_chat_id), failure=failure,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
