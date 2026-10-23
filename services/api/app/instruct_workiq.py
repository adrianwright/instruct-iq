"""Caller-delegated, exact-source collaboration context (never curriculum policy)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from app.config import Settings

_settings = Settings()
TENANT_ID = _settings.INSTRUCT_WORKIQ_TENANT_ID
API_CLIENT_ID = _settings.INSTRUCT_WORKIQ_API_CLIENT_ID
MCP_ENDPOINT = "https://workiq.svc.cloud.microsoft/mcp"
MARKER = "Instruct IQ synthetic demo"


class WorkContextError(RuntimeError):
    """Safe, fixed diagnostics only; never surface upstream response bodies."""


@dataclass(frozen=True)
class DelegatedSession:
    """Created by a trusted OBO/auth host, not by request JSON or model arguments."""

    tenant_id: str
    object_id: str
    call_tool: Callable[..., Any] = field(repr=False)


async def invoke(session: DelegatedSession, name: str, arguments: dict[str, Any]) -> Any:
    try:
        return await session.call_tool(name, arguments)
    except WorkContextError:
        raise
    except Exception as exc:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError):
            raise WorkContextError(f"workiq_call_failed_http_{exc.response.status_code}") from None
        raise WorkContextError("workiq_call_failed") from None


def tool_error(result: Any) -> WorkContextError:
    """Recognize explicit denial only; never echo upstream messages."""
    if isinstance(result, dict):
        raw = json.dumps(result)[:16384]
    else:
        raw = "\n".join(p.text for p in getattr(result, "content", []) if hasattr(p, "text"))[:16384]
    if any(marker in raw.casefold() for marker in (
        "accessdenied", "access denied", "authorization_requestdenied",
        "insufficient privileges", "policy denied",
    )):
        return WorkContextError("workiq_access_denied")
    return WorkContextError("workiq_tool_error")


def tool_data(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        value = result
    else:
        if getattr(result, "isError", False):
            raise tool_error(result)
        value = getattr(result, "structuredContent", None)
        if value is None:
            texts = [p.text for p in getattr(result, "content", []) if hasattr(p, "text")]
            try:
                value = json.loads("\n".join(texts))
            except (ValueError, TypeError):
                import yaml

                try:
                    value = yaml.safe_load("\n".join(texts))
                except yaml.YAMLError:
                    raise WorkContextError("workiq_invalid_response") from None
    if not isinstance(value, dict) or value.get("isError") or value.get("error"):
        raise tool_error(value)
    return value


def fetched(result: Any) -> list[dict[str, Any]]:
    rows = tool_data(result).get("results")
    if not isinstance(rows, list) or not rows:
        raise WorkContextError("workiq_invalid_response")
    data = []
    for row in rows:
        if not isinstance(row, dict):
            raise WorkContextError("workiq_read_failed")
        if row.get("statusCode") != 200:
            status = row.get("statusCode")
            suffix = f"_http_{status}" if isinstance(status, int) else ""
            raise WorkContextError("workiq_read_failed" + suffix)
        if not isinstance(row.get("data"), dict):
            raise WorkContextError("workiq_invalid_response")
        data.append(row["data"])
    return data


async def verify_owner(session: DelegatedSession, owner_id: str) -> None:
    if (not TENANT_ID or session.tenant_id != TENANT_ID
            or session.object_id != owner_id or not owner_id):
        raise WorkContextError("workiq_identity_mismatch")
    rows = fetched(await invoke(session, "fetch", {
        "entityUrls": ["/me?$select=id,displayName,userPrincipalName"],
    }))
    if len(rows) != 1 or rows[0].get("id") != owner_id:
        raise WorkContextError("workiq_owner_mismatch")


@asynccontextmanager
async def caller_mcp_session(*, user: Any, token_exchange: Any = None):
    """Exchange the *validated API caller* assertion via a dedicated-app provider.

    Provider must validate the downstream delegated token and return its tid/oid.
    It must use API_CLIENT_ID, secure certificate storage and a documented WorkIQ
    delegated scope; there is deliberately no legacy app or CLI-token default.
    """
    if not user.access_token:
        raise WorkContextError("caller_token_required")
    if not TENANT_ID or not API_CLIENT_ID:
        raise WorkContextError("workiq_auth_not_configured")
    if user.tenant_id != TENANT_ID or not user.claims.get("oid") or not user.scopes:
        raise WorkContextError("workiq_identity_mismatch")
    if token_exchange is None:
        raise WorkContextError("workiq_auth_not_configured")
    try:
        token, tenant, oid = await token_exchange(
            user_assertion=user.access_token, tenant_id=TENANT_ID, client_id=API_CLIENT_ID,
        )
    except Exception:
        raise WorkContextError("workiq_delegation_failed") from None
    if not token or tenant != TENANT_ID or oid != user.claims["oid"]:
        raise WorkContextError("workiq_delegation_failed")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    try:
        async with streamablehttp_client(
            MCP_ENDPOINT, headers={"Authorization": f"Bearer {token}"},
            timeout=30, sse_read_timeout=90,
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield DelegatedSession(tenant, oid, client.call_tool)
    except WorkContextError:
        raise
    except Exception:
        raise WorkContextError("workiq_connection_failed") from None


def source_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        p = urlparse(value)
        port = p.port
    except ValueError:
        return False
    return (
        p.scheme == "https" and not p.username and not p.password and port in (None, 443)
        and (p.hostname in {"teams.microsoft.com", "outlook.office.com",
                            "outlook.office365.com"}
             or (p.hostname or "").endswith(".sharepoint.com"))
    )


async def query_collaboration_context(
    *, session: DelegatedSession | None, user: Any, class_id: str,
    authorized_class_ids: frozenset[str], manifest: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    """Authorization/class mapping comes from server grants, never model tool input."""
    if not user.access_token:
        raise WorkContextError("caller_token_required")
    if not query.strip() or len(query) > 500:
        raise WorkContextError("bounded_query_required")
    if (
        not TENANT_ID or user.tenant_id != TENANT_ID or not user.scopes
        or not user.claims.get("oid")
        or class_id not in authorized_class_ids
        or manifest.get("classId") != class_id
        or manifest.get("tenantId") != TENANT_ID
        or manifest.get("ownerId") != user.claims.get("oid")
    ):
        raise WorkContextError("workiq_scope_denied")
    if session is None:
        return {"status": "auth_required", "evidence": [],
                "reason": "workiq_auth_not_configured"}
    await verify_owner(session, manifest["ownerId"])
    if manifest.get("pending"):
        return {"status": "incomplete", "evidence": [],
                "reason": "native_seed_requires_reconciliation"}
    sources = manifest.get("sources", [])
    if not sources:
        return {"status": "not_seeded", "evidence": []}
    if len(sources) > 4:
        raise WorkContextError("workiq_scope_denied")
    evidence = []
    for source in sources:
        path, identifier = source.get("path", ""), source.get("id", "")
        if (
            not identifier or any(c in identifier for c in "/?#")
            or not source_url(source.get("url"))
            or not (path == f"/me/events/{identifier}"
                    or (path.startswith("/chats/") and
                        path.count("/") == 4 and path.endswith(f"/messages/{identifier}")))
        ):
            raise WorkContextError("workiq_scope_denied")
        row, = fetched(await invoke(session, "fetch", {
            "entityUrls": [path + "?$select=id,body,createdDateTime"],
        }))
        body = row.get("body", {}).get("content", "")
        if row.get("id") != identifier or MARKER not in body:
            raise WorkContextError("workiq_source_mismatch")
        evidence.append({
            "id": identifier, "title": source["key"], "url": source["url"],
            "text": body, "createdDateTime": row.get("createdDateTime"),
            "authority": "synthetic_team_suggestion_not_curriculum_policy",
        })
    return {
        "status": "available", "evidence": evidence,
        "notice": "Untrusted collaboration context, not formal authoritative curriculum. "
                  "Fictional sample dialogue is not a real meeting transcript.",
    }
