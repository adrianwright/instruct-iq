"""No live calls: JWT boundary plus frozen normalized-source/runtime tests."""
import asyncio
import copy
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth, instruct_routes
from app.auth import require_api_user
from app.config import Settings
from app.instruct_auth import authorize, principal
from app.auth import AuthenticatedUser
from app.instruct_contracts import PlanRequestV1, StreamTranscriptV1
from app.instruct_runtime import InstructRuntime, ReferenceIndex
from app.instruct_sources import ConnectedSources, validate_batch
from app.main import app
from app.schemas import Source
from test_auth import TENANT_ID, _token, _validator
from test_instruct_policy import generator, run


class FrozenSources:
    def __init__(self, registry=None):
        plan = run(registry)
        self.batches = {b.source: b.model_copy(deep=True) for b in plan.sources}
        for batch in self.batches.values():
            for evidence in batch.evidence:
                evidence.provenance.mode = "connected"
        self.calls = []

    async def retrieve(self, context):
        self.calls.append(context)
        return self.batches[context.source].model_copy(deep=True)


def test_instructional_principal_uses_verified_entra_object_id():
    user = AuthenticatedUser("", TENANT_ID, "pairwise-subject", frozenset(),
                             {"oid": "ba12c12b-23b2-5b85-a3fe-89361cf8a461"})
    assert principal(user).subject == user.claims["oid"]
    assert principal(user).tenantId == TENANT_ID


@pytest.fixture
def setup(monkeypatch):
    baseline = run()
    body = PlanRequestV1(
        schemaVersion="instruct.request.v1", classId=baseline.classId,
        assessmentId=baseline.assessmentId, scenario=baseline.scenario,
        includeWork=False, includeWeb=False,
    )
    member = {
        "principal": {"tenantId": TENANT_ID, "subject": "user-123"},
        "classroom": {"classId": body.classId, "title": "Authorized science",
                      "assessmentIds": [body.assessmentId], "studentCount": 24},
        "revision": "membership-1", "validFrom": "2020-01-01T00:00:00Z",
        "validTo": "2099-01-01T00:00:00Z",
    }
    settings = Settings(_env_file=None, APP_ENVIRONMENT="test",
                        INSTRUCT_CLASS_GRANTS_JSON=json.dumps([member]),
                        INSTRUCT_PROVIDER_TIMEOUT_SECONDS=0.1,
                        INSTRUCT_REQUEST_TIMEOUT_SECONDS=0.2)
    sources = FrozenSources()
    runtime = InstructRuntime(settings, sources)
    monkeypatch.setattr(instruct_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(instruct_routes, "get_instruct_runtime", lambda: runtime)
    monkeypatch.setattr(auth, "get_access_token_validator", _validator)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token()}"}
    return client, headers, body.model_dump(mode="json"), sources, runtime, settings, member


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def semantics(result):
    result = copy.deepcopy(result)
    for key in ("requestId", "planId", "generatedAt"):
        result.pop(key)
    return result


def test_real_auth_denial_is_not_masked_by_commercial_global_override(setup):
    client, _, body, sources, *_ = setup
    assert require_api_user in app.dependency_overrides
    for path in ("classes", "plan", "plan/stream"):
        response = (client.get(f"/api/instruct/v1/{path}") if path == "classes" else
                    client.post(f"/api/instruct/v1/{path}", json=body))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"
        assert "text/event-stream" not in response.headers.get("content-type", "")
    assert not sources.calls


@pytest.mark.parametrize("claims,status", [
    ({"sub": "other-user"}, 404), ({"scp": "wrong"}, 403), ({"aud": "wrong"}, 401),
])
def test_jwt_and_class_denials_precede_provider_and_sse(setup, claims, status):
    client, _, body, sources, *_ = setup
    response = client.post("/api/instruct/v1/plan/stream", json=body,
                           headers={"Authorization": f"Bearer {_token(**claims)}"})
    assert response.status_code == status
    assert "text/event-stream" not in response.headers["content-type"]
    assert "student" not in response.text and not sources.calls


def test_classes_and_scope_denial_before_retrieval(setup):
    client, headers, body, sources, *_ = setup
    assert client.get("/api/instruct/v1/classes", headers=headers).json()["classes"][0]["classId"] == body["classId"]
    for field in ("classId", "assessmentId"):
        response = client.post("/api/instruct/v1/plan", json={**body, field: "other"}, headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Resource not found."
    assert not sources.calls


def test_operator_oid_grant_is_not_pairwise_sub_or_cross_tenant(setup):
    *_, settings, member = setup
    object_id = "ba12c12b-23b2-5b85-a3fe-89361cf8a461"
    member["principal"]["subject"] = object_id
    settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([member])
    user = AuthenticatedUser("", TENANT_ID, "pairwise-subject", frozenset(), {"oid": object_id})
    grant = authorize(settings, user, member["classroom"]["classId"])
    assert grant.principal.subject == object_id
    other = AuthenticatedUser("", "other-tenant", "pairwise-subject", frozenset(), {"oid": object_id})
    with pytest.raises(HTTPException) as denied:
        authorize(settings, other, member["classroom"]["classId"])
    assert denied.value.status_code == 404


def test_frozen_snapshot_rest_sse_parity_and_claim_reference_resolution(setup):
    client, headers, body, sources, *_ = setup
    rest = client.post("/api/instruct/v1/plan", json=body, headers=headers)
    assert rest.status_code == 200, rest.text
    result = rest.json()["result"]
    assert result["status"] == "complete"
    streamed = client.post("/api/instruct/v1/plan/stream", json=body, headers=headers)
    transcript = StreamTranscriptV1.model_validate_json(json.dumps({"events": events(streamed)}))
    assert semantics(transcript.events[-1].payload.result.model_dump(mode="json")) == semantics(result)
    assert [c.source for c in sources.calls] == [Source.FOUNDRY, Source.FABRIC] * 2
    claim = result["package"]["objective"]
    ref_id = claim["evidenceRefs"][0]
    path = f"/api/instruct/v1/classes/{body['classId']}/plans/{result['planId']}/evidence/{ref_id}"
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    original = next(e for b in result["sources"] for e in b["evidence"] if e["refId"] == ref_id)
    assert response.json()["evidence"] == original
    assert client.get(path, headers={"Authorization": f"Bearer {_token(sub='other-user')}"}).status_code == 404
    assert client.get(path.replace(result["planId"], "unknown"), headers=headers).status_code == 404


def test_revocation_revision_assessment_and_expiry_fail_closed(setup):
    client, headers, body, _, runtime, settings, member = setup
    result = client.post("/api/instruct/v1/plan", json=body, headers=headers).json()["result"]
    ref_id = result["groups"][0]["rationale"]["evidenceRefs"][0]
    path = f"/api/instruct/v1/classes/{body['classId']}/plans/{result['planId']}/evidence/{ref_id}"
    assert client.get(path, headers=headers).status_code == 200
    for change in (
        {"revision": "membership-2"},
        {"classroom": {**member["classroom"], "assessmentIds": []}},
        {"validTo": "2021-01-01T00:00:00Z"},
    ):
        settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([{**member, **change}])
        assert client.get(path, headers=headers).status_code == 404
    settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([member])
    runtime.references.clock = lambda: float("inf")
    assert client.get(path, headers=headers).status_code == 404


def test_unprovisioned_sources_block_without_seed_fallback(setup):
    client, headers, body, _, runtime, settings, _ = setup
    runtime.sources = ConnectedSources(settings)
    response = client.post("/api/instruct/v1/plan", json=body, headers=headers)
    result = response.json()["result"]
    assert result["status"] == "blocked" and result["executionMode"] == "connected"
    assert result["groups"] == [] and result["package"] is None
    assert {s["state"] for s in result["sources"] if s["requested"]} == {"unavailable"}


def test_normalized_provider_mutations_reach_generated_groups_and_objective(setup):
    client, headers, body, _, runtime, *_ = setup
    before = client.post("/api/instruct/v1/plan", json=body, headers=headers).json()["result"]
    registry = generator.generate()
    for batch in registry["sources"]:
        for fact in batch["facts"]:
            if fact.get("studentId") == "student-01":
                fact["outcome"] = "correct"
            if fact["kind"] == "curriculum":
                fact["objective"] = "Updated approved objective from the normalized provider."
    runtime.sources = FrozenSources(registry)
    after = client.post("/api/instruct/v1/plan", json=body, headers=headers).json()["result"]
    group = lambda plan: next(g for g in plan["groups"] if "student-01" in g["studentIds"])
    assert group(before)["need"] == "graph_interpretation"
    assert group(after)["need"] == "extension"
    assert after["package"]["objective"]["text"] != before["package"]["objective"]["text"]
    assert "Updated approved objective" in after["package"]["objective"]["text"]


async def test_explicit_coordinates_do_not_enable_unverified_mapping_or_legacy_fallback(setup):
    _, _, body, _, runtime, settings, _ = setup
    settings.INSTRUCT_FABRIC_WORKSPACE_ID = "dedicated-workspace"
    settings.INSTRUCT_FABRIC_DATA_AGENT_ID = "dedicated-data-agent"
    settings.INSTRUCT_FABRIC_TOOL_NAME = "verified-tool-required"
    settings.INSTRUCT_FABRIC_QUESTION_ARGUMENT = "verified-argument-required"
    settings.INSTRUCT_SEARCH_ENDPOINT = "https://dedicated-search.invalid"
    settings.INSTRUCT_FOUNDRY_KB_NAME = "dedicated-kb"
    settings.INSTRUCT_SEARCH_API_VERSION = "operator-verified-version"
    user = _validator().validate(_token())
    request = PlanRequestV1.model_validate_json(json.dumps(body))
    grant = authorize(settings, user, request.classId, request.assessmentId)
    sources = ConnectedSources(settings)
    for context in runtime.contexts(request, grant):
        if context.source in {Source.FABRIC, Source.FOUNDRY}:
            batch = await sources.retrieve(context)
            assert batch.state == "unavailable" and "mapping" in batch.reason
            assert not batch.facts and not batch.evidence


def test_timeout_cancels_provider_retains_independent_evidence_and_sse_terminal(setup):
    client, headers, body, sources, runtime, *_ = setup
    cancelled = []
    retrieve = sources.retrieve

    async def slow(context):
        if context.source == Source.FOUNDRY:
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)
        return await retrieve(context)

    sources.retrieve = slow
    response = client.post("/api/instruct/v1/plan/stream", json=body, headers=headers)
    transcript = StreamTranscriptV1.model_validate_json(json.dumps({"events": events(response)}))
    result = transcript.events[-1].payload.result
    assert result.status == "partial" and result.groups and result.package is None
    assert cancelled == [True]
    assert next(s for s in result.sources if s.source == Source.FOUNDRY).state == "failed"


def test_provider_errors_sanitized_optional_request_and_privacy_context(setup):
    client, headers, body, sources, *_ = setup
    original = sources.retrieve

    async def broken(context):
        if context.source in {Source.FOUNDRY, Source.WORK, Source.WEB}:
            sources.calls.append(context)
            raise RuntimeError("secret-token provider-private-data")
        return await original(context)

    sources.retrieve = broken
    response = client.post("/api/instruct/v1/plan", json={**body, "includeWork": True, "includeWeb": True},
                           headers=headers)
    result = response.json()["result"]
    assert result["status"] == "partial"
    assert "secret-token" not in response.text and "provider-private-data" not in response.text
    query = next(c.publicQuery for c in sources.calls if c.source == Source.WEB)
    assert body["classId"] not in query and body["assessmentId"] not in query
    assert all(word not in query for word in ("student", "score", "support"))


def test_invalid_request_and_membership_config_sanitized(setup):
    client, headers, body, sources, _, settings, _ = setup
    response = client.post("/api/instruct/v1/plan", json={**body, "principal": "secret"}, headers=headers)
    assert response.status_code == 422 and "secret" not in response.text
    settings.INSTRUCT_CLASS_GRANTS_JSON = "invalid-secret"
    response = client.get("/api/instruct/v1/classes", headers=headers)
    assert response.status_code == 503 and "invalid-secret" not in response.text
    assert not sources.calls


def test_stream_internal_failure_is_one_sanitized_error_not_final(setup):
    client, headers, body, _, runtime, *_ = setup

    async def broken(*args):
        raise RuntimeError("secret")

    runtime.execute = broken
    response = client.post("/api/instruct/v1/plan/stream", json=body, headers=headers)
    transcript = StreamTranscriptV1.model_validate_json(json.dumps({"events": events(response)}))
    assert transcript.events[-1].type == "error" and "secret" not in response.text
    with pytest.raises(ValueError):
        StreamTranscriptV1.model_validate_json(json.dumps({"events": events(response)[:-1]}))


async def test_cancellation_awaits_outstanding_provider_work(setup):
    _, _, body, _, runtime, settings, _ = setup
    user = _validator().validate(_token())
    request = PlanRequestV1.model_validate_json(json.dumps(body))
    grant = authorize(settings, user, request.classId, request.assessmentId)
    started = asyncio.Event()
    stopped = []

    class Waiting:
        async def retrieve(self, context):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                stopped.append(context.source)

    runtime.sources = Waiting()
    task = asyncio.create_task(runtime.execute(request, grant, "cancel-test"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert set(stopped) == {Source.FABRIC, Source.FOUNDRY}
    assert not runtime.references.entries


def test_batch_scope_mode_hash_validation_and_bounded_index(setup):
    _, _, body, sources, runtime, settings, _ = setup
    user = _validator().validate(_token())
    request = PlanRequestV1.model_validate_json(json.dumps(body))
    grant = authorize(settings, user, request.classId, request.assessmentId)
    context = next(c for c in runtime.contexts(request, grant) if c.source == Source.FABRIC)
    batch = sources.batches[Source.FABRIC].model_copy(deep=True)
    assert validate_batch(context, batch) == batch
    for field, value in (("classId", "other"), ("assessmentId", "other")):
        with pytest.raises(ValueError):
            validate_batch(context, batch.model_copy(update={field: value}))
    batch.evidence[0].provenance.mode = "development_example"
    with pytest.raises(ValueError):
        validate_batch(context, batch)
    batch.evidence[0].provenance.mode = "connected"
    batch.evidence[0].excerpt = "Changed content"
    with pytest.raises(ValueError):
        validate_batch(context, batch)
    index = ReferenceIndex(max_plans=1)
    first = asyncio.run(runtime.execute(request, grant, "first"))
    second = asyncio.run(runtime.execute(request, grant, "second"))
    index.put(first, grant)
    index.put(second, grant)
    assert len(index.entries) == 1
    ref = first.result.sources[0].evidence[0].refId
    assert index.get(grant, first.result.planId, ref) is None
