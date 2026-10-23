"""Strict normalized Instruct v1 contracts shared by policy and instructional routes."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    model_validator,
)

from app.schemas import Source

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
Text = Annotated[str, Field(min_length=1, max_length=12000)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SourceState = Literal[
    "not_requested", "disabled", "unavailable", "failed", "running", "succeeded"
]
Authority = Literal[
    "assessment_record", "mandatory_support", "approved_curriculum",
    "approved_schedule", "approved_resource", "team_decision", "public_reference",
]
ExecutionMode = Literal["connected", "test_double", "development_example"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


class ScenarioV1(Contract):
    assessmentDate: Literal["2026-10-16"]
    lessonDate: Literal["2026-10-19"]
    timezone: Literal["America/New_York"]
    planningCutoff: AwareDatetime
    lessonMinutes: Literal[35]
    studentCount: Literal[24]

    @model_validator(mode="after")
    def fixed_cutoff(self) -> Self:
        if self.planningCutoff.isoformat() != "2026-10-19T07:00:00-04:00":
            raise ValueError("scenario cutoff must be 2026-10-19T07:00:00-04:00")
        return self


class PlanRequestV1(Contract):
    schemaVersion: Literal["instruct.request.v1"]
    classId: Id
    assessmentId: Id
    scenario: ScenarioV1
    includeWork: bool
    includeWeb: bool


class PrincipalScopeV1(Contract):
    tenantId: Id
    subject: Annotated[str, Field(min_length=1, max_length=255)]


class ClassGrantV1(Contract):
    """Server-created authorization context, never accepted from a browser."""

    grantId: Id
    principal: PrincipalScopeV1
    classId: Id
    checkedAt: AwareDatetime
    membershipRevision: Id


class RetrievalContextV1(Contract):
    schemaVersion: Literal["instruct.retrieval.v1"]
    grant: ClassGrantV1
    assessmentId: Id
    scenario: ScenarioV1
    source: Source
    capability: Literal["assessment", "curriculum", "team_context", "public_enrichment"]
    publicQuery: Text | None = None

    @model_validator(mode="after")
    def capability_matches(self) -> Self:
        expected = {
            Source.FABRIC: "assessment", Source.FOUNDRY: "curriculum",
            Source.WORK: "team_context", Source.WEB: "public_enrichment",
        }
        if self.capability != expected[self.source]:
            raise ValueError("source/capability mismatch")
        if (self.source == Source.WEB) != (self.publicQuery is not None):
            raise ValueError("only Web requires a privacy-filtered publicQuery")
        return self


class ProvenanceV1(Contract):
    mode: ExecutionMode
    nativeId: Text
    nativeRevision: Text
    retrievedAt: AwareDatetime
    contentSha256: Digest
    adapter: Text


class EvidenceV1(Contract):
    refId: Id
    classId: Id
    source: Source
    documentId: Id
    title: Text
    locator: Text
    excerpt: Text
    provenance: ProvenanceV1
    publicUrl: HttpUrl | None = None

    @model_validator(mode="after")
    def public_link(self) -> Self:
        if self.publicUrl is not None and self.source != Source.WEB:
            raise ValueError("private evidence uses authorized document IDs, not public URLs")
        return self


class FactBaseV1(Contract):
    factId: Id
    evidenceRefs: Annotated[list[Id], Field(min_length=1)]
    effectiveFrom: AwareDatetime
    effectiveTo: AwareDatetime | None = None

    @model_validator(mode="after")
    def effective_interval(self) -> Self:
        _unique(self.evidenceRefs, "fact evidence references")
        if self.effectiveTo is not None and self.effectiveTo <= self.effectiveFrom:
            raise ValueError("effectiveTo must follow effectiveFrom")
        return self


class RosterFactV1(FactBaseV1):
    kind: Literal["roster"]
    authority: Literal["assessment_record"]
    studentIds: Annotated[list[Id], Field(min_length=24, max_length=24)]

    @model_validator(mode="after")
    def unique_students(self) -> Self:
        _unique(self.studentIds, "roster students")
        return self


class ObservationFactV1(FactBaseV1):
    kind: Literal["observation"]
    authority: Literal["assessment_record"]
    assessmentId: Id
    studentId: Id
    skillId: Id
    itemId: Id
    attemptId: Id | None
    outcome: Literal["correct", "incorrect", "missing_submission"]

    @model_validator(mode="after")
    def missing_is_not_incorrect(self) -> Self:
        if (self.outcome == "missing_submission") != (self.attemptId is None):
            raise ValueError("missing submission has no attempt; scored observations require one")
        return self


class AssessmentFactV1(FactBaseV1):
    """Authorized expected coverage, not an assertion that students submitted."""

    kind: Literal["assessment"]
    authority: Literal["assessment_record"]
    assessmentId: Id
    graphSkillId: Id
    evidenceSkillId: Id
    itemSkills: dict[Id, Id]
    attemptSelection: Literal["latest_effective_then_attempt_id"]

    @model_validator(mode="after")
    def coverage(self) -> Self:
        if self.graphSkillId == self.evidenceSkillId or set(self.itemSkills.values()) != {
            self.graphSkillId, self.evidenceSkillId
        }:
            raise ValueError("expected items must cover both distinct required skills")
        return self


class CurriculumFactV1(FactBaseV1):
    kind: Literal["curriculum"]
    authority: Literal["approved_curriculum"]
    approvalId: Id
    skillIds: Annotated[list[Id], Field(min_length=1)]
    objective: Text


class SupportFactV1(FactBaseV1):
    kind: Literal["support"]
    authority: Literal["mandatory_support"]
    approvalId: Id
    studentIds: Annotated[list[Id], Field(min_length=1)]
    requirement: Text


class ScheduleFactV1(FactBaseV1):
    kind: Literal["schedule"]
    authority: Literal["approved_schedule"]
    approvalId: Id
    lessonDate: date
    minutes: Annotated[int, Field(ge=1, le=180)]
    supersedesFactIds: list[Id]


class ResourceFactV1(FactBaseV1):
    kind: Literal["resource"]
    authority: Literal["approved_resource"]
    approvalId: Id
    skillIds: Annotated[list[Id], Field(min_length=1)]
    usage: Text


class TeamDecisionFactV1(FactBaseV1):
    kind: Literal["team_decision"]
    authority: Literal["team_decision"]
    decision: Text


class EnrichmentFactV1(FactBaseV1):
    kind: Literal["enrichment"]
    authority: Literal["public_reference"]
    recommendation: Text


ProviderFactV1 = Annotated[
    RosterFactV1 | ObservationFactV1 | AssessmentFactV1 | CurriculumFactV1 | SupportFactV1
    | ScheduleFactV1 | ResourceFactV1 | TeamDecisionFactV1 | EnrichmentFactV1,
    Field(discriminator="kind"),
]


class ProviderBatchV1(Contract):
    """Planned adapter output, not a claim about any vendor's wire API."""

    schemaVersion: Literal["instruct.provider.v1"]
    classId: Id
    assessmentId: Id
    source: Source
    requested: bool
    state: SourceState
    reason: Text | None
    durationMs: Annotated[int, Field(ge=0)]
    evidence: list[EvidenceV1]
    facts: list[ProviderFactV1]

    @model_validator(mode="after")
    def source_integrity(self) -> Self:
        if self.requested == (self.state == "not_requested"):
            raise ValueError("not_requested iff requested is false")
        if self.state != "succeeded" and (self.evidence or self.facts):
            raise ValueError("only succeeded batches expose evidence/facts")
        if self.state in {"disabled", "unavailable", "failed"} and self.reason is None:
            raise ValueError("non-successful requested source needs a safe reason")
        refs = {e.refId for e in self.evidence}
        _unique([e.refId for e in self.evidence], "evidence IDs")
        _unique([f.factId for f in self.facts], "fact IDs")
        facts_by_id = {f.factId: f for f in self.facts}
        allowed = {
            Source.FABRIC: {"roster", "observation", "assessment"},
            Source.FOUNDRY: {"curriculum", "support", "schedule", "resource"},
            Source.WORK: {"team_decision"}, Source.WEB: {"enrichment"},
        }
        for evidence in self.evidence:
            if evidence.source != self.source or evidence.classId != self.classId:
                raise ValueError("evidence source/class mismatch")
        for fact in self.facts:
            if fact.kind not in allowed[self.source] or not set(fact.evidenceRefs) <= refs:
                raise ValueError("fact source mismatch or dangling evidence reference")
            if isinstance(fact, (ObservationFactV1, AssessmentFactV1)) and fact.assessmentId != self.assessmentId:
                raise ValueError("observation assessment mismatch")
            if isinstance(fact, ScheduleFactV1):
                _unique(fact.supersedesFactIds, "superseded schedules")
                for superseded_id in fact.supersedesFactIds:
                    superseded = facts_by_id.get(superseded_id)
                    if (
                        not isinstance(superseded, ScheduleFactV1)
                        or superseded_id == fact.factId
                        or superseded.lessonDate != fact.lessonDate
                        or superseded.effectiveFrom >= fact.effectiveFrom
                    ):
                        raise ValueError("supersession must resolve to an earlier same-date schedule")
        return self


class ClaimV1(Contract):
    claimId: Id
    text: Text
    basis: Literal["supported_fact", "instructional_proposal"]
    factIds: list[Id]
    evidenceRefs: list[Id]

    @model_validator(mode="after")
    def factual_support(self) -> Self:
        _unique(self.factIds, "claim facts")
        _unique(self.evidenceRefs, "claim evidence references")
        if self.basis == "supported_fact" and (not self.factIds or not self.evidenceRefs):
            raise ValueError("factual claim requires facts and claim-level evidence")
        return self


class GroupV1(Contract):
    groupId: Id
    need: Literal[
        "insufficient_evidence", "graph_interpretation", "evidence_selection", "extension"
    ]
    provisional: Literal[True]
    studentIds: Annotated[list[Id], Field(min_length=1)]
    overlappingNeeds: dict[Id, list[Literal["graph_interpretation", "evidence_selection"]]]
    rationale: ClaimV1
    scaffold: ClaimV1

    @model_validator(mode="after")
    def unique_members(self) -> Self:
        _unique(self.studentIds, "group students")
        if not set(self.overlappingNeeds) <= set(self.studentIds):
            raise ValueError("overlap map must refer to group members")
        if self.rationale.basis != "supported_fact":
            raise ValueError("generated grouping rationale must be grounded")
        return self


class SegmentV1(Contract):
    segmentId: Id
    minutes: Annotated[int, Field(ge=1, le=35)]
    instruction: ClaimV1
    groupIds: list[Id]


class ExitTicketV1(Contract):
    prompt: ClaimV1
    answerKey: ClaimV1
    skillIds: Annotated[list[Id], Field(min_length=1)]


class TeachingPackageV1(Contract):
    objective: ClaimV1
    segments: Annotated[list[SegmentV1], Field(min_length=1)]
    exitTicket: ExitTicketV1
    implementedSupportFactIds: list[Id]
    appliedScheduleFactId: Id
    resourceFactIds: list[Id]

    @model_validator(mode="after")
    def total_minutes(self) -> Self:
        _unique([s.segmentId for s in self.segments], "segment IDs")
        _unique(self.implementedSupportFactIds, "implemented supports")
        _unique(self.resourceFactIds, "resource facts")
        for segment in self.segments:
            _unique(segment.groupIds, "segment groups")
        if sum(s.minutes for s in self.segments) != 35:
            raise ValueError("lesson segments must total 35 minutes, including exit ticket")
        return self


class IssueV1(Contract):
    issueId: Id
    code: Literal[
        "required_source_missing", "optional_source_missing", "insufficient_evidence",
        "authority_conflict", "unsupported_claim", "missing_required_fact",
    ]
    affected: Literal["groups", "lesson", "enrichment", "student_evidence"]
    blocking: bool
    message: Text
    factIds: list[Id]
    evidenceRefs: list[Id]
    resolution: Text


class PlanResultV1(Contract):
    schemaVersion: Literal["instruct.plan.v1"]
    planId: Id
    revision: Literal[1]
    requestId: Id
    principal: PrincipalScopeV1
    classId: Id
    assessmentId: Id
    scenario: ScenarioV1
    generatedAt: AwareDatetime
    executionMode: ExecutionMode
    status: Literal["complete", "partial", "blocked"]
    sources: Annotated[list[ProviderBatchV1], Field(min_length=4, max_length=4)]
    groups: list[GroupV1]
    package: TeachingPackageV1 | None
    issues: list[IssueV1]
    unresolvedQuestions: list[Text]

    @model_validator(mode="after")
    def result_integrity(self) -> Self:
        sources = {s.source: s for s in self.sources}
        if set(sources) != set(Source):
            raise ValueError("exactly one batch per source is required")
        if any(s.state == "running" for s in self.sources):
            raise ValueError("final result cannot contain a running source")
        for source in self.sources:
            if (source.classId, source.assessmentId) != (self.classId, self.assessmentId):
                raise ValueError("source class/assessment scope mismatch")
            if source.source in {Source.FABRIC, Source.FOUNDRY} and not source.requested:
                raise ValueError("Fabric and Foundry are required capabilities")
        facts = {f.factId: f for s in self.sources for f in s.facts}
        refs = {e.refId: e for s in self.sources for e in s.evidence}
        _unique([f.factId for s in self.sources for f in s.facts], "global fact IDs")
        _unique([e.refId for s in self.sources for e in s.evidence], "global evidence IDs")
        _unique([i.issueId for i in self.issues], "issue IDs")
        _unique([g.groupId for g in self.groups], "group IDs")
        if any(e.provenance.mode != self.executionMode for e in refs.values()):
            raise ValueError("evidence execution mode mismatch; no fallback mixing")
        for fact in facts.values():
            if fact.effectiveFrom > self.scenario.planningCutoff:
                raise ValueError("fact is not effective at the planning cutoff")
            if fact.effectiveTo is not None and fact.effectiveTo <= self.scenario.planningCutoff:
                # Historical schedules may be retained solely for visible supersession.
                if not isinstance(fact, ScheduleFactV1):
                    raise ValueError("expired facts cannot support this plan")
        if self.groups and sources[Source.FABRIC].state != "succeeded":
            raise ValueError("groups require successful Fabric retrieval")
        if self.package is not None and any(
            sources[s].state != "succeeded" for s in (Source.FABRIC, Source.FOUNDRY)
        ):
            raise ValueError("approved lesson requires both required sources")
        rosters = [f for f in facts.values() if isinstance(f, RosterFactV1)]
        students = set(rosters[0].studentIds) if len(rosters) == 1 else set()
        if self.groups:
            assigned = [sid for g in self.groups for sid in g.studentIds]
            if len(rosters) != 1 or set(assigned) != students or len(assigned) != len(students):
                raise ValueError("provisional primary groups must partition the class roster")
        for fact in facts.values():
            if len(rosters) == 1 and isinstance(fact, ObservationFactV1) and fact.studentId not in students:
                raise ValueError("observation student is not in roster")
            if len(rosters) == 1 and isinstance(fact, SupportFactV1) and not set(fact.studentIds) <= students:
                raise ValueError("support students are not in roster")
        claims = [c for g in self.groups for c in (g.rationale, g.scaffold)]
        if self.package is not None:
            package = self.package
            schedule = facts.get(package.appliedScheduleFactId)
            if not isinstance(schedule, ScheduleFactV1) or schedule.minutes != 35:
                raise ValueError("35-minute package requires an approved schedule fact")
            if schedule.lessonDate != date.fromisoformat(self.scenario.lessonDate):
                raise ValueError("schedule lesson date mismatch")
            if schedule.effectiveTo is not None and schedule.effectiveTo <= self.scenario.planningCutoff:
                raise ValueError("applied schedule is expired")
            supports = {f.factId for f in facts.values() if isinstance(f, SupportFactV1)}
            if set(package.implementedSupportFactIds) != supports:
                raise ValueError("all authorized supports must be represented")
            curricula = [f for f in facts.values() if isinstance(f, CurriculumFactV1)]
            if not curricula:
                raise ValueError("approved curriculum fact required")
            if package.objective.basis != "supported_fact" or not any(
                isinstance(facts.get(fid), CurriculumFactV1) for fid in package.objective.factIds
            ):
                raise ValueError("shared objective must cite approved curriculum")
            if not set(package.exitTicket.skillIds) <= {
                skill_id for curriculum in curricula for skill_id in curriculum.skillIds
            }:
                raise ValueError("exit ticket skills must belong to approved curriculum")
            if any(not isinstance(facts.get(fid), ResourceFactV1) for fid in package.resourceFactIds):
                raise ValueError("resources must be approved resource facts")
            group_ids = {g.groupId for g in self.groups}
            if not self.groups or any(not set(s.groupIds) <= group_ids for s in package.segments):
                raise ValueError("lesson group reference mismatch")
            claims += [
                package.objective, package.exitTicket.prompt, package.exitTicket.answerKey,
                *(s.instruction for s in package.segments),
            ]
        _unique([c.claimId for c in claims], "claim IDs")
        for item in [*claims, *self.issues]:
            if not set(item.factIds) <= facts.keys() or not set(item.evidenceRefs) <= refs.keys():
                raise ValueError("dangling claim/issue reference")
        for claim in claims:
            supporting_refs = {ref for fid in claim.factIds for ref in facts[fid].evidenceRefs}
            if set(claim.evidenceRefs) != supporting_refs:
                raise ValueError("claim references must match its supporting facts")
            if any(
                facts[fid].effectiveTo is not None
                and facts[fid].effectiveTo <= self.scenario.planningCutoff
                for fid in claim.factIds
            ):
                raise ValueError("expired historical facts cannot support current claims")
        usable = bool(self.groups or self.package)
        if self.status == "blocked" and (usable or not any(i.blocking for i in self.issues)):
            raise ValueError("blocked result has no usable output and needs a blocking issue")
        if self.status == "partial" and (not usable or not self.issues):
            raise ValueError("partial result retains usable output and names its limitations")
        if self.status == "complete" and (self.package is None or any(i.blocking for i in self.issues)):
            raise ValueError("complete result requires a full grounded core and no blocking issues")
        for source in self.sources:
            if source.state in {"disabled", "unavailable", "failed"}:
                required = source.source in {Source.FABRIC, Source.FOUNDRY}
                code = "required_source_missing" if required else "optional_source_missing"
                if not any(i.code == code and i.blocking == required for i in self.issues):
                    raise ValueError("source failure needs a correctly bounded issue")
                if self.status == "complete":
                    raise ValueError("missing requested capability must be partial or blocked")
        return self


class FinalEnvelopeV1(Contract):
    schemaVersion: Literal["instruct.final.v1"]
    requestId: Id
    result: PlanResultV1

    @model_validator(mode="after")
    def request_matches(self) -> Self:
        if self.requestId != self.result.requestId:
            raise ValueError("envelope request mismatch")
        return self


class ErrorV1(Contract):
    code: Literal[
        "unauthenticated", "forbidden", "not_found", "invalid_request",
        "auth_unavailable", "internal_error", "cancelled",
    ]
    message: Text
    retryable: bool


class ErrorEnvelopeV1(Contract):
    schemaVersion: Literal["instruct.error.v1"]
    requestId: Id
    error: ErrorV1


class ClassSummaryV1(Contract):
    classId: Id
    title: Text
    assessmentIds: list[Id]
    studentCount: Literal[24]


class ClassesEnvelopeV1(Contract):
    schemaVersion: Literal["instruct.classes.v1"]
    requestId: Id
    principal: PrincipalScopeV1
    classes: list[ClassSummaryV1]


class EvidenceEnvelopeV1(Contract):
    schemaVersion: Literal["instruct.evidence.v1"]
    requestId: Id
    principal: PrincipalScopeV1
    classId: Id
    planId: Id
    evidence: EvidenceV1

    @model_validator(mode="after")
    def class_matches(self) -> Self:
        if self.classId != self.evidence.classId:
            raise ValueError("evidence class mismatch")
        return self


class StartedEventV1(Contract):
    type: Literal["started"]
    schemaVersion: Literal["instruct.event.v1"]
    requestId: Id
    sequence: Literal[0]


class SourceEventV1(Contract):
    type: Literal["source"]
    schemaVersion: Literal["instruct.event.v1"]
    requestId: Id
    sequence: Annotated[int, Field(ge=1)]
    source: Source
    state: SourceState
    reason: Text | None

    @model_validator(mode="after")
    def safe_failure_reason(self) -> Self:
        if self.state in {"disabled", "unavailable", "failed"} and self.reason is None:
            raise ValueError("failed/disabled/unavailable progress needs a safe reason")
        return self


class FinalEventV1(Contract):
    type: Literal["final"]
    schemaVersion: Literal["instruct.event.v1"]
    requestId: Id
    sequence: Annotated[int, Field(ge=1)]
    payload: FinalEnvelopeV1

    @model_validator(mode="after")
    def request_matches(self) -> Self:
        if self.requestId != self.payload.requestId:
            raise ValueError("final event request mismatch")
        return self


class ErrorEventV1(Contract):
    type: Literal["error"]
    schemaVersion: Literal["instruct.event.v1"]
    requestId: Id
    sequence: Annotated[int, Field(ge=1)]
    payload: ErrorEnvelopeV1

    @model_validator(mode="after")
    def request_matches(self) -> Self:
        if self.requestId != self.payload.requestId:
            raise ValueError("error event request mismatch")
        if self.payload.error.code not in {"internal_error", "cancelled"}:
            raise ValueError("auth/request denials must occur before opening the stream")
        return self


StreamEventV1 = Annotated[
    StartedEventV1 | SourceEventV1 | FinalEventV1 | ErrorEventV1,
    Field(discriminator="type"),
]


class StreamTranscriptV1(Contract):
    """Development/acceptance representation; HTTP carries individual SSE frames."""

    events: Annotated[list[StreamEventV1], Field(min_length=2)]

    @model_validator(mode="after")
    def terminal_behavior(self) -> Self:
        if not isinstance(self.events[0], StartedEventV1):
            raise ValueError("stream must start with started")
        states: dict[Source, SourceState] = {}
        transitions = {
            "not_requested": set(), "disabled": set(), "unavailable": set(),
            "failed": set(), "running": {"succeeded", "failed", "unavailable"},
            "succeeded": set(),
        }
        for index, event in enumerate(self.events):
            if event.sequence != index or event.requestId != self.events[0].requestId:
                raise ValueError("stream sequence/request mismatch")
            terminal = isinstance(event, (FinalEventV1, ErrorEventV1))
            if terminal != (index == len(self.events) - 1):
                raise ValueError("exactly one final or error must terminate the stream")
            if isinstance(event, StartedEventV1) and index != 0:
                raise ValueError("duplicate started event")
            if isinstance(event, SourceEventV1):
                if event.source not in states and event.state not in {
                    "not_requested", "disabled", "unavailable", "running"
                }:
                    raise ValueError("active retrieval must announce running before its result")
                if event.source in states and event.state not in transitions[states[event.source]]:
                    raise ValueError("invalid source lifecycle transition")
                states[event.source] = event.state
        last = self.events[-1]
        if isinstance(last, FinalEventV1):
            expected = {s.source: s.state for s in last.payload.result.sources}
            if states != expected:
                raise ValueError("final must agree with all four terminal source states")
        return self


class DraftScopeV1(Contract):
    principal: PrincipalScopeV1
    classId: Id
    planId: Id
    schemaVersion: Literal["instruct.draft.v1"]


class EditChangeV1(Contract):
    path: Annotated[str, Field(pattern=(
        r"^/(groups/(0|[1-9][0-9]*)/(rationale/text|scaffold/text|studentIds)"
        r"|package/(objective/text|segments/(0|[1-9][0-9]*)/(minutes|instruction/text)"
        r"|exitTicket/(prompt|answerKey)/text))$"
    ))]
    before: str | int | list[Id]
    after: str | int | list[Id]
    provenance: Literal["teacher_edit_unverified"]


class EditRevisionV1(Contract):
    revision: Annotated[int, Field(ge=1)]
    editedAt: AwareDatetime
    editor: PrincipalScopeV1
    changes: Annotated[list[EditChangeV1], Field(min_length=1)]
    invalidatedClaimIds: Annotated[list[Id], Field(min_length=1)]


class ReviewV1(Contract):
    reviewer: PrincipalScopeV1
    reviewedAt: AwareDatetime
    editRevision: Annotated[int, Field(ge=0)]
    meaning: Literal["teacher_review_only_not_published"]


class DraftV1(Contract):
    schemaVersion: Literal["instruct.draft.v1"]
    scope: DraftScopeV1
    state: Literal["generated", "edited", "reviewed"]
    baseline: PlanResultV1
    baselineSha256: Digest
    edits: list[EditRevisionV1]
    review: ReviewV1 | None

    @model_validator(mode="after")
    def draft_integrity(self) -> Self:
        # Hash canonicalization is specified in the contract, not a new persistence layer.
        import hashlib
        import json

        scope, baseline = self.scope, self.baseline
        if (scope.principal, scope.classId, scope.planId) != (
            baseline.principal, baseline.classId, baseline.planId
        ):
            raise ValueError("draft scope differs from baseline")
        canonical = json.dumps(
            baseline.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != self.baselineSha256:
            raise ValueError("baseline hash mismatch")
        document = baseline.model_dump(mode="json")
        for revision, edit in enumerate(self.edits, start=1):
            if edit.revision != revision or edit.editor != scope.principal:
                raise ValueError("edit revision/editor mismatch")
            invalidated: set[str] = set()
            paths = [change.path for change in edit.changes]
            _unique(paths, "edit paths in revision")
            for change in edit.changes:
                parts = change.path.lstrip("/").split("/")
                target = document
                try:
                    for part in parts[:-1]:
                        target = target[int(part)] if isinstance(target, list) else target[part]
                    key = parts[-1]
                    old = target[key]
                except (KeyError, IndexError, ValueError, TypeError) as exc:
                    raise ValueError("edit path does not resolve") from exc
                if old != change.before or type(old) is not type(change.after) or old == change.after:
                    raise ValueError("edit before/type/change mismatch")
                if key == "text" and "claimId" in target:
                    if not str(change.after).strip():
                        raise ValueError("edited text must not be blank")
                    invalidated.add(target["claimId"])
                elif key == "studentIds" and "groupId" in target:
                    invalidated.add(target["rationale"]["claimId"])
                    rationale_path = "/" + "/".join(parts[:-1]) + "/rationale/text"
                    if rationale_path not in paths:
                        raise ValueError("membership edits require a changed rationale in that revision")
                elif key == "minutes" and "segmentId" in target:
                    if not isinstance(change.after, int) or not 1 <= change.after <= 35:
                        raise ValueError("edited segment minutes must be 1..35")
                    invalidated.add(target["instruction"]["claimId"])
                else:
                    raise ValueError("field is not teacher-editable")
                target[key] = change.after
            if set(edit.invalidatedClaimIds) != invalidated:
                raise ValueError("edit must identify exactly the invalidated generated claims")
            _unique(edit.invalidatedClaimIds, "invalidated claims")
            assigned = [sid for g in document["groups"] for sid in g["studentIds"]]
            if any(not g["studentIds"] for g in document["groups"]):
                raise ValueError("edited groups must not be empty")
            original = [sid for g in baseline.groups for sid in g.studentIds]
            if sorted(assigned) != sorted(original):
                raise ValueError("edited membership must preserve the roster partition")
            package = document["package"]
            if package and sum(s["minutes"] for s in package["segments"]) != 35:
                raise ValueError("edited lesson must remain 35 minutes")
        if self.state == "generated" and (self.edits or self.review is not None):
            raise ValueError("generated state has no edits or review")
        if self.state == "edited" and (not self.edits or self.review is not None):
            raise ValueError("editing invalidates review")
        if self.state == "reviewed":
            if self.review is None or self.review.editRevision != len(self.edits):
                raise ValueError("review must bind to the current edit revision")
            if self.review.reviewer != scope.principal:
                raise ValueError("reviewer must match scoped principal")
        elif self.review is not None:
            raise ValueError("review is only present in reviewed state")
        return self


class ExportV1(Contract):
    schemaVersion: Literal["instruct.export.v1"]
    format: Literal["json", "markdown"]
    exportedAt: AwareDatetime
    draft: DraftV1
    markdown: Text | None

    @model_validator(mode="after")
    def export_shape(self) -> Self:
        if (self.format == "markdown") != (self.markdown is not None):
            raise ValueError("Markdown export requires rendered text; JSON is lossless draft only")
        return self


EXAMPLE_MODELS: dict[str, type[BaseModel]] = {
    "request": PlanRequestV1,
    "provider": ProviderBatchV1,
    "complete": FinalEnvelopeV1,
    "partial": FinalEnvelopeV1,
    "blocked": FinalEnvelopeV1,
    "stream": StreamTranscriptV1,
    "error": ErrorEnvelopeV1,
    "draft": DraftV1,
    "export": ExportV1,
}


def validate_examples(directory: str) -> list[str]:
    """Bounded offline import/schema/example check; never called by runtime routes."""
    from pathlib import Path

    validated = []
    for name, model in EXAMPLE_MODELS.items():
        model.model_json_schema()
        model.model_validate_json((Path(directory) / f"{name}.json").read_text(encoding="utf-8"))
        validated.append(name)
    TypeAdapter(StreamEventV1).json_schema()
    return validated
