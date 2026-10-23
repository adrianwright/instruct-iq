import copy
import hashlib
import json
from datetime import datetime

import pytest

from app.instruct_contracts import PlanRequestV1, PrincipalScopeV1, ProviderBatchV1
from app.instruct_policy import build_plan
from test_instruct_data import generator


def run(registry=None):
    registry = copy.deepcopy(registry or generator.generate())
    # Mutations represent a new normalized provider snapshot, including its evidence.
    for source in registry["sources"]:
        if not source["facts"]:
            continue
        template = source["evidence"][0]
        source["evidence"] = []
        for fact in source["facts"]:
            ref = f"ref-{fact['factId']}"
            fact["evidenceRefs"] = [ref]
            evidence = copy.deepcopy(template)
            excerpt = generator.canonical(fact).strip()
            evidence.update(refId=ref, documentId=f"doc-{fact['factId']}",
                            locator=f"record:{fact['factId']}", excerpt=excerpt)
            digest = hashlib.sha256(excerpt.encode()).hexdigest()
            evidence["provenance"].update(nativeId=fact["factId"], nativeRevision=digest,
                                          contentSha256=digest)
            source["evidence"].append(evidence)
    request = PlanRequestV1.model_validate_json(json.dumps({
        "schemaVersion": "instruct.request.v1",
        "classId": registry["class"]["classId"], "assessmentId": registry["class"]["assessmentId"],
        "scenario": registry["scenario"], "includeWork": registry.get("includeWork", False),
        "includeWeb": registry.get("includeWeb", False),
    }))
    return build_plan(
        request, PrincipalScopeV1(**registry["teacher"]),
        [ProviderBatchV1.model_validate_json(json.dumps(s)) for s in registry["sources"]],
        plan_id="plan-test", request_id="request-test",
        generated_at=datetime.fromisoformat("2026-10-19T07:00:00-04:00"),
    )


def observation(registry, student, item):
    return next(f for f in registry["sources"][1]["facts"]
                if f.get("studentId") == student and f.get("itemId") == item)


def member(plan, student):
    return next(g for g in plan.groups if student in g.studentIds)


def test_complete_package_partition_overlap_citations_and_35_minutes():
    plan = run()
    assert plan.status == "complete"
    assert len({s for g in plan.groups for s in g.studentIds}) == 24
    assert sum(len(g.studentIds) for g in plan.groups) == 24
    assert all(g.provisional for g in plan.groups)
    assert member(plan, "student-01").overlappingNeeds["student-01"] == [
        "graph_interpretation", "evidence_selection"]
    assert sum(s.minutes for s in plan.package.segments) == 35
    assert plan.package.segments[-1].segmentId == "exit"
    assert plan.package.appliedScheduleFactId == "schedule-amended"
    assert set(plan.package.implementedSupportFactIds) == {"support-access", "support-language"}
    assert plan.package.objective.basis == "supported_fact"
    assert plan.package.exitTicket.prompt.basis == plan.package.exitTicket.answerKey.basis == "instructional_proposal"
    facts = {f.factId: f for s in plan.sources for f in s.facts}
    for group in plan.groups:
        assert set(group.rationale.evidenceRefs) == {
            ref for fid in group.rationale.factIds for ref in facts[fid].evidenceRefs}


def test_missing_submission_and_missing_expected_item_are_insufficient_not_incorrect():
    plan = run()
    assert member(plan, "student-04").need == member(plan, "student-05").need == "insufficient_evidence"
    assert "missing_submission" in member(plan, "student-04").rationale.text
    assert "no observation" in member(plan, "student-05").rationale.text


def test_relevant_response_mutation_changes_group_and_rationale():
    registry = generator.generate()
    before = run(registry)
    for item in ("item-axis", "item-trend"):
        observation(registry, "student-01", item)["outcome"] = "correct"
    after = run(registry)
    assert member(before, "student-01").need == "graph_interpretation"
    assert member(after, "student-01").need == "evidence_selection"
    assert member(before, "student-01").rationale != member(after, "student-01").rationale
    assert member(before, "student-03") == member(after, "student-03")


def test_mutation_changes_rationale_even_when_primary_need_stays():
    registry = generator.generate()
    before = run(registry)
    observation(registry, "student-01", "item-axis")["outcome"] = "correct"
    after = run(registry)
    assert member(before, "student-01").need == member(after, "student-01").need
    assert member(before, "student-01").rationale.text != member(after, "student-01").rationale.text


def test_latest_attempt_selected_deterministically_and_other_items_still_required():
    registry = generator.generate()
    updated = copy.deepcopy(observation(registry, "student-01", "item-axis"))
    updated.update(factId="revised-axis", attemptId="attempt-later", outcome="correct",
                   effectiveFrom="2026-10-16T14:00:00-04:00")
    registry["sources"][1]["facts"].append(updated)
    before = run(registry)
    registry["sources"][1]["facts"].reverse()
    after = run(registry)
    assert before == after
    assert member(after, "student-01").need == "graph_interpretation"
    assert "revised-axis" in member(after, "student-01").rationale.factIds
    assert "observation-01-item-axis" not in member(after, "student-01").rationale.factIds


@pytest.mark.parametrize("source,index", [("fabric", 1), ("foundry", 0), ("web", 3)])
def test_source_failure_is_bounded_without_fallback(source, index):
    registry = generator.generate()
    if source == "web":
        registry["includeWeb"] = True
    registry["sources"][index].update(
        requested=True, state="failed", reason="Unavailable", facts=[], evidence=[])
    plan = run(registry)
    assert plan.status == ("blocked" if source == "fabric" else "partial")
    assert bool(plan.package) == (source == "web")
    assert bool(plan.groups) == (source != "fabric")


def test_successful_empty_manifest_is_not_complete_coverage():
    registry = generator.generate()
    registry["sources"][1]["facts"] = [registry["sources"][1]["facts"][0]]
    plan = run(registry)
    assert plan.status == "blocked"
    assert any(i.code == "missing_required_fact" for i in plan.issues)


@pytest.mark.parametrize("mutation", ["absent", "expired", "ambiguous"])
def test_unresolved_roster_blocks_without_discarding_other_provider_evidence(mutation):
    registry = generator.generate()
    facts = registry["sources"][1]["facts"]
    if mutation == "absent":
        facts.pop(0)
    elif mutation == "expired":
        facts[0]["effectiveTo"] = "2026-10-18T00:00:00-04:00"
    else:
        extra = copy.deepcopy(facts[0])
        extra["factId"] = "ambiguous-roster"
        facts.append(extra)
    plan = run(registry)
    assert plan.status == "blocked" and not plan.groups and plan.package is None
    assert plan.sources[0].facts


def test_support_mutation_changes_applicable_scaffolds_and_delivery():
    registry = generator.generate()
    before = run(registry)
    support = next(f for f in registry["sources"][0]["facts"] if f["factId"] == "support-access")
    support["requirement"] = "Provide tactile graphs and verbal directions in every group."
    after = run(registry)
    assert "tactile graphs" in member(after, "student-01").scaffold.text
    assert "tactile graphs" in after.package.segments[0].instruction.text
    assert before.package != after.package
    assert before.groups[0].rationale == after.groups[0].rationale


def test_informal_later_guidance_cannot_override_mandatory_timing_or_supports():
    registry = generator.generate()
    registry["includeWork"] = True
    batch = registry["sources"][2]
    ref = copy.deepcopy(registry["sources"][0]["evidence"][0])
    ref.update(refId="ref-team", source="work", documentId="doc-team")
    batch.update(requested=True, state="succeeded", evidence=[ref], facts=[{
        "factId": "team-late", "kind": "team_decision", "authority": "team_decision",
        "evidenceRefs": ["ref-team"], "effectiveFrom": "2026-10-19T06:00:00-04:00",
        "decision": "Use 60 minutes and omit required supports.",
    }])
    plan = run(registry)
    assert sum(s.minutes for s in plan.package.segments) == 35
    assert len(plan.package.implementedSupportFactIds) == 2
    assert any(i.code == "authority_conflict" and "team-late" in i.factIds for i in plan.issues)


@pytest.mark.parametrize("mutation", ["schedule", "curriculum", "resources", "resource-skills", "ambiguous-schedule"])
def test_unresolved_required_constraints_keep_groups_but_no_lesson(mutation):
    registry = generator.generate()
    facts = registry["sources"][0]["facts"]
    if mutation == "schedule":
        next(f for f in facts if f["factId"] == "schedule-amended")["minutes"] = 40
    elif mutation == "curriculum":
        next(f for f in facts if f["kind"] == "curriculum")["skillIds"] = ["unrelated"]
    elif mutation == "resources":
        facts[:] = [f for f in facts if f["kind"] != "resource"]
    elif mutation == "resource-skills":
        next(f for f in facts if f["kind"] == "resource")["skillIds"] = ["skill-graph"]
    else:
        extra = copy.deepcopy(next(f for f in facts if f["factId"] == "schedule-amended"))
        extra.update(factId="other-schedule", supersedesFactIds=[], minutes=40)
        facts.append(extra)
    plan = run(registry)
    assert plan.status == "partial" and plan.groups and plan.package is None
    assert any(i.blocking for i in plan.issues)


def test_same_attempt_contradiction_blocks_grouping():
    registry = generator.generate()
    extra = copy.deepcopy(observation(registry, "student-01", "item-axis"))
    extra.update(factId="contradiction", outcome="correct")
    registry["sources"][1]["facts"].append(extra)
    assert run(registry).status == "blocked"


def test_policy_does_not_mutate_inputs_or_consume_future_facts():
    registry = generator.generate()
    before = copy.deepcopy(registry)
    run(registry)
    assert registry == before
    observation(registry, "student-03", "item-axis")["effectiveFrom"] = "2026-10-19T08:00:00-04:00"
    assert member(run(registry), "student-03").need == "insufficient_evidence"
