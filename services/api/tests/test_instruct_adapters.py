"""Exact native response boundaries; instructional test data is never runtime input."""
import copy
import json

import pytest

from app.config import Settings
from app.instruct_adapters import NativeTransports
from app.instruct_contracts import ClassGrantV1, PlanRequestV1
from app.instruct_runtime import InstructRuntime
from app.instruct_sources import ConnectedSources
from app.schemas import Source
from test_instruct_data import generator


MODEL = "11111111-2222-3333-4444-555555555555"


@pytest.mark.asyncio
async def test_native_identity_async_transport_dependencies_are_installed():
    from azure.core.pipeline.transport import AioHttpTransport

    async with AioHttpTransport() as transport:
        assert transport.session is not None


def test_actual_publisher_projection_drives_complete_policy_without_fixture_citations(monkeypatch):
    from datetime import datetime, timezone
    from pathlib import Path
    from app.instruct_adapters import normalize
    from app.instruct_policy import build_plan
    from app.instruct_sources import empty_batch, validate_batch
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "agent" / "provisioning" / "instruct"))
    from publish import snapshots

    request, grant, runtime, _, _, _ = boundary()
    approver = "11111111-2222-3333-4444-555555555555"
    config = {"tenantId": grant.principal.tenantId, "workspaceId": "new-workspace",
              "lakehouseId": "new-lakehouse", "syntheticApproverId": approver}
    published = snapshots(generator.generate(), config, "https://instruction.search.windows.net")
    batches = []
    for context in runtime.contexts(request, grant):
        if context.source.value not in published:
            batches.append(empty_batch(context, "not_requested", None))
            continue
        raw = json.dumps(published[context.source.value])
        batches.append(validate_batch(context, normalize(
            raw, context, "verified-native-store", [approver],
        )))
    result = build_plan(request, grant.principal, batches, plan_id="published-projection",
                        request_id="published-projection", generated_at=datetime.now(timezone.utc))
    assert result.status == "complete"
    assert sorted(
        len(b.facts) for b in batches if b.source in {Source.FOUNDRY, Source.FABRIC}
    ) == [6, 70]
    assert all(e.provenance.mode == "connected" for b in batches for e in b.evidence)
    assert all(e.locator.startswith(("https://instruction.search.windows.net/", "fabric://new-workspace/"))
               for b in batches for e in b.evidence)
    foundry = published["foundry"]["records"]
    assert next(r for r in foundry if r["recordId"] == "schedule-amended")["fact"]["minutes"] == 35
    assert len([r for r in foundry if r["fact"]["kind"] == "support"]) == 2


def boundary():
    registry = generator.generate()
    request = PlanRequestV1.model_validate_json(json.dumps({
        "schemaVersion": "instruct.request.v1",
        "classId": registry["class"]["classId"],
        "assessmentId": registry["class"]["assessmentId"],
        "scenario": registry["scenario"], "includeWork": False, "includeWeb": False,
    }))
    grant = ClassGrantV1.model_validate_json(json.dumps({
        "grantId": "grant-1", "principal": registry["teacher"],
        "classId": request.classId, "checkedAt": "2026-10-15T12:00:00Z",
        "membershipRevision": "membership-1",
    }))
    snapshots = {}
    for batch in registry["sources"]:
        if batch["source"] not in {Source.FABRIC.value, Source.FOUNDRY.value}:
            continue
        records = []
        for original in batch["facts"]:
            fact = {k: v for k, v in original.items() if k != "evidenceRefs"}
            approval = None if batch["source"] == Source.FABRIC.value else {
                "approvalId": fact["approvalId"], "approvedBy": "district-authority",
                "approvedAt": fact["effectiveFrom"], "status": "approved",
            }
            records.append({
                "recordId": fact["factId"], "revision": "native-row-v2",
                "locator": f"record:{fact['factId']}", "title": f"Native {fact['kind']}",
                "fact": fact, "approval": approval,
            })
        snapshots[batch["source"]] = {
            "schemaVersion": "instruct.native-snapshot.v1",
            "tenantId": grant.principal.tenantId, "classId": request.classId,
            "assessmentId": request.assessmentId,
            "planningCutoff": request.scenario.planningCutoff.isoformat(),
            "revision": "snapshot-v7", "recordCount": len(records), "records": records,
            "completeKinds": (["roster", "assessment", "observation"]
                              if batch["source"] == Source.FABRIC.value
                              else ["curriculum", "support", "schedule", "resource"]),
        }
    settings = Settings(
        _env_file=None, APP_ENVIRONMENT="test",
        INSTRUCT_FABRIC_SEMANTIC_MODEL_ID=MODEL,
        INSTRUCT_SEARCH_ENDPOINT="https://instruction.search.windows.net",
        INSTRUCT_FOUNDRY_KB_NAME="instruction-kb",
        INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE="approved-snapshots",
        INSTRUCT_SEARCH_API_VERSION="2026-08-01-preview",
        INSTRUCT_APPROVER_IDS_JSON='["district-authority"]',
    )
    calls = []

    async def get(url, scope, timeout):
        calls.append(("GET", url, scope, None))
        return {"knowledgeSources": [{"name": "approved-snapshots",
                                     "enableImageServing": None, "enableFreshness": None}]}

    async def post(url, scope, body, timeout):
        calls.append(("POST", url, scope, body))
        if "executeQueries" in url:
            snapshot = snapshots[Source.FABRIC.value]
            return {"results": [{"tables": [{"rows": [
                {"[Snapshot]": json.dumps({**snapshot, "records": [record]})}
                for record in snapshot["records"]
            ]}]}]}
        return {
            "response": [{"content": [{"type": "text", "text": "DO NOT USE THIS ANSWER"}]}],
            "activity": [{"id": 2, "type": "searchIndex", "count": 1,
                          "knowledgeSourceName": "approved-snapshots"}],
            "references": [{"type": "searchIndex", "activitySource": 2,
                            "docKey": "authorized-snapshot",
                            "sourceData": {"snapshot": json.dumps(snapshots[Source.FOUNDRY.value])}}],
        }

    transports = NativeTransports(settings, post=post, get=get)
    runtime = InstructRuntime(settings, ConnectedSources(settings, transports))
    return request, grant, runtime, snapshots, calls, transports


async def test_exact_responses_drive_policy_and_native_evidence():
    request, grant, runtime, snapshots, calls, _ = boundary()
    before = (await runtime.execute(request, grant, "native-request")).result
    assert before.status == "complete"
    fabric_call = next(c for c in calls if "executeQueries" in c[1])
    assert fabric_call[1] == f"https://api.powerbi.com/v1.0/myorg/datasets/{MODEL}/executeQueries"
    dax = fabric_call[3]["queries"][0]["query"]
    assert all(s in dax for s in (grant.principal.tenantId, request.classId,
                                  request.assessmentId, request.scenario.planningCutoff.isoformat()))
    search_call = next(c for c in calls if "/retrieve?" in c[1])
    assert "/knowledgebases('instruction-kb')/retrieve?" in search_call[1]
    params = search_call[3]["knowledgeSourceParams"][0]
    assert search_call[3]["outputMode"] == "extractiveData"
    assert params["includeReferenceSourceData"] and params["failOnError"]
    assert request.classId in params["filterAddOn"] and grant.principal.tenantId in params["filterAddOn"]
    for batch in before.sources:
        for evidence in batch.evidence:
            assert evidence.provenance.nativeRevision == "snapshot-v7/native-row-v2"
            assert evidence.locator.startswith("record:")
            assert "DO NOT USE" not in evidence.excerpt
    for record in snapshots[Source.FABRIC.value]["records"]:
        if record["fact"].get("studentId") == "student-01":
            record["fact"]["outcome"] = "correct"
    for record in snapshots[Source.FOUNDRY.value]["records"]:
        if record["fact"]["kind"] == "curriculum":
            record["fact"]["objective"] = "A newly approved native objective"
    after = (await runtime.execute(request, grant, "native-mutation")).result
    group = lambda result: next(g.need for g in result.groups if "student-01" in g.studentIds)
    assert group(before) == "graph_interpretation" and group(after) == "extension"
    assert after.package.objective.text == "A newly approved native objective"


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(classId="unauthorized"),
    lambda s: s.update(tenantId="another-tenant"),
    lambda s: s.update(assessmentId="another-assessment"),
    lambda s: s.update(planningCutoff="2026-10-18T07:00:00-04:00"),
    lambda s: s.update(recordCount=s["recordCount"] + 1),
    lambda s: s.update(completeKinds=["curriculum"]),
    lambda s: s["records"][0].update(revision=""),
    lambda s: s["records"][0].update(locator=""),
    lambda s: s["records"][0]["approval"].update(approvedBy="untrusted"),
    lambda s: s["records"][0]["approval"].update(status="draft"),
    lambda s: s["records"][0]["approval"].update(approvalId="unbound"),
    lambda s: s["records"][0]["approval"].update(approvedAt="2099-01-01T00:00:00Z"),
    lambda s: s["records"][0]["fact"].update(evidenceRefs=["fabricated"]),
])
async def test_native_scope_approval_revision_and_completeness_fail_closed(mutation):
    request, grant, runtime, snapshots, *_ = boundary()
    mutation(snapshots[Source.FOUNDRY.value])
    result = (await runtime.execute(request, grant, "invalid-native")).result
    foundry = next(b for b in result.sources if b.source == Source.FOUNDRY)
    assert foundry.state == "failed" and not foundry.facts and not foundry.evidence
    assert result.package is None


@pytest.mark.parametrize("source", [Source.FABRIC, Source.FOUNDRY])
@pytest.mark.parametrize("failure", ["partial", "narrative", "wrong-source", "duplicate", "http"])
async def test_transport_errors_never_become_success_shaped_records(source, failure):
    request, grant, runtime, _, _, transports = boundary()
    original = transports.post

    async def broken(url, scope, body, timeout):
        if ("executeQueries" in url) != (source == Source.FABRIC):
            return await original(url, scope, body, timeout)
        if failure == "http":
            raise RuntimeError("credential and private response must not escape")
        payload = copy.deepcopy(await original(url, scope, body, timeout))
        if failure == "narrative":
            return {"response": [{"content": [{"text": "answer without records"}]}]}
        if source == Source.FABRIC:
            if failure == "partial":
                payload["results"][0]["error"] = {"code": "TooManyRows"}
            elif failure == "duplicate":
                payload["results"][0]["tables"][0]["rows"] *= 2
            else:
                payload["results"][0]["tables"][0]["rows"][0] = {"Wrong[Snapshot]": "{}"}
        elif failure == "partial":
            payload["activity"][0]["error"] = {"code": "Partial"}
        elif failure == "duplicate":
            payload["references"] *= 2
        else:
            payload["activity"][0]["knowledgeSourceName"] = "wrong"
        return payload

    transports.post = broken
    result = (await runtime.execute(request, grant, "broken-transport")).result
    batch = next(b for b in result.sources if b.source == source)
    assert batch.state == "failed" and not batch.evidence and not batch.facts
    assert "credential" not in batch.reason


async def test_capability_discovery_rejects_unscoped_knowledge_base():
    request, grant, runtime, _, calls, transports = boundary()

    async def wrong(*args):
        return {"knowledgeSources": [{"name": "approved-snapshots"}, {"name": "other"}]}

    transports.get = wrong
    result = (await runtime.execute(request, grant, "discovery")).result
    assert next(b for b in result.sources if b.source == Source.FOUNDRY).state == "unavailable"
    assert not any("/retrieve?" in call[1] for call in calls)


@pytest.mark.parametrize("mixed", [False, True])
async def test_fabric_silent_truncation_and_mixed_revisions_are_rejected(mixed):
    request, grant, runtime, _, _, transports = boundary()
    original = transports.post

    async def changed(url, *args):
        payload = await original(url, *args)
        if "executeQueries" in url:
            rows = payload["results"][0]["tables"][0]["rows"]
            if mixed:
                fragment = json.loads(rows[-1]["[Snapshot]"])
                fragment["revision"] = "concurrent-new-revision"
                rows[-1]["[Snapshot]"] = json.dumps(fragment)
            else:
                rows.pop()
        return payload

    transports.post = changed
    result = (await runtime.execute(request, grant, "truncated")).result
    assert next(b for b in result.sources if b.source == Source.FABRIC).state == "failed"
    assert not result.groups


@pytest.mark.parametrize("status", [200, 206, 401, 403, 429, 500])
async def test_native_http_auth_status_and_no_redirects(monkeypatch, status):
    from types import SimpleNamespace

    import azure.identity.aio
    import httpx

    from app import instruct_adapters

    seen = []

    class Credential:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_token(self, scope):
            assert scope == "https://search.azure.com/.default"
            return SimpleNamespace(token="test-only-token")

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json={"references": []})

    client = httpx.AsyncClient

    def create(**kwargs):
        assert kwargs["follow_redirects"] is False
        return client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(azure.identity.aio, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(instruct_adapters.httpx, "AsyncClient", create)
    args = ("https://instruction.search.windows.net", "https://search.azure.com/.default",
            {"intents": []}, 1)
    if status == 200:
        assert await instruct_adapters._post(*args) == {"references": []}
    else:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            await instruct_adapters._post(*args)
    assert seen[0].headers["Authorization"] == "Bearer test-only-token"
    assert json.loads(seen[0].content) == {"intents": []}
