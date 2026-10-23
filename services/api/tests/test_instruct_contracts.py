"""Persistent structural regressions; these do not prove live grounding."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.instruct_contracts import (
    EXAMPLE_MODELS, DraftV1, ExportV1, FinalEnvelopeV1, PlanRequestV1,
    ProviderBatchV1, StreamTranscriptV1, validate_examples,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "examples"


def payload(name):
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def validate(model, value):
    return model.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("name", EXAMPLE_MODELS)
def test_examples_and_lossless_round_trip(name):
    model = EXAMPLE_MODELS[name]
    parsed = validate(model, payload(name))
    assert model.model_validate_json(parsed.model_dump_json()) == parsed


def test_validator_and_terminal_parity():
    assert len(validate_examples(str(EXAMPLES))) == 9
    stream = validate(StreamTranscriptV1, payload("stream"))
    assert stream.events[-1].payload == validate(FinalEnvelopeV1, payload("blocked"))


@pytest.mark.parametrize("field,value", [
    ("unexpected", True), ("includeWork", "false"), ("includeWeb", 1),
    ("principal", {"subject": "forged"}),
])
def test_strict_request(field, value):
    body = payload("request")
    body[field] = value
    with pytest.raises(ValidationError):
        validate(PlanRequestV1, body)


@pytest.mark.parametrize("outcome,attempt,valid", [
    ("missing_submission", None, True), ("incorrect", "attempt-01", True),
    ("correct", None, False), ("missing_submission", "attempt-01", False),
])
def test_missing_is_not_incorrect(outcome, attempt, valid):
    body = payload("provider")
    body["facts"][1].update(outcome=outcome, attemptId=attempt)
    if valid:
        validate(ProviderBatchV1, body)
    else:
        with pytest.raises(ValidationError):
            validate(ProviderBatchV1, body)


@pytest.mark.parametrize("mutation", ["ref", "class", "source", "duplicate", "failure"])
def test_provider_integrity(mutation):
    body = payload("provider")
    if mutation == "ref":
        body["facts"][0]["evidenceRefs"] = ["missing"]
    elif mutation == "class":
        body["evidence"][0]["classId"] = "other"
    elif mutation == "source":
        body["source"] = "foundry"
    elif mutation == "duplicate":
        body["facts"].append(copy.deepcopy(body["facts"][0]))
    else:
        body["state"] = "failed"
    with pytest.raises(ValidationError):
        validate(ProviderBatchV1, body)


@pytest.mark.parametrize("mutation", ["duplicate-terminal", "eof", "sequence", "state", "request"])
def test_stream_rejects_invalid_termination(mutation):
    body = payload("stream")
    if mutation == "duplicate-terminal":
        body["events"].append(copy.deepcopy(body["events"][-1]))
    elif mutation == "eof":
        body["events"].pop()
    elif mutation == "sequence":
        body["events"][1]["sequence"] = 99
    elif mutation == "state":
        body["events"][1]["state"] = "succeeded"
    else:
        body["events"][-1]["requestId"] = "other"
    with pytest.raises(ValidationError):
        validate(StreamTranscriptV1, body)


@pytest.mark.parametrize("mutation", ["scope", "hash", "invalidation", "review", "before", "path"])
def test_draft_scope_hash_edits_and_review(mutation):
    body = payload("draft")
    if mutation == "scope":
        body["scope"]["classId"] = "other"
    elif mutation == "hash":
        body["baselineSha256"] = "0" * 64
    elif mutation == "invalidation":
        body["edits"][0]["invalidatedClaimIds"] = ["other"]
    elif mutation == "review":
        body["state"] = "reviewed"
    elif mutation == "before":
        body["edits"][0]["changes"][0]["before"] = "not the baseline"
    else:
        body["edits"][0]["changes"][0]["path"] = "/baseline/principal"
    with pytest.raises(ValidationError):
        validate(DraftV1, body)


def test_export_retains_baseline_and_edit_provenance():
    exported = validate(ExportV1, payload("export"))
    restored = ExportV1.model_validate_json(exported.model_dump_json())
    assert restored.draft == validate(DraftV1, payload("draft"))
    assert restored.draft.edits[0].changes[0].provenance == "teacher_edit_unverified"


def test_review_binds_current_edit_and_subsequent_edit_must_clear_it():
    body = payload("draft")
    body["state"] = "reviewed"
    body["review"] = {
        "reviewer": body["scope"]["principal"], "reviewedAt": "2026-10-19T07:10:00-04:00",
        "editRevision": len(body["edits"]), "meaning": "teacher_review_only_not_published",
    }
    validate(DraftV1, body)
    body["review"]["editRevision"] = 0
    with pytest.raises(ValidationError):
        validate(DraftV1, body)
    body["review"]["editRevision"] = len(body["edits"])
    body["state"] = "edited"
    with pytest.raises(ValidationError):
        validate(DraftV1, body)
    body["review"] = None
    validate(DraftV1, body)


def test_expected_item_manifest_must_cover_both_distinct_skill_roles():
    body = payload("provider")
    manifest = {
        "factId": "manifest", "kind": "assessment", "authority": "assessment_record",
        "evidenceRefs": ["ref-assessment"], "effectiveFrom": "2026-10-16T00:00:00-04:00",
        "assessmentId": body["assessmentId"], "graphSkillId": "skill-graph",
        "evidenceSkillId": "skill-evidence",
        "itemSkills": {"item-graph": "skill-graph", "item-evidence": "skill-evidence"},
        "attemptSelection": "latest_effective_then_attempt_id",
    }
    body["facts"].append(manifest)
    validate(ProviderBatchV1, body)
    manifest["itemSkills"].pop("item-evidence")
    with pytest.raises(ValidationError):
        validate(ProviderBatchV1, body)


@pytest.mark.parametrize("mutation", ["timing", "claim", "support", "partition", "mode"])
def test_plan_cross_reference_guarantees(mutation):
    body = payload("complete")
    result = body["result"]
    if mutation == "timing":
        result["package"]["segments"][0]["minutes"] += 1
    elif mutation == "claim":
        result["groups"][0]["rationale"]["evidenceRefs"] = ["missing"]
    elif mutation == "support":
        result["package"]["implementedSupportFactIds"] = ["missing"]
    elif mutation == "partition":
        result["groups"][0]["studentIds"].append(result["groups"][0]["studentIds"][0])
    else:
        result["executionMode"] = "connected"
    with pytest.raises(ValidationError):
        validate(FinalEnvelopeV1, body)
