import importlib.util
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.instruct_workiq import DelegatedSession, TENANT_ID, WorkContextError

spec = importlib.util.spec_from_file_location("instruct_workiq_seed", Path(__file__).with_name("workiq_seed.py"))
seed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_module)
OWNER = seed_module.OWNER_ID


@pytest.fixture
def scratch():
    path = seed_module.ROOT / ".local" / "instruct-iq-seed-tests" / uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path)


class Native:
    def __init__(self):
        self.rows = {}
        self.writes = []
        self.members = [{"userId": OWNER, "tenantId": TENANT_ID}]
        self.error = False

    async def call(self, name, arguments):
        if name == "get_schema":
            return {"type": "object", "properties": {
                k: {} for k in ("body", "subject", "sensitivity", "attendees", "start", "end")
            }}
        if name == "create_entity":
            self.writes.append(arguments)
            if self.error:
                raise RuntimeError("secret-upstream-token")
            identifier = str(len(self.writes))
            row = {
                "id": identifier, **arguments["jsonBody"],
                "createdDateTime": "2026-10-15T21:00:00Z",
                "webUrl": f"https://teams.microsoft.com/l/message/{identifier}",
            }
            self.rows[arguments["parentUrl"] + "/" + identifier] = row
            return row
        path = arguments["entityUrls"][0].split("?")[0]
        if path == "/me":
            row = {"id": OWNER}
        elif path == "/chats/self-chat":
            row = {"id": "self-chat", "chatType": "oneOnOne", "members": self.members}
        else:
            row = self.rows[path]
        return {"results": [{"statusCode": 200, "data": row}]}


@pytest.mark.asyncio
async def test_native_seed_idempotency_private_ownership_and_actual_dates(scratch):
    native = Native()
    session = DelegatedSession(TENANT_ID, OWNER, native.call)
    path = scratch / "workiq.json"
    first = await seed_module.seed(
        session, self_chat_id="self-chat", manifest_path=path,
        now=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    again = await seed_module.seed(session, self_chat_id="self-chat", manifest_path=path)
    assert first == again
    assert len(native.writes) == 4
    assert all(s["id"] and s["url"] for s in first["sources"])
    assert first["scenarioDate"] != first["sources"][0]["createdDateTime"][:10]
    event = native.writes[-1]["jsonBody"]
    assert event["attendees"] == [] and event["sensitivity"] == "private"
    assert event["start"]["dateTime"] > "2026-10-15"
    assert "secret" not in path.read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong", ["tenant", "members"])
async def test_wrong_tenant_or_shared_target_never_writes(scratch, wrong):
    native = Native()
    if wrong == "members":
        native.members.append({"userId": "colleague", "tenantId": TENANT_ID})
    session = DelegatedSession("wrong" if wrong == "tenant" else TENANT_ID, OWNER, native.call)
    with pytest.raises(WorkContextError):
        await seed_module.seed(session, self_chat_id="self-chat", manifest_path=scratch / "workiq.json")
    assert native.writes == []


@pytest.mark.asyncio
async def test_ambiguous_or_denied_write_is_not_retried_and_redacts(scratch):
    native = Native()
    native.error = True
    session = DelegatedSession(TENANT_ID, OWNER, native.call)
    path = scratch / "workiq.json"
    with pytest.raises(WorkContextError, match="seed_write_unconfirmed_no_retry") as error:
        await seed_module.seed(session, self_chat_id="self-chat", manifest_path=path)
    assert "secret-upstream" not in str(error.value)
    with pytest.raises(WorkContextError, match="indeterminate"):
        await seed_module.seed(session, self_chat_id="self-chat", manifest_path=path)
    assert len(native.writes) == 1
    assert json.loads(path.read_text())["pending"]["key"] == "discussion"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [
    "blocked_wrong_mcp_account_no_writes_attempted",
    "demo_profile_verified_session_closed_no_writes",
])
async def test_preflight_checkpoint_can_resume_after_real_owner_verification(scratch, status):
    native = Native()
    path = scratch / "workiq.json"
    path.write_text(json.dumps({
        "status": status,
        "tenantId": TENANT_ID, "ownerId": OWNER, "classId": seed_module.CLASS_ID,
        "sources": [], "pending": None,
    }))
    result = await seed_module.seed(
        DelegatedSession(TENANT_ID, OWNER, native.call),
        self_chat_id="self-chat", manifest_path=path,
    )
    assert result["status"] == "native_seed_verified"
    assert len(native.writes) == 4


@pytest.mark.asyncio
async def test_unconfirmed_create_schema_never_writes(scratch):
    native = Native()

    async def call(name, arguments):
        if name == "get_schema":
            return {"type": "object", "properties": {"unknownField": {}}}
        return await native.call(name, arguments)

    with pytest.raises(WorkContextError, match="schema_requires_review"):
        await seed_module.seed(
            DelegatedSession(TENANT_ID, OWNER, call),
            self_chat_id="self-chat", manifest_path=scratch / "workiq.json",
        )
    assert native.writes == []
