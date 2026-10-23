"""Deterministic instructional policy over authorized, normalized provider facts only."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.instruct_contracts import (
    AssessmentFactV1, ClaimV1, CurriculumFactV1, GroupV1, IssueV1,
    ObservationFactV1, PlanRequestV1, PlanResultV1, PrincipalScopeV1,
    ProviderBatchV1, ResourceFactV1, RosterFactV1, ScheduleFactV1,
    SupportFactV1, TeachingPackageV1,
)
from app.schemas import Source


def build_plan(
    request: PlanRequestV1, principal: PrincipalScopeV1, sources: list[ProviderBatchV1],
    *, plan_id: str, request_id: str, generated_at: datetime,
) -> PlanResultV1:
    """Caller must authorize before retrieval. This pure function performs no I/O."""
    if {s.source for s in sources} != set(Source) or len(sources) != 4:
        raise ValueError("one terminal batch per source required")
    cutoff = request.scenario.planningCutoff
    snapshot = []
    for source in sorted(sources, key=lambda s: list(Source).index(s.source)):
        if (source.classId, source.assessmentId) != (request.classId, request.assessmentId):
            raise ValueError("provider scope mismatch")
        requested = source.source in {Source.FABRIC, Source.FOUNDRY} or (
            source.source == Source.WORK and request.includeWork
        ) or (source.source == Source.WEB and request.includeWeb)
        if source.requested != requested or source.state == "running":
            raise ValueError("source selection/terminal state mismatch")
        facts = [
            f for f in source.facts if f.effectiveFrom <= cutoff and (
                f.effectiveTo is None or f.effectiveTo > cutoff or isinstance(f, ScheduleFactV1))
        ]
        snapshot.append(source.model_copy(update={
            "facts": sorted(facts, key=lambda f: f.factId),
            "evidence": sorted(source.evidence, key=lambda e: e.refId),
        }))
    by_source = {s.source: s for s in snapshot}
    facts = [f for s in snapshot for f in s.facts]
    issues = []

    def issue(code, affected, message, *, blocking=True, related=()):
        issues.append(IssueV1(
            issueId=f"issue-{len(issues) + 1}", code=code, affected=affected,
            blocking=blocking, message=message, factIds=[f.factId for f in related],
            evidenceRefs=sorted({r for f in related for r in f.evidenceRefs}),
            resolution="Retrieve or reconcile authorized evidence, then regenerate and review.",
        ))

    def claim(cid, text, related=(), *, proposal=False):
        related = sorted({f.factId: f for f in related}.values(), key=lambda f: f.factId)
        return ClaimV1(
            claimId=cid, text=text, basis="instructional_proposal" if proposal else "supported_fact",
            factIds=[f.factId for f in related],
            evidenceRefs=sorted({r for f in related for r in f.evidenceRefs}),
        )

    for source in snapshot:
        if source.state in {"disabled", "unavailable", "failed"}:
            required = source.source in {Source.FABRIC, Source.FOUNDRY}
            issue("required_source_missing" if required else "optional_source_missing",
                  "groups" if source.source == Source.FABRIC else "lesson" if required else "enrichment",
                  f"Requested {source.source.value} evidence is {source.state}.", blocking=required)

    rosters = [f for f in facts if isinstance(f, RosterFactV1)]
    coverage = [f for f in facts if isinstance(f, AssessmentFactV1)]
    supports = [f for f in facts if isinstance(f, SupportFactV1)]
    groups = []
    if by_source[Source.FABRIC].state == "succeeded":
        if len(rosters) != 1 or len(coverage) != 1:
            issue("missing_required_fact", "groups", "One authorized roster and expected item/skill manifest are required.")
        else:
            roster, manifest = rosters[0], coverage[0]
            selected = {}
            ambiguous = False
            for obs in (f for f in facts if isinstance(f, ObservationFactV1)):
                if manifest.itemSkills.get(obs.itemId) != obs.skillId or obs.studentId not in roster.studentIds:
                    issue("authority_conflict", "groups", "Observation does not match authorized roster/item coverage.", related=[obs, manifest])
                    ambiguous = True
                    continue
                key = (obs.studentId, obs.itemId)
                rank = (obs.effectiveFrom, obs.attemptId or "")
                old = selected.get(key)
                if old and rank == (old.effectiveFrom, old.attemptId or "") and old.outcome != obs.outcome:
                    issue("authority_conflict", "groups", "Same selected attempt has contradictory outcomes.", related=[old, obs])
                    ambiguous = True
                elif old is None or rank > (old.effectiveFrom, old.attemptId or ""):
                    selected[key] = obs
            if not ambiguous:
                buckets = defaultdict(list)
                details = {}
                for student in sorted(roster.studentIds):
                    observations = [selected.get((student, item)) for item in sorted(manifest.itemSkills)]
                    missing = any(o is None or o.outcome == "missing_submission" for o in observations)
                    gaps = [
                        role for role, skill in (
                            ("graph_interpretation", manifest.graphSkillId),
                            ("evidence_selection", manifest.evidenceSkillId),
                        ) if any(o and o.skillId == skill and o.outcome == "incorrect" for o in observations)
                    ]
                    need = "insufficient_evidence" if missing else gaps[0] if gaps else "extension"
                    buckets[need].append(student)
                    description = "; ".join(
                        f"{item}: {o.outcome} ({o.attemptId or 'no attempt'})" if o else f"{item}: no observation"
                        for item, o in zip(sorted(manifest.itemSkills), observations)
                    )
                    details[student] = (gaps, observations, f"{student}: {description}.")
                scaffolds = {
                    "insufficient_evidence": "Collect a short, accessible check of every missing item before inferring mastery.",
                    "graph_interpretation": "Model axes and trends with a worked example, then gradually remove prompts.",
                    "evidence_selection": "Use claim-evidence sentence frames and compare relevant numerical evidence.",
                    "extension": "Compare two defensible claims and justify which evidence is stronger.",
                }
                for need in ("insufficient_evidence", "graph_interpretation", "evidence_selection", "extension"):
                    members = buckets[need]
                    if not members:
                        continue
                    related = [roster, manifest] + [
                        o for student in members for o in details[student][1] if o is not None
                    ]
                    applicable = [s for s in supports if set(s.studentIds) & set(members)]
                    text = " ".join(details[s][2] for s in members)
                    text += " Provisional priority: insufficient evidence, then observed graph need, evidence need, extension; not an ability label."
                    groups.append(GroupV1(
                        groupId=f"group-{need}", need=need, provisional=True, studentIds=members,
                        overlappingNeeds={s: details[s][0] for s in members if details[s][0]},
                        rationale=claim(f"rationale-{need}", text, related),
                        scaffold=claim(f"scaffold-{need}", scaffolds[need] + "".join(
                            f" Required for {', '.join(sorted(set(s.studentIds) & set(members)))}: {s.requirement}"
                            for s in applicable), applicable, proposal=True),
                    ))
                if buckets["insufficient_evidence"]:
                    issue("insufficient_evidence", "student_evidence",
                          "Missing submissions or item coverage are not incorrect answers or low mastery.",
                          blocking=False, related=[roster, manifest])

    curricula = [f for f in facts if isinstance(f, CurriculumFactV1)]
    resources = [f for f in facts if isinstance(f, ResourceFactV1)]
    schedule_history = [f for f in facts if isinstance(f, ScheduleFactV1)
                        and f.lessonDate.isoformat() == request.scenario.lessonDate]
    superseded = {fid for f in schedule_history for fid in f.supersedesFactIds}
    schedules = [s for s in schedule_history if s.factId not in superseded
                 and (s.effectiveTo is None or s.effectiveTo > cutoff)]
    package = None
    if by_source[Source.FOUNDRY].state == "succeeded":
        if len(curricula) != 1 or len(schedules) != 1:
            issue("authority_conflict" if len(curricula) > 1 or len(schedules) > 1 else "missing_required_fact",
                  "lesson", "A unique approved curriculum and effective superseding schedule are required.",
                  related=curricula + schedules)
        elif schedules[0].minutes != 35:
            issue("authority_conflict", "lesson", "Effective schedule conflicts with the fixed 35-minute scenario.", related=schedules)
        elif not resources:
            issue("missing_required_fact", "lesson", "An approved instructional resource is required.")
        elif coverage and not {coverage[0].graphSkillId, coverage[0].evidenceSkillId} <= {
            skill for resource in resources for skill in resource.skillIds
        }:
            issue("missing_required_fact", "lesson", "Approved resources do not cover both required skills.", related=resources)
        elif coverage and not {coverage[0].graphSkillId, coverage[0].evidenceSkillId} <= set(curricula[0].skillIds):
            issue("authority_conflict", "lesson", "Assessment skills do not match the approved objective.", related=[coverage[0], curricula[0]])
        elif groups:
            curriculum, schedule = curricula[0], schedules[0]
            constraints = [schedule, *supports, *resources]
            support_text = " ".join(f"For {', '.join(s.studentIds)}: {s.requirement}" for s in supports)
            resource_text = " ".join(r.usage for r in resources)
            steps = [
                ("launch", 5, "Preview vocabulary and the shared objective."),
                ("model", 7, "Model interpreting axes and comparing numerical evidence."),
                ("practice", 15, "Use provisional group scaffolds; regroup as checks reveal new evidence."),
                ("share", 4, "Compare claims and justify evidence choices."),
                ("exit", 4, "Complete the exit ticket independently with all authorized supports."),
            ]
            package = TeachingPackageV1(
                objective=claim("objective", curriculum.objective, [curriculum]),
                segments=[{
                    "segmentId": sid, "minutes": minutes,
                    "instruction": claim(f"instruction-{sid}", text + (
                        f" Approved resources: {resource_text} Required supports throughout: {support_text}"
                        if sid == "launch" else ""), constraints, proposal=True),
                    "groupIds": [g.groupId for g in groups],
                } for sid, minutes, text in steps],
                exitTicket={
                    "prompt": claim("exit-prompt", "For a graph of readings 2, 4, 6 at minutes 0, 1, 2, identify the time axis, describe the trend, and cite two values supporting it.", proposal=True),
                    "answerKey": claim("exit-key", "Time is on the horizontal axis; readings increase by 2 each minute. Readings 2 at minute 0 and 6 at minute 2 support the increase.", proposal=True),
                    "skillIds": [coverage[0].graphSkillId, coverage[0].evidenceSkillId],
                },
                implementedSupportFactIds=[s.factId for s in supports],
                appliedScheduleFactId=schedule.factId, resourceFactIds=[r.factId for r in resources],
            )
    for fact in facts:
        if fact.kind == "team_decision":
            issue("authority_conflict", "lesson",
                  "Informal team guidance is retained for teacher review, not applied over approved curriculum, supports or timing.",
                  blocking=False, related=[fact, *supports, *schedules, *curricula])
    modes = {e.provenance.mode for source in snapshot for e in source.evidence}
    if len(modes) > 1:
        raise ValueError("mixed execution modes are forbidden")
    if not groups and not any(i.blocking for i in issues):
        issue("missing_required_fact", "groups", "Assessment-grounded groups could not be established.")
    status = "blocked" if not groups else "partial" if package is None or any(
        i.blocking or i.code == "optional_source_missing" for i in issues
    ) else "complete"
    result = PlanResultV1(
        schemaVersion="instruct.plan.v1", planId=plan_id, revision=1, requestId=request_id,
        principal=principal, classId=request.classId, assessmentId=request.assessmentId,
        scenario=request.scenario, generatedAt=generated_at, executionMode=next(iter(modes), "connected"),
        status=status, sources=snapshot, groups=groups, package=package, issues=issues,
        unresolvedQuestions=[i.message for i in issues],
    )
    # Revalidate the complete snapshot, including references, timing and support coverage.
    return PlanResultV1.model_validate_json(result.model_dump_json())
