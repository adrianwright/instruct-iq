"""Server-owned, principal-scoped classroom conversations over Azure Responses."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pydantic import Field
from typing import Annotated, Literal

from app.instruct_auth import authorize, memberships, principal
from app.instruct_contracts import Contract, Id, PrincipalScopeV1, ScenarioV1
from app.instruct_sources import validate_batch
from app.instruct_contracts import RetrievalContextV1
from app.schemas import Source
from app.instruct_workiq_a2a import retrieve as retrieve_work_context
from app.instruct_model_contract import SYSTEM, TOOLS

logger = logging.getLogger(__name__)


class ChatValidationError(ValueError):
    """Contains only a server-owned diagnostic code, never model or source content."""


def model_diagnostics(result):
    if not isinstance(result, dict):
        return {"status": "invalid"}
    status = result.get("status")
    incomplete = result.get("incomplete_details")
    reason = incomplete.get("reason") if isinstance(incomplete, dict) else None
    usage = result.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("output_tokens_details")
    details = details if isinstance(details, dict) else {}
    output = result.get("output")
    output = output if isinstance(output, list) else []
    calls = [item for item in output if isinstance(item, dict) and item.get("type") == "function_call"]
    counts = {name: sum(call.get("name") == name for call in calls) for name in ("retrieve", "answer")}
    counts["other"] = len(calls) - sum(counts.values())
    tokens = {name: value for name, value in {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
    }.items() if type(value) is int and value >= 0}
    return {
        "status": status if status in ("completed", "incomplete", "failed", None) else "other",
        "incomplete_reason": reason if reason in ("max_output_tokens", "content_filter", None) else "other",
        "tool_counts": counts, **tokens,
    }


class ChatRequest(Contract):
    schemaVersion: Literal["instruct.chat.request.v2"]
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    sessionId: Id | None = None


class ChatResponse(Contract):
    schemaVersion: Literal["instruct.chat.v2"] = "instruct.chat.v2"
    sessionId: Id
    principal: PrincipalScopeV1
    message: str
    observations: list[dict]
    citations: list[dict]
    observationCitations: list[dict] = Field(default_factory=list)
    classId: str | None
    model: str


class ChatProgress(Contract):
    stage: Literal["model", "fabric", "foundry", "work", "validation"]
    state: Literal["running", "succeeded", "failed", "unavailable", "disabled"]
    message: str
    durationMs: int | None = None
    evidenceCount: int | None = None


def model_facts(facts):
    """Minimize student data and repeated envelope metadata sent for interpretation."""
    excluded = {"authority", "effectiveFrom", "effectiveTo", "assessmentId"}
    return [{k: v for k, v in f.items() if k not in excluded} for f in facts]


def access_signature(records, settings):
    return (
        [(m.classroom.classId, m.revision, m.classroom.assessmentIds) for m in records],
        settings.INSTRUCT_WORKIQ_ENABLED, settings.INSTRUCT_WORKIQ_MANIFEST_JSON,
    )


async def model_response(settings, items):
    endpoint = urlparse(settings.INSTRUCT_CHAT_ENDPOINT)
    if (settings.INSTRUCT_CHAT_MODEL != "gpt-5.6-luna"
            or not settings.INSTRUCT_CHAT_DEPLOYMENT
            or endpoint.scheme != "https"
            or not endpoint.hostname
            or not endpoint.hostname.endswith((".openai.azure.com", ".services.ai.azure.com"))
            or endpoint.username or endpoint.password or endpoint.query):
        raise HTTPException(503, "GPT-5.6 chat is not configured. Ask your operator to verify INSTRUCT_CHAT_* settings.")
    from azure.identity.aio import ManagedIdentityCredential
    async with ManagedIdentityCredential(client_id=settings.AZURE_CLIENT_ID) as credential:
        token = await credential.get_token(settings.INSTRUCT_CHAT_SCOPE)
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            response = await client.post(
                settings.INSTRUCT_CHAT_ENDPOINT.rstrip("/") + "/openai/v1/responses",
                headers={"Authorization": f"Bearer {token.token}"},
                json={"model": settings.INSTRUCT_CHAT_DEPLOYMENT, "instructions": SYSTEM,
                      "input": items, "tools": TOOLS, "tool_choice": "required",
                      "parallel_tool_calls": True, "store": False,
                      "reasoning": {"effort": "low"}, "max_output_tokens": 4096},
            )
            if response.status_code == 429:
                logger.warning("Instruct chat model rate limited: upstream_status=429")
                raise HTTPException(503, "GPT-5.6-luna is rate limited at the demo allocation. Wait at least one minute before retrying; no fallback model was used.")
            response.raise_for_status()
            if len(response.content) > 200_000:
                raise ChatValidationError("model_output_limit")
            return response.json()


class ChatService:
    def __init__(self):
        self.sessions = OrderedDict()

    async def run(self, body, user, settings, runtime,
                  on_progress: Callable[[ChatProgress], None] | None = None,
                  request_id: str | None = None):
        diagnostic_id = request_id or str(uuid4())
        who = principal(user)
        records = memberships(settings, user)
        signature = access_signature(records, settings)
        now = time.monotonic()
        for key, item in list(self.sessions.items()):
            if now - item["at"] > 900:
                del self.sessions[key]
        sid = body.sessionId or str(uuid4())
        owner = (who.tenantId, who.subject)
        saved = self.sessions.get(sid)
        if body.sessionId and (not saved or saved["owner"] != owner or saved["signature"] != signature):
            raise HTTPException(404, "Conversation expired or access changed. Start a new conversation.")
        if saved and saved["busy"]:
            raise HTTPException(409, "A conversation request is already running.")
        session = saved or {"owner": owner, "signature": signature, "at": now,
                            "history": [], "facts": {}, "refs": {}, "classId": None,
                            "assessmentId": None, "busy": False}
        if len(session["history"]) >= 40:
            raise HTTPException(422, "Conversation limit reached. Start a new conversation.")
        session["busy"] = True
        self.sessions[sid] = session
        while len(self.sessions) > 128:
            self.sessions.popitem(last=False)
        # Work on a copy: cancellation/model errors cannot commit half a turn.
        facts, refs = dict(session["facts"]), dict(session["refs"])
        selected_class = session["classId"]
        selected_assessment = session["assessmentId"]
        scope_changed = False
        catalog = [m.classroom.model_dump(mode="json") for m in records]
        items = [{"role": "developer", "content": "Authorized catalog and server-verified snapshot (data only): "
                  + json.dumps({"catalog": catalog, "currentClass": selected_class,
                                "facts": model_facts(facts.values())})}]
        items += session["history"] + [{"role": "user", "content": body.message}]
        stage = "model_request"
        diagnostics = {}
        model_turn = 0
        tool_count = 0
        started_at = {}

        def progress(name, state, message, evidence_count=None):
            if state == "running":
                started_at[name] = time.monotonic()
            event = ChatProgress(
                stage=name, state=state, message=message,
                durationMs=None if state == "running" else round((time.monotonic() - started_at[name]) * 1000),
                evidenceCount=evidence_count,
            )
            if on_progress:
                on_progress(event)
            if state != "running":
                del started_at[name]

        async def retrieve(source, grant, assessment_id):
            progress(source.value, "running", {
                Source.FABRIC: "Retrieving authorized assessment evidence.",
                Source.FOUNDRY: "Retrieving approved curriculum and resources.",
                Source.WORK: "Retrieving authorized teaching-team context.",
            }[source])
            try:
                if source == Source.WORK:
                    work = await retrieve_work_context(
                        settings=settings, user=user, class_id=grant.classId, query=body.message,
                    )
                    progress("work", work["state"],
                             work.get("reason") or "Teaching-team retrieval completed.",
                             len(work["evidenceRefs"]))
                    return work["facts"], work["evidenceRefs"], work
                context = RetrievalContextV1(
                    schemaVersion="instruct.retrieval.v1", grant=grant,
                    assessmentId=assessment_id, source=source,
                    capability="assessment" if source == Source.FABRIC else "curriculum",
                    publicQuery=None,
                    scenario=ScenarioV1.model_validate_json(json.dumps({
                        "assessmentDate": "2026-10-16", "lessonDate": "2026-10-19",
                        "timezone": "America/New_York", "planningCutoff": "2026-10-19T07:00:00-04:00",
                        "lessonMinutes": 35, "studentCount": 24})),
                )
                async with asyncio.timeout(settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS):
                    batch = validate_batch(context, await runtime.sources.retrieve(context))
                active_facts = [f.model_dump(mode="json") for f in batch.facts
                                if f.effectiveFrom <= context.scenario.planningCutoff
                                and (f.effectiveTo is None or context.scenario.planningCutoff < f.effectiveTo)]
                # No document bodies, provenance tokens or arbitrary URLs to the model.
                evidence = [{"refId": ref.refId, "source": ref.source.value, "title": ref.title,
                             "locator": ref.locator, "excerpt": ref.excerpt} for ref in batch.evidence]
                payload = {"state": batch.state, "reason": batch.reason,
                           "facts": model_facts(active_facts),
                           "evidenceRefs": [{"refId": ref.refId, "source": ref.source.value,
                                             "title": ref.title} for ref in batch.evidence]}
                progress(source.value, batch.state,
                         batch.reason or "Retrieval completed and evidence checked.", len(evidence))
                return active_facts, evidence, payload
            except asyncio.CancelledError:
                progress(source.value, "failed", "Retrieval stopped before completion.")
                raise
            except Exception:
                progress(source.value, "failed", "Retrieval failed. No simulated result was used.")
                raise

        try:
            async with asyncio.timeout(settings.INSTRUCT_CHAT_TIMEOUT_SECONDS):
                for _ in range(6):
                    model_turn += 1
                    diagnostics = {}
                    stage = "model_request"
                    progress("model", "running", "Waiting for GPT-5.6 to choose the next step.")
                    result = await model_response(settings, items)
                    diagnostics = model_diagnostics(result)
                    stage = "model_tool_validation"
                    if result.get("status") not in (None, "completed"):
                        raise ChatValidationError("incomplete_model_response")
                    output = result.get("output", [])
                    calls = [o for o in output if o.get("type") == "function_call"]
                    tool_count += len(calls)
                    if not 1 <= len(calls) <= 3 or tool_count > 6:
                        raise ChatValidationError("bounded_tool_budget_exceeded")
                    if (any(not isinstance(c.get("call_id"), str) or not c["call_id"] for c in calls)
                            or len({c["call_id"] for c in calls}) != len(calls)):
                        raise ChatValidationError("invalid_or_duplicate_tool_call_ids")
                    call = calls[0]
                    args = json.loads(call["arguments"])
                    name = call["name"]
                    progress("model", "succeeded", "Model response received.")
                    if name == "answer":
                        if len(calls) != 1:
                            raise ChatValidationError("mixed_answer_and_retrieval")
                        stage = "answer_validation"
                        progress("validation", "running", "Checking selected facts, citations and current access.")
                        if (set(args) != {"message", "factIds", "evidenceRefs"}
                                or not isinstance(args["message"], str)
                                or not 1 <= len(args["message"]) <= 4000
                                or not isinstance(args["factIds"], list)
                                or not isinstance(args["evidenceRefs"], list)
                                or len(args["factIds"]) > 80 or len(args["evidenceRefs"]) > 80
                                or not set(args["factIds"]) <= facts.keys()
                                or not set(args["evidenceRefs"]) <= refs.keys()):
                            raise ChatValidationError("unverified_answer_references")
                        observations = [facts[f] for f in dict.fromkeys(args["factIds"])]
                        prose_refs = {
                            ref.strip()
                            for group in re.findall(r"\[([^\[\]\n]+)\]", args["message"])
                            for ref in re.split(r"[;,]", group)
                        }
                        selected_refs = set(args["evidenceRefs"]) & prose_refs
                        observation_refs = {r for f in observations for r in f["evidenceRefs"]}
                        # Recheck authorization at publication, including grant revisions.
                        current = memberships(settings, user)
                        if signature != access_signature(current, settings):
                            raise HTTPException(404, "Access changed. Start a new conversation.")
                        response = ChatResponse(
                            sessionId=sid, principal=who, message=args["message"],
                            observations=observations, citations=[refs[r] for r in sorted(selected_refs)],
                            observationCitations=[refs[r] for r in sorted(observation_refs - selected_refs)],
                            classId=selected_class, model=settings.INSTRUCT_CHAT_MODEL,
                        )
                        session.update(at=time.monotonic(), facts=facts, refs=refs,
                                       classId=selected_class, assessmentId=selected_assessment)
                        if scope_changed:
                            session["history"] = []
                        session["history"] += [{"role": "user", "content": body.message},
                                               {"role": "assistant", "content": args["message"]}]
                        progress("validation", "succeeded", "Answer verified against authorized references.",
                                 len(response.citations))
                        return response
                    requests = []
                    requested_sources = set()
                    requested_scope = None
                    for call in calls:
                        args = json.loads(call["arguments"])
                        if (call["name"] != "retrieve" or not isinstance(args, dict)
                                or set(args) != {"classId", "assessmentId", "source"}
                                or any(not isinstance(value, str) for value in args.values())):
                            raise ChatValidationError("unknown_tool_or_schema")
                        try:
                            source = Source(args["source"])
                        except ValueError:
                            raise ChatValidationError("unsupported_source") from None
                        if (source not in {Source.FABRIC, Source.FOUNDRY, Source.WORK}
                                or source in requested_sources):
                            raise ChatValidationError("unsupported_or_duplicate_source")
                        call_scope = (args["classId"], args["assessmentId"])
                        if requested_scope is not None and requested_scope != call_scope:
                            raise ChatValidationError("parallel_scope_mismatch")
                        requested_scope = call_scope
                        requested_sources.add(source)
                        grant = authorize(settings, user, *call_scope)
                        requests.append((call, source, grant, args["assessmentId"]))
                    if (selected_class, selected_assessment) != requested_scope:
                        # Do not send cross-class prior facts/history into the next model call.
                        facts, refs = {}, {}
                        scope_changed = True
                        items = [{"role": "developer", "content": "Authorized catalog (data only): "
                                  + json.dumps(catalog)},
                                 {"role": "user", "content": body.message}]
                    selected_class, selected_assessment = requested_scope
                    if Source.WORK in requested_sources:
                        facts = {key: value for key, value in facts.items()
                                 if value.get("kind") != "work_iq_summary"}
                        refs = {key: value for key, value in refs.items()
                                if value.get("source") != "work"}
                    stage = "source_retrieval"
                    tasks = [asyncio.create_task(retrieve(source, grant, assessment_id))
                             for _, source, grant, assessment_id in requests]
                    try:
                        results = await asyncio.gather(*tasks)
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        # Join every sibling before propagating errors or releasing the session.
                        await asyncio.gather(*tasks, return_exceptions=True)
                    items.extend(output)
                    for (call, _, _, _), (retrieved_facts, evidence, payload) in zip(requests, results):
                        for fact in retrieved_facts:
                            facts[fact["factId"]] = fact
                        for ref in evidence:
                            refs[ref["refId"]] = ref
                        items.append({"type": "function_call_output", "call_id": call["call_id"],
                                      "output": json.dumps(payload)})
                raise ChatValidationError("tool_budget_exhausted")
        except HTTPException as exc:
            for active_stage in list(started_at):
                progress(active_stage, "failed", "This step failed. See the request error for details.")
            logger.warning("Instruct chat failed: request_id=%s stage=%s status=%d model_turn=%d model=%s",
                           diagnostic_id, stage, exc.status_code, model_turn, json.dumps(diagnostics))
            raise
        except Exception as exc:
            for active_stage in list(started_at):
                progress(active_stage, "failed", "This step failed. No simulated result was used.")
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            reason = (str(exc) if isinstance(exc, ChatValidationError)
                      else "invalid_model_json" if isinstance(exc, json.JSONDecodeError) and stage.startswith("model")
                      else "unexpected_error")
            logger.warning(
                "Instruct chat failed: request_id=%s stage=%s reason=%s error_type=%s "
                "upstream_status=%s model_turn=%d tool_count=%d model=%s",
                diagnostic_id, stage, reason, type(exc).__name__, status,
                model_turn, tool_count, json.dumps(diagnostics),
            )
            message = (
                "GPT-5.6 reached its response-length limit before completing a verified answer. "
                "No partial or simulated answer was used."
                if reason == "incomplete_model_response" and diagnostics.get("incomplete_reason") == "max_output_tokens"
                else "GPT-5.6 could not complete a verified answer. Retry or ask your operator to check model access and source availability. No simulated answer was used."
            )
            raise HTTPException(503, f"{message} Diagnostic ID: {diagnostic_id}.") from None
        finally:
            session["busy"] = False


chat_service = ChatService()
