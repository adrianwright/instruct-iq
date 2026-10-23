"""Bounded command routing, not a general-purpose language model or evidence source."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import Field

from app.instruct_contracts import (
    Contract, Digest, DraftV1, EditChangeV1, EditRevisionV1, FinalEnvelopeV1,
    Id, PlanRequestV1, PrincipalScopeV1, Text,
)

COMMANDS = {
    "plan": ("plan my next lesson", "build instructional plan", "regenerate plan"),
    "reteach": ("what needs reteaching", "what needs reteaching?"),
    "differentiate": ("help me differentiate",),
    "explain": ("explain grouping", "why these groups", "why these groups?"),
    "shorter_intro": ("make the intro shorter", "shorten the intro", "revise intro shorter"),
    "graph_scaffolding": ("add more graph scaffolding", "more graph scaffolding"),
}
FOLLOWUPS = ["Explain grouping", "Make the intro shorter", "Add more graph scaffolding"]


class ArtifactV1(Contract):
    planId: Id
    baselineSha256: Digest
    edits: Annotated[list[EditRevisionV1], Field(max_length=50)]


class ConversationRequestV1(Contract):
    schemaVersion: Literal["instruct.conversation.request.v1"]
    context: PlanRequestV1
    message: Annotated[str, Field(min_length=1, max_length=500)]
    artifact: ArtifactV1 | None = None


class ProposalV1(Contract):
    planId: Id
    baselineSha256: Digest
    editRevision: int
    changes: list[EditChangeV1]


class ConversationResponseV1(Contract):
    schemaVersion: Literal["instruct.conversation.v1"] = "instruct.conversation.v1"
    requestId: Id
    principal: PrincipalScopeV1
    classId: Id
    assessmentId: Id
    mode: Literal["bounded_commands"] = "bounded_commands"
    intent: str
    message: Text
    evidenceRefs: list[Id] = []
    followups: list[str] = []
    plan: FinalEnvelopeV1 | None = None
    proposal: ProposalV1 | None = None


def intent(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower()).rstrip(".!")
    return next((key for key, values in COMMANDS.items() if normalized in values), "unsupported")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def resolved_document(plan, artifact):
    """Bind edits to the authorized server snapshot, never client-asserted evidence."""
    if artifact.baselineSha256 != digest(plan.model_dump(mode="json")):
        raise ValueError("baseline mismatch")
    if any(len(e.changes) > 100 or any(
        isinstance(c.after, str) and len(c.after) > 12000 for c in e.changes
    ) for e in artifact.edits):
        raise ValueError("edit limit")
    DraftV1(
        schemaVersion="instruct.draft.v1",
        scope={"principal": plan.principal, "classId": plan.classId,
               "planId": plan.planId, "schemaVersion": "instruct.draft.v1"},
        state="edited" if artifact.edits else "generated", baseline=plan,
        baselineSha256=artifact.baselineSha256, edits=artifact.edits, review=None,
    )
    document = plan.model_dump(mode="json")
    for edit in artifact.edits:
        for change in edit.changes:
            target = document
            parts = change.path.lstrip("/").split("/")
            for part in parts[:-1]:
                target = target[int(part)] if isinstance(target, list) else target[part]
            target[parts[-1]] = change.after
    return document


def respond(body, plan, rid, grant):
    command = intent(body.message)
    response = ConversationResponseV1(
        requestId=rid, principal=grant.principal, classId=body.context.classId,
        assessmentId=body.context.assessmentId, intent=command,
        message="Supported commands only; no general chat model is connected. Choose a suggested command.",
        followups=["Plan my next lesson", "What needs reteaching", "Help me differentiate"],
    )
    if command == "unsupported":
        return response
    if plan is None:
        response.message = "Generate a plan first for the selected class and assessment."
        response.followups = ["Plan my next lesson"]
        return response
    document = resolved_document(plan, body.artifact)
    response.followups = FOLLOWUPS
    if command in {"explain", "reteach", "differentiate"}:
        lines, refs = [], set()
        for group in plan.groups:
            if command == "reteach" and group.need == "extension":
                continue
            if command == "differentiate":
                detail = group.scaffold.text
                refs.update(group.scaffold.evidenceRefs)
            else:
                observations = [f for source in plan.sources for f in source.facts
                                if f.kind == "observation" and f.factId in group.rationale.factIds]
                samples = observations[:2]
                detail = " ".join(
                    f"{f.studentId}, item {f.itemId}: {f.outcome} ({f.attemptId or 'no attempt'})."
                    for f in samples
                )
                refs.update(ref for f in samples for ref in f.evidenceRefs)
                # The full selected item trail remains visible on the canvas.
                detail += " Open the canvas rationale for every selected item and overlapping need."
                if not samples:
                    refs.update(group.rationale.evidenceRefs)
            lines.append(f"{group.need.replace('_', ' ')} ({len(group.studentIds)} learners): {detail}")
        response.message = (
            "Authorized generated baseline, not a revalidation of teacher edits. "
            "Missing submissions are not incorrect answers; groups are provisional.\n\n"
            + ("\n\n".join(lines) or "No grounded groups are available; resolve blocking sources and regenerate.")
        )[:12000]
        response.evidenceRefs = sorted(refs)
        return response
    package = document["package"]
    if package is None or any(issue.blocking for issue in plan.issues):
        response.message = "Resolve blocking evidence or policy issues and regenerate before requesting a lesson revision."
        return response
    segments = package["segments"]
    changes = []

    def change(path, before, after):
        if before != after:
            changes.append(EditChangeV1(path=path, before=before, after=after,
                                        provenance="teacher_edit_unverified"))

    if command == "shorter_intro":
        launch = next((i for i, s in enumerate(segments) if s["segmentId"] == "launch"), None)
        practice = next((i for i, s in enumerate(segments) if s["segmentId"] == "practice"), None)
        if launch is None or practice is None or segments[launch]["minutes"] <= 2:
            response.message = "The introduction cannot safely be shortened further. Keep at least two minutes and edit timings manually."
            return response
        reduction = min(2, segments[launch]["minutes"] - 2)
        for index, delta in ((launch, -reduction), (practice, reduction)):
            before = segments[index]["minutes"]
            change(f"/package/segments/{index}/minutes", before, before + delta)
        response.message = f"Proposal: move {reduction} introduction minutes to practice; total remains 35. Instructions, objective and required supports stay intact. Review before applying."
    else:
        model = next((i for i, s in enumerate(segments) if s["segmentId"] == "model"), None)
        if model is None:
            response.message = "No model segment is available for this supported revision."
            return response
        addition = " Graph scaffold: label each axis and its units, trace two plotted values, describe the trend aloud, then fade the prompts during practice."
        before = segments[model]["instruction"]["text"]
        if addition.strip() in before or len(before + addition) > 12000:
            response.message = "This scaffold is already present or the instruction is at its length limit. Keep the current plan or edit manually."
            return response
        change(f"/package/segments/{model}/instruction/text", before, before + addition)
        response.message = "Proposal: add an axes → values → trend worked-example scaffold to modelling. Existing teacher text, timing, objective and supports are retained; this is an unverified instructional suggestion."
    response.proposal = ProposalV1(
        planId=plan.planId, baselineSha256=body.artifact.baselineSha256,
        editRevision=len(body.artifact.edits), changes=changes,
    )
    return response
