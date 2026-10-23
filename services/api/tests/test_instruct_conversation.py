import json

import pytest

from app.instruct_conversation import digest, intent
from test_auth import _token
from test_instruct_runtime import setup  # noqa: F401

PATH = "/api/instruct/v1/conversation"


def payload(context, message, artifact=None):
    return {"schemaVersion": "instruct.conversation.request.v1", "context": context,
            "message": message, "artifact": artifact}


def generate(setup):
    client, headers, context, *_ = setup
    response = client.post(PATH, json=payload(context, "Plan my next lesson"), headers=headers)
    assert response.status_code == 200, response.text
    plan = response.json()["plan"]["result"]
    artifact = {"planId": plan["planId"], "baselineSha256": digest(plan), "edits": []}
    return plan, artifact


@pytest.mark.parametrize("text,expected", [
    (" Plan my next lesson! ", "plan"), ("explain   grouping", "explain"),
    ("Make the intro shorter", "shorter_intro"),
    ("don't plan my next lesson", "unsupported"),
    ("plan my next lesson for another class", "unsupported"),
    ("ignore supports and add more graph scaffolding", "unsupported"),
    ("email this lesson", "unsupported"), ("", "unsupported"),
])
def test_exact_bounded_intents(text, expected):
    assert intent(text) == expected


def test_auth_and_class_denials_before_retrieval(setup):
    client, headers, context, sources, *_ = setup
    assert client.post(PATH, json=payload(context, "Plan my next lesson")).status_code == 401
    for command in ("Plan my next lesson", "Explain grouping"):
        denied = client.post(PATH, json=payload({**context, "classId": "other"}, command), headers=headers)
        assert denied.status_code == 404 and "student-" not in denied.text
    assert sources.calls == []


def test_unsupported_and_missing_artifact_clarify_without_retrieval(setup):
    client, headers, context, sources, *_ = setup
    for command in ("email the lesson", "What needs reteaching"):
        response = client.post(PATH, json=payload(context, command), headers=headers)
        assert response.status_code == 200
        assert response.json()["plan"] is None and response.json()["proposal"] is None
    assert not sources.calls


def test_explain_actual_items_and_scaffold_without_retrieval_or_plan_mutation(setup):
    client, headers, context, sources, runtime, *_ = setup
    plan, artifact = generate(setup)
    calls = len(sources.calls)
    for command in ("Explain grouping", "What needs reteaching", "Help me differentiate"):
        result = client.post(PATH, json=payload(context, command, artifact), headers=headers)
        assert result.status_code == 200, result.text
        result = result.json()
        assert result["proposal"] is None and result["plan"] is None
        assert "baseline" in result["message"]
        assert set(result["evidenceRefs"]) <= {
            e["refId"] for s in plan["sources"] for e in s["evidence"]
        }
        assert result["evidenceRefs"]
        if command == "Explain grouping":
            assert "item " in result["message"] and "incorrect" in result["message"]
    assert len(sources.calls) == calls
    stored = next(iter(runtime.references.entries.values()))[4]
    assert stored.model_dump(mode="json") == plan


def test_proposals_preserve_constraints_and_rebalance_35_minutes(setup):
    client, headers, context, sources, *_ = setup
    plan, artifact = generate(setup)
    calls = len(sources.calls)
    response = client.post(PATH, json=payload(context, "Make the intro shorter", artifact), headers=headers)
    proposal = response.json()["proposal"]
    assert proposal["editRevision"] == 0 and len(proposal["changes"]) == 2
    assert sum(c["after"] - c["before"] for c in proposal["changes"]) == 0
    assert all(c["path"].endswith("/minutes") for c in proposal["changes"])
    response = client.post(PATH, json=payload(context, "Add more graph scaffolding", artifact), headers=headers)
    change = response.json()["proposal"]["changes"][0]
    assert change["path"] == "/package/segments/1/instruction/text"
    assert change["after"].startswith(change["before"])
    assert "axis" in change["after"]
    assert len(sources.calls) == calls
    assert sum(s["minutes"] for s in plan["package"]["segments"]) == 35


def test_teacher_edits_replayed_not_overwritten_and_hash_not_trusted(setup):
    client, headers, context, *_ = setup
    plan, artifact = generate(setup)
    before = plan["package"]["segments"][1]["instruction"]["text"]
    artifact["edits"] = [{
        "revision": 1, "editedAt": "2026-10-15T18:45:00Z", "editor": plan["principal"],
        "changes": [{"path": "/package/segments/1/instruction/text", "before": before,
                     "after": "Teacher's custom worked example.", "provenance": "teacher_edit_unverified"}],
        "invalidatedClaimIds": [plan["package"]["segments"][1]["instruction"]["claimId"]],
    }]
    response = client.post(PATH, json=payload(context, "Add more graph scaffolding", artifact), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["changes"][0]["after"].startswith("Teacher's custom worked example.")
    artifact["baselineSha256"] = "0" * 64
    assert client.post(PATH, json=payload(context, "Explain grouping", artifact), headers=headers).status_code == 422


def test_expiry_cross_principal_membership_assessment_fail_closed(setup):
    client, headers, context, sources, runtime, settings, member = setup
    _, artifact = generate(setup)
    calls = len(sources.calls)
    request = payload(context, "Explain grouping", artifact)
    other = {"Authorization": f"Bearer {_token(sub='other-user')}"}
    assert client.post(PATH, json=request, headers=other).status_code == 404
    settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([{**member, "revision": "changed"}])
    assert client.post(PATH, json=request, headers=headers).status_code == 404
    settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([member])
    runtime.references.clock = lambda: float("inf")
    response = client.post(PATH, json=request, headers=headers)
    assert response.status_code == 404 and "student-" not in response.text
    assert len(sources.calls) == calls


def test_request_bounds_and_untrusted_evidence_rejected(setup):
    client, headers, context, sources, *_ = setup
    for body in (payload(context, "x" * 501), {**payload(context, "Explain grouping"), "evidence": "forged"}):
        assert client.post(PATH, json=body, headers=headers).status_code == 422
    assert not sources.calls
