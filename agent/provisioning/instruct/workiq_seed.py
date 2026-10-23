"""Small, private, native WorkIQ seeder. Import-safe; no CLI/legacy identity fallback."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import Settings
from app.instruct_workiq import (
    MARKER, TENANT_ID, DelegatedSession, WorkContextError, fetched, source_url,
    tool_data, verify_owner, invoke,
)

OWNER_ID = Settings().INSTRUCT_WORKIQ_OPERATOR_ID
CLASS_ID = "class-science-7a"
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "data" / "instruct" / "work" / "evidence.json"
MANIFEST = ROOT / ".local" / "instruct-iq-deployment" / "workiq.json"


def checkpoint(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


async def seed(
    session: DelegatedSession, *, self_chat_id: str, manifest_path: Path = MANIFEST,
    now: datetime | None = None, progress: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    progress("seed_owner_read")
    await verify_owner(session, OWNER_ID)
    if not self_chat_id or any(c in self_chat_id for c in "/?#"):
        raise WorkContextError("explicit_self_chat_required")
    progress("seed_self_chat_ownership_read")
    chat, = fetched(await invoke(session, "fetch", {
        "entityUrls": [f"/chats/{self_chat_id}?$expand=members"],
    }))
    members = chat.get("members", [])
    if (
        chat.get("id") != self_chat_id or chat.get("chatType") != "oneOnOne"
        or len(members) != 1 or members[0].get("userId") != OWNER_ID
        or members[0].get("tenantId") != TENANT_ID
    ):
        raise WorkContextError("self_chat_ownership_unverified")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    manifest = {
        "schemaVersion": 1, "tenantId": TENANT_ID, "ownerId": OWNER_ID,
        "classId": CLASS_ID, "marker": MARKER, "selfChatId": self_chat_id,
        "fixtureHash": fingerprint, "scenarioDate": fixture["scenarioDate"],
        "sources": [], "pending": None,
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        # A read-only preflight checkpoint contains no native identity to resume.
        preflight = (
            existing.get("status") in {
                "blocked_wrong_mcp_account_no_writes_attempted",
                "demo_profile_verified_session_closed_no_writes",
            }
            and existing.get("sources") == [] and existing.get("pending") is None
            and existing.get("tenantId") == TENANT_ID
            and existing.get("ownerId") == OWNER_ID
            and existing.get("classId") == CLASS_ID
        )
        if not preflight:
            manifest = existing
        if any(manifest.get(k) != v for k, v in (
            ("tenantId", TENANT_ID), ("ownerId", OWNER_ID), ("classId", CLASS_ID),
            ("selfChatId", self_chat_id), ("fixtureHash", fingerprint),
        )):
            raise WorkContextError("seed_manifest_mismatch")
        if manifest.get("pending"):
            raise WorkContextError("seed_outcome_indeterminate_reconcile_exact_target")
    keys = [s.get("key") for s in manifest["sources"]]
    if len(keys) != len(set(keys)) or any(k not in (
        "discussion", "recap", "resource", "agenda") for k in keys):
        raise WorkContextError("seed_manifest_mismatch")
    for source in manifest["sources"]:
        progress("existing_native_source_read")
        expected = (f"/me/events/{source['id']}" if source["key"] == "agenda"
                    else f"/chats/{self_chat_id}/messages/{source['id']}")
        if source.get("path") != expected:
            raise WorkContextError("seed_manifest_mismatch")
        row, = fetched(await invoke(session, "fetch", {
            "entityUrls": [expected + "?$select=id,body,createdDateTime"],
        }))
        if row.get("id") != source["id"] or MARKER not in row.get("body", {}).get("content", ""):
            raise WorkContextError("seed_existing_source_mismatch")
    for key in ("discussion", "recap", "resource", "agenda"):
        if key in keys:
            continue
        parent = "/me/events" if key == "agenda" else f"/chats/{self_chat_id}/messages"
        # Discover the create contract on this authenticated tenant before writing.
        progress("schema_" + key)
        schema = tool_data(await invoke(session, "get_schema", {
            "path": parent, "operationType": "create", "format": "jsonschema",
        }))
        if not schema:
            raise WorkContextError("seed_schema_unavailable")
        payload: dict[str, Any] = {
            "body": {"contentType": "text", "content": fixture[key]},
        }
        if key == "agenda":
            start = (now or datetime.now(timezone.utc)) + timedelta(days=7)
            start = start.replace(hour=15, minute=0, second=0, microsecond=0)
            payload.update(
                subject=f"{MARKER} — proposed science-team planning agenda",
                sensitivity="private", attendees=[],
                start={"dateTime": start.isoformat(), "timeZone": "UTC"},
                end={"dateTime": (start + timedelta(minutes=30)).isoformat(), "timeZone": "UTC"},
            )
        # Unknown wrappers/references require operator review, not guessed fields.
        properties = schema.get("properties", {})
        if (not isinstance(properties, dict) or not set(payload) <= set(properties)
                or not set(schema.get("required", [])) <= set(payload)):
            raise WorkContextError("seed_schema_requires_review")
        # A crash/timeout after a POST must never cause a blind duplicate on rerun.
        manifest["pending"] = {"key": key, "parent": parent}
        checkpoint(manifest, manifest_path)
        progress("native_write_" + key)
        try:
            created = tool_data(await invoke(session, "create_entity", {
                "parentUrl": parent, "jsonBody": payload,
            }))
        except WorkContextError as exc:
            if any(code in str(exc) for code in ("access_denied", "http_401", "http_403")):
                raise
            raise WorkContextError("seed_write_unconfirmed_no_retry") from None
        except Exception:
            raise WorkContextError("seed_write_unconfirmed_no_retry") from None
        identifier = created.get("id")
        if not identifier or any(c in identifier for c in "/?#"):
            raise WorkContextError("seed_write_unconfirmed_no_retry")
        path = f"{parent}/{identifier}"
        # Save exact native identity even if source-link/verification is unavailable.
        manifest["pending"]["id"] = identifier
        checkpoint(manifest, manifest_path)
        link_field = "webLink" if key == "agenda" else "webUrl"
        progress("native_readback_" + key)
        row, = fetched(await invoke(session, "fetch", {
            "entityUrls": [path + f"?$select=id,body,{link_field},createdDateTime"],
        }))
        url = row.get("webUrl") or row.get("webLink")
        if (row.get("id") != identifier or not source_url(url)
                or not row.get("createdDateTime")
                or MARKER not in row.get("body", {}).get("content", "")):
            raise WorkContextError("seed_verification_incomplete_no_retry")
        manifest["sources"].append({
            "key": key, "id": identifier, "path": path, "url": url,
            "createdDateTime": row["createdDateTime"],
        })
        manifest["pending"] = None
        manifest["status"] = "native_seed_partial"
        checkpoint(manifest, manifest_path)
    manifest["status"] = "native_seed_verified"
    checkpoint(manifest, manifest_path)
    return manifest


if __name__ == "__main__":
    raise SystemExit(
        "No writes attempted. Supply an authenticated WorkIQ session for tenant "
        f"{TENANT_ID}, operator {OWNER_ID}, and an exact verified self-chat ID "
        "to seed(). The current terminal/MCP account is not reused."
    )
