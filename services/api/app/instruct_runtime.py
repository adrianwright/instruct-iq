"""Bounded request execution and principal-scoped generated-reference index."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings
from app.instruct_contracts import (
    ClassGrantV1, FinalEnvelopeV1, PlanRequestV1, RetrievalContextV1,
)
from app.instruct_policy import build_plan
from app.instruct_sources import ConnectedSources, empty_batch, validate_batch
from app.schemas import Source

CAPABILITIES = {
    Source.FABRIC: "assessment", Source.FOUNDRY: "curriculum",
    Source.WORK: "team_context", Source.WEB: "public_enrichment",
}


class ReferenceIndex:
    def __init__(self, *, clock=time.monotonic, max_plans=128):
        self.clock = clock
        self.max_plans = max_plans
        self.entries = OrderedDict()

    def _prune(self):
        for key, value in list(self.entries.items()):
            if value[0] <= self.clock():
                del self.entries[key]

    def put(self, envelope: FinalEnvelopeV1, grant: ClassGrantV1):
        self._prune()
        result = envelope.result
        key = (grant.principal.tenantId, grant.principal.subject, grant.classId, result.planId)
        evidence = {e.refId: e.model_copy(deep=True) for s in result.sources for e in s.evidence}
        self.entries[key] = (
            self.clock() + 900, grant.membershipRevision, result.assessmentId, evidence,
            result.model_copy(deep=True),
        )
        while len(self.entries) > self.max_plans:
            self.entries.popitem(last=False)

    def get(self, grant: ClassGrantV1, plan_id: str, ref_id: str):
        self._prune()
        key = (grant.principal.tenantId, grant.principal.subject, grant.classId, plan_id)
        entry = self.entries.get(key)
        if entry is None or entry[1] != grant.membershipRevision or ref_id not in entry[3]:
            return None
        return entry[2], entry[3][ref_id].model_copy(deep=True)

    def plan(self, grant: ClassGrantV1, plan_id: str):
        self._prune()
        key = (grant.principal.tenantId, grant.principal.subject, grant.classId, plan_id)
        entry = self.entries.get(key)
        if entry is None or entry[1] != grant.membershipRevision:
            return None
        return entry[4].model_copy(deep=True)


class InstructRuntime:
    def __init__(self, settings: Settings, sources=None, references=None):
        self.settings = settings
        self.sources = sources if sources is not None else ConnectedSources(settings)
        self.references = references if references is not None else ReferenceIndex()

    def contexts(self, request: PlanRequestV1, grant: ClassGrantV1):
        return [RetrievalContextV1(
            schemaVersion="instruct.retrieval.v1", grant=grant,
            assessmentId=request.assessmentId, scenario=request.scenario,
            source=source, capability=CAPABILITIES[source],
            publicQuery="Grade 7 science graph interpretation and evidence selection USGS EPA"
            if source == Source.WEB else None,
        ) for source in Source]

    @staticmethod
    def selected(request, source):
        return source in {Source.FABRIC, Source.FOUNDRY} or (
            source == Source.WORK and request.includeWork
        ) or (source == Source.WEB and request.includeWeb)

    async def execute(self, request: PlanRequestV1, grant: ClassGrantV1, request_id: str):
        deadline = asyncio.get_running_loop().time() + self.settings.INSTRUCT_REQUEST_TIMEOUT_SECONDS

        async def retrieve(context):
            if not self.selected(request, context.source):
                return empty_batch(context, "not_requested", None)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return empty_batch(context, "failed", "Retrieval deadline exceeded.")
            try:
                async with asyncio.timeout(min(remaining, self.settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS)):
                    return validate_batch(context, await self.sources.retrieve(context))
            except TimeoutError:
                return empty_batch(context, "failed", "Retrieval deadline exceeded.")
            except asyncio.CancelledError:
                raise
            except Exception:
                return empty_batch(context, "failed", "Provider evidence could not be validated.")

        tasks = [asyncio.create_task(retrieve(c)) for c in self.contexts(request, grant)]
        try:
            batches = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        result = build_plan(
            request, grant.principal, batches, plan_id=str(uuid4()), request_id=request_id,
            generated_at=datetime.now(timezone.utc),
        )
        return FinalEnvelopeV1(
            schemaVersion="instruct.final.v1", requestId=request_id, result=result,
        )
