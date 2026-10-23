"""Instructional routes; authorization finishes before SSE response construction."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from functools import lru_cache
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app.auth import AuthenticatedUser
from app.config import get_settings
from app.instruct_auth import authorize, memberships, principal, require_instruct_user
from app.instruct_contracts import (
    ClassesEnvelopeV1, ErrorEnvelopeV1, ErrorEventV1, ErrorV1, EvidenceEnvelopeV1,
    FinalEnvelopeV1, FinalEventV1, PlanRequestV1, SourceEventV1, StartedEventV1,
)
from app.instruct_runtime import InstructRuntime
from app.instruct_conversation import (
    ConversationRequestV1, ConversationResponseV1, intent, respond,
)

router = APIRouter(prefix="/api/instruct/v1")
logger = logging.getLogger(__name__)


@router.post("/chat")
async def chat(request: Request, user: AuthenticatedUser = Depends(require_instruct_user)):
    from app.instruct_chat import ChatRequest, chat_service
    raw = await request.body()
    if len(raw) > 10_000:
        raise HTTPException(422, "Invalid request")
    try:
        body = ChatRequest.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid request") from None
    if "text/event-stream" in request.headers.get("accept", ""):
        # Authenticate and resolve the caller's grants before starting the stream.
        settings, runtime = get_settings(), get_instruct_runtime()
        memberships(settings, user)
        rid = request_id(request)

        async def generate():
            queue = asyncio.Queue()
            sequence = 0

            async def produce():
                try:
                    result = await chat_service.run(
                        body, user, settings, runtime,
                        on_progress=lambda event: queue.put_nowait(("progress", event.model_dump(mode="json"))),
                        request_id=rid,
                    )
                    queue.put_nowait(("final", result.model_dump(mode="json")))
                except HTTPException as exc:
                    queue.put_nowait(("error", {
                        "message": exc.detail, "status": exc.status_code,
                    }))
                except Exception:
                    logger.exception("Chat stream failed: request_id=%s", rid)
                    queue.put_nowait(("error", {
                        "message": "Chat could not complete. No simulated answer was used.", "status": 500,
                    }))

            task = asyncio.create_task(produce())
            try:
                yield {"event": "started", "data": json.dumps({
                    "schemaVersion": "instruct.chat.event.v1", "requestId": rid,
                    "sequence": sequence, "type": "started",
                })}
                while True:
                    kind, payload = await queue.get()
                    sequence += 1
                    yield {"event": kind, "data": json.dumps({
                        "schemaVersion": "instruct.chat.event.v1", "requestId": rid,
                        "sequence": sequence, "type": kind, "payload": payload,
                    })}
                    if kind in {"final", "error"}:
                        break
            finally:
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return EventSourceResponse(generate(), headers={"Cache-Control": "no-store"})
    task = asyncio.create_task(chat_service.run(
        body, user, get_settings(), get_instruct_runtime(), request_id=request_id(request),
    ))
    try:
        while not task.done():
            if await request.is_disconnected():
                raise asyncio.CancelledError
            await asyncio.wait({task}, timeout=0.05)
        return await task
    except HTTPException as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={
            "schemaVersion": "instruct.error.v1", "requestId": request_id(request),
            "error": {"code": "chat_unavailable" if exc.status_code == 503 else "chat_request_failed",
                      "message": exc.detail, "retryable": exc.status_code >= 500},
        })
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@lru_cache(maxsize=1)
def get_instruct_runtime():
    return InstructRuntime(get_settings())


def request_id(request: Request):
    if not hasattr(request.state, "instruct_request_id"):
        request.state.instruct_request_id = str(uuid4())
    return request.state.instruct_request_id


def error_envelope(request: Request, status: int):
    codes = {401: "unauthenticated", 403: "forbidden", 404: "not_found",
             422: "invalid_request", 503: "auth_unavailable"}
    messages = {401: "Authentication required.", 403: "Access denied.",
                404: "Resource not found.", 422: "Invalid request.",
                503: "Authorization unavailable."}
    return ErrorEnvelopeV1(
        schemaVersion="instruct.error.v1", requestId=request_id(request),
        error=ErrorV1(code=codes.get(status, "internal_error"),
                      message=messages.get(status, "Request failed."),
                      retryable=status >= 500),
    )


async def read_plan(request: Request) -> PlanRequestV1:
    # FastAPI's Python-mode validation rejects strict ISO datetime JSON fields.
    try:
        return PlanRequestV1.model_validate_json(await request.body())
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None


async def read_conversation(request: Request) -> ConversationRequestV1:
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(422, "Invalid request")
    try:
        return ConversationRequestV1.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None


@router.post("/conversation", response_model=ConversationResponseV1)
async def conversation(request: Request, user: AuthenticatedUser = Depends(require_instruct_user),
                       body: ConversationRequestV1 = Depends(read_conversation)):
    context = body.context
    grant = authorize(get_settings(), user, context.classId, context.assessmentId)
    runtime, rid = get_instruct_runtime(), request_id(request)
    if intent(body.message) == "plan":
        try:
            envelope = await execute_with_disconnect(request, runtime, context, grant, rid)
            current = authorize(get_settings(), user, context.classId, context.assessmentId)
            if current.membershipRevision != grant.membershipRevision:
                raise HTTPException(404, "Resource not found")
            runtime.references.put(envelope, current)
            return ConversationResponseV1(
                requestId=rid, principal=current.principal, classId=context.classId,
                assessmentId=context.assessmentId, intent="plan", plan=envelope,
                message=f"Generated a live-grounded {envelope.result.status} baseline. Review the canvas and source limitations; nothing is published.",
                followups=["What needs reteaching", "Explain grouping", "Help me differentiate"],
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(500, "Request failed") from None
    baseline = None
    if body.artifact:
        baseline = runtime.references.plan(grant, body.artifact.planId)
        if baseline is None or baseline.assessmentId != context.assessmentId:
            raise HTTPException(404, "Resource not found")
    try:
        return respond(body, baseline, rid, grant)
    except (ValueError, TypeError, KeyError, IndexError):
        raise HTTPException(422, "Invalid request") from None


@router.get("/classes", response_model=ClassesEnvelopeV1)
async def classes(request: Request, user: AuthenticatedUser = Depends(require_instruct_user)):
    return ClassesEnvelopeV1(
        schemaVersion="instruct.classes.v1", requestId=request_id(request),
        principal=principal(user),
        classes=[m.classroom for m in memberships(get_settings(), user)],
    )


async def execute_with_disconnect(request, runtime, body, grant, rid):
    task = asyncio.create_task(runtime.execute(body, grant, rid))
    try:
        while not task.done():
            if await request.is_disconnected():
                raise asyncio.CancelledError
            await asyncio.wait({task}, timeout=0.05)
        return await task
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@router.post("/plan", response_model=FinalEnvelopeV1)
async def plan(request: Request, user: AuthenticatedUser = Depends(require_instruct_user),
               body: PlanRequestV1 = Depends(read_plan)):
    grant = authorize(get_settings(), user, body.classId, body.assessmentId)
    runtime = get_instruct_runtime()
    try:
        envelope = await execute_with_disconnect(request, runtime, body, grant, request_id(request))
        # A revoked/revised grant cannot publish retrieved content.
        current = authorize(get_settings(), user, body.classId, body.assessmentId)
        if current.membershipRevision != grant.membershipRevision:
            raise HTTPException(404, "Resource not found")
        runtime.references.put(envelope, current)
        return envelope
    except asyncio.CancelledError:
        raise
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Request failed") from None


@router.post("/plan/stream")
async def stream(request: Request, user: AuthenticatedUser = Depends(require_instruct_user),
                 body: PlanRequestV1 = Depends(read_plan)):
    grant = authorize(get_settings(), user, body.classId, body.assessmentId)
    runtime = get_instruct_runtime()
    rid = request_id(request)

    async def generate():
        sequence = 0

        def frame(event):
            return {"event": event.type, "data": event.model_dump_json()}

        def source_event(source, state, reason=None):
            nonlocal sequence
            sequence += 1
            return frame(SourceEventV1(
                type="source", schemaVersion="instruct.event.v1", requestId=rid,
                sequence=sequence, source=source, state=state, reason=reason,
            ))

        yield frame(StartedEventV1(
            type="started", schemaVersion="instruct.event.v1", requestId=rid, sequence=0,
        ))
        for context in runtime.contexts(body, grant):
            yield source_event(context.source, "running" if runtime.selected(body, context.source)
                               else "not_requested")
        try:
            # EventSourceResponse owns disconnect cancellation; do not race its receive loop.
            envelope = await runtime.execute(body, grant, rid)
            current = authorize(get_settings(), user, body.classId, body.assessmentId)
            if current.membershipRevision != grant.membershipRevision:
                raise ValueError("membership changed")
            for batch in envelope.result.sources:
                if batch.requested:
                    yield source_event(batch.source, batch.state, batch.reason)
            runtime.references.put(envelope, current)
            sequence += 1
            yield frame(FinalEventV1(
                type="final", schemaVersion="instruct.event.v1", requestId=rid,
                sequence=sequence, payload=envelope,
            ))
        except asyncio.CancelledError:
            # A disconnected client cannot receive a terminal frame. Never synthesize final.
            raise
        except Exception:
            sequence += 1
            yield frame(ErrorEventV1(
                type="error", schemaVersion="instruct.event.v1", requestId=rid,
                sequence=sequence, payload=error_envelope(request, 500),
            ))

    return EventSourceResponse(generate(), headers={"Cache-Control": "no-store"})


@router.get("/classes/{class_id}/plans/{plan_id}/evidence/{ref_id}",
            response_model=EvidenceEnvelopeV1)
async def evidence(class_id: str, plan_id: str, ref_id: str, request: Request,
                   user: AuthenticatedUser = Depends(require_instruct_user)):
    grant = authorize(get_settings(), user, class_id)
    found = get_instruct_runtime().references.get(grant, plan_id, ref_id)
    if found is None:
        raise HTTPException(404, "Resource not found")
    assessment_id, item = found
    authorize(get_settings(), user, class_id, assessment_id)
    return EvidenceEnvelopeV1(
        schemaVersion="instruct.evidence.v1", requestId=request_id(request),
        principal=principal(user), classId=class_id, planId=plan_id, evidence=item,
    )
