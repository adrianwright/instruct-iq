"""Connected-only source boundary. Unsupported live mappings fail closed."""
from __future__ import annotations

import hashlib
import time

from pydantic import TypeAdapter

from app.config import Settings, _is_operator_value
from app.instruct_adapters import MappingUnavailable, NativeTransports, normalize
from app.instruct_contracts import ProviderBatchV1, RetrievalContextV1
from app.schemas import Source


def empty_batch(context: RetrievalContextV1, state: str, reason: str | None) -> ProviderBatchV1:
    return ProviderBatchV1(
        schemaVersion="instruct.provider.v1", classId=context.grant.classId,
        assessmentId=context.assessmentId, source=context.source,
        requested=state != "not_requested", state=state, reason=reason,
        durationMs=0, evidence=[], facts=[],
    )


class ConnectedSources:
    def __init__(self, settings: Settings, transports=None):
        self.settings = settings
        self.transports = transports or NativeTransports(settings)

    async def retrieve(self, context: RetrievalContextV1) -> ProviderBatchV1:
        source = context.source
        if source in {Source.WORK, Source.WEB}:
            return empty_batch(context, "unavailable", "Optional integration is not configured.")
        coordinates = (
            (self.settings.INSTRUCT_FABRIC_SEMANTIC_MODEL_ID,)
            if source == Source.FABRIC else
            (self.settings.INSTRUCT_SEARCH_ENDPOINT, self.settings.INSTRUCT_FOUNDRY_KB_NAME,
             self.settings.INSTRUCT_SEARCH_API_VERSION,
             self.settings.INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE)
        )
        if not all(_is_operator_value(value) for value in coordinates):
            return empty_batch(context, "unavailable", "Dedicated native provider mapping is not configured.")
        started = time.monotonic()
        try:
            approvers = TypeAdapter(list[str]).validate_json(self.settings.INSTRUCT_APPROVER_IDS_JSON)
            if source == Source.FOUNDRY and not approvers:
                raise MappingUnavailable("Authorized curriculum approver mapping is not configured.")
            transport = self.transports.fabric if source == Source.FABRIC else self.transports.foundry
            raw, native_id = await transport(context)
            batch = validate_batch(context, normalize(raw, context, native_id, approvers))
            batch.durationMs = int((time.monotonic() - started) * 1000)
            return batch
        except MappingUnavailable as exc:
            return empty_batch(context, "unavailable", str(exc))
        except Exception:
            return empty_batch(context, "failed", "Native source retrieval or validation failed.")


def validate_batch(context: RetrievalContextV1, batch: ProviderBatchV1) -> ProviderBatchV1:
    # Revalidate even typed values: model_copy/model_construct do not validate.
    batch = ProviderBatchV1.model_validate_json(batch.model_dump_json())
    if (batch.classId, batch.assessmentId, batch.source) != (
        context.grant.classId, context.assessmentId, context.source,
    ) or not batch.requested or batch.state not in {"succeeded", "failed", "unavailable"}:
        raise ValueError("provider scope or lifecycle mismatch")
    if any(e.provenance.mode != "connected" for e in batch.evidence):
        raise ValueError("connected runtime rejects development evidence")
    if any(hashlib.sha256(e.excerpt.encode("utf-8")).hexdigest() != e.provenance.contentSha256
           for e in batch.evidence):
        raise ValueError("evidence excerpt digest mismatch")
    return batch
