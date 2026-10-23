"""Read-only native transports and the explicit instructional ingestion contract.

Never parse generated answers as records. Both stores must expose a complete,
versioned snapshot; this application schema is not a vendor response schema.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote, urlparse
from uuid import UUID

import httpx
from pydantic import AwareDatetime, Field, TypeAdapter

from app.instruct_contracts import (
    Contract, Id, ProviderBatchV1, ProviderFactV1, RetrievalContextV1, Text,
)
from app.schemas import Source


class MappingUnavailable(ValueError):
    pass


class Approval(Contract):
    approvalId: Id
    approvedBy: Id
    approvedAt: AwareDatetime
    status: Literal["approved"]


class NativeRecord(Contract):
    recordId: Id
    revision: Text
    locator: Text
    title: Text
    fact: dict
    approval: Approval | None


class NativeSnapshot(Contract):
    schemaVersion: Literal["instruct.native-snapshot.v1"]
    tenantId: Id
    classId: Id
    assessmentId: Id
    planningCutoff: AwareDatetime
    revision: Text
    completeKinds: list[str]
    recordCount: int = Field(ge=1, le=10000)
    records: list[NativeRecord]


def normalize(raw: str, context: RetrievalContextV1, native_id: str, approvers: list[str]):
    snapshot = NativeSnapshot.model_validate_json(raw)
    if (
        snapshot.tenantId != context.grant.principal.tenantId
        or snapshot.classId != context.grant.classId
        or snapshot.assessmentId != context.assessmentId
        or snapshot.planningCutoff != context.scenario.planningCutoff
        or snapshot.recordCount != len(snapshot.records)
        or len({r.recordId for r in snapshot.records}) != len(snapshot.records)
    ):
        raise ValueError("snapshot scope, cutoff or completeness mismatch")
    kinds = ({"roster", "assessment", "observation"} if context.source == Source.FABRIC
             else {"curriculum", "support", "schedule", "resource"})
    if set(snapshot.completeKinds) != kinds or len(snapshot.completeKinds) != len(kinds):
        raise ValueError("snapshot must attest complete source coverage")
    evidence, facts = [], []
    now = datetime.now(timezone.utc)
    for record in snapshot.records:
        if "evidenceRefs" in record.fact or record.fact.get("kind") not in kinds:
            raise ValueError("invalid raw fact mapping")
        ref = f"{context.source.value}-{record.recordId}"
        fact = TypeAdapter(ProviderFactV1).validate_json(json.dumps(
            {**record.fact, "evidenceRefs": [ref]},
        ))
        if context.source == Source.FOUNDRY:
            approval = record.approval
            if (
                approval is None or approval.approvedBy not in approvers
                or approval.approvalId != fact.approvalId
                or approval.approvedAt > fact.effectiveFrom
                or approval.approvedAt > snapshot.planningCutoff
            ):
                raise ValueError("unauthorized or late approval")
        elif record.approval is not None:
            raise ValueError("assessment records cannot carry curriculum approval")
        excerpt = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        evidence.append({
            "refId": ref, "classId": snapshot.classId, "source": context.source.value,
            "documentId": record.recordId, "title": record.title,
            "locator": record.locator, "excerpt": excerpt,
            "provenance": {
                "mode": "connected", "nativeId": f"{native_id}/{record.recordId}",
                "nativeRevision": f"{snapshot.revision}/{record.revision}",
                "retrievedAt": now.isoformat(),
                "contentSha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                "adapter": "instruct-native-snapshot.v1",
            },
        })
        facts.append(fact.model_dump(mode="json"))
    return ProviderBatchV1.model_validate_json(json.dumps({
        "schemaVersion": "instruct.provider.v1", "classId": snapshot.classId,
        "assessmentId": snapshot.assessmentId, "source": context.source.value,
        "requested": True, "state": "succeeded", "reason": None, "durationMs": 0,
        "facts": facts, "evidence": evidence,
    }))


async def _request(method, url, scope, body, timeout):
    from azure.identity.aio import DefaultAzureCredential

    async with DefaultAzureCredential() as credential:
        token = await credential.get_token(scope)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(
                method, url, json=body, headers={"Authorization": f"Bearer {token.token}"},
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("partial native response")
            return response.json()


async def _post(url, scope, body, timeout):
    return await _request("POST", url, scope, body, timeout)


async def _get(url, scope, timeout):
    return await _request("GET", url, scope, None, timeout)


class NativeTransports:
    def __init__(self, settings, post=None, get=None):
        self.settings = settings
        self.post = post or _post
        self.get = get or _get

    async def fabric(self, context):
        settings = self.settings
        model = str(UUID(settings.INSTRUCT_FABRIC_SEMANTIC_MODEL_ID))
        # IDs are contract-validated; quote DAX literals nevertheless.
        literal = lambda value: '"' + value.replace('"', '""') + '"'
        filters = " && ".join(
            f"'InstructSnapshots'[{column}] = {literal(value)}"
            for column, value in (
                ("TenantId", context.grant.principal.tenantId),
                ("ClassId", context.grant.classId), ("AssessmentId", context.assessmentId),
                ("PlanningCutoff", context.scenario.planningCutoff.isoformat()),
            )
        )
        payload = await self.post(
            f"https://api.powerbi.com/v1.0/myorg/datasets/{model}/executeQueries",
            "https://analysis.windows.net/powerbi/api/.default",
            {"queries": [{"query": "EVALUATE SELECTCOLUMNS(FILTER('InstructSnapshots', "
              + filters + '), "Snapshot", \'InstructSnapshots\'[Snapshot])'}],
             "serializerSettings": {"includeNulls": True}},
            settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS,
        )
        results = payload["results"]
        if payload.get("error") or len(results) != 1 or results[0].get("error"):
            raise ValueError("Fabric query failure or truncation")
        tables = results[0]["tables"]
        if len(tables) != 1 or tables[0].get("error") or not tables[0]["rows"]:
            raise ValueError("Fabric snapshot missing")
        # One native record per row avoids semantic-model text cell limits.
        # Repeated manifests must agree; the normalizer checks the total count,
        # detecting truncated query responses even when HTTP 200 has no error.
        manifest, records = None, []
        for row in tables[0]["rows"]:
            fragment = json.loads(row["[Snapshot]"])
            record = fragment.pop("records")
            if not isinstance(record, list) or len(record) != 1:
                raise ValueError("Fabric rows must contain exactly one native record")
            if manifest is not None and manifest != fragment:
                raise ValueError("Fabric returned mixed snapshot revisions or scope")
            manifest = fragment
            records.extend(record)
        return json.dumps({**manifest, "records": records}), (
            f"powerbi:dataset:{model}:InstructSnapshots"
        )

    async def foundry(self, context):
        settings = self.settings
        endpoint = settings.INSTRUCT_SEARCH_ENDPOINT.rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(
            ".search.windows.net"
        ) or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.port:
            raise MappingUnavailable("Dedicated Search endpoint mapping is invalid.")
        if settings.INSTRUCT_SEARCH_API_VERSION != "2026-08-01-preview":
            raise MappingUnavailable("Search API version mapping is not verified.")
        source = settings.INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE
        kb_url = (
            f"{endpoint}/knowledgebases('{quote(settings.INSTRUCT_FOUNDRY_KB_NAME, safe='')}')"
            "?api-version=2026-08-01-preview"
        )
        definition = await self.get(
            kb_url, "https://search.azure.com/.default",
            settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS,
        )
        sources = definition.get("knowledgeSources", [])
        if (
            not isinstance(sources, list)
            or [{k: v for k, v in item.items() if v is not None} for item in sources]
            != [{"name": source}]
        ):
            raise MappingUnavailable("Knowledge base must contain only the dedicated mapped source.")
        escape = lambda value: "'" + value.replace("'", "''") + "'"
        filters = " and ".join(
            f"{key} eq {escape(value)}" for key, value in (
                ("tenantId", context.grant.principal.tenantId),
                ("classId", context.grant.classId), ("assessmentId", context.assessmentId),
                ("planningCutoff", context.scenario.planningCutoff.isoformat()),
            )
        )
        payload = await self.post(
            kb_url.replace("?api-version=", "/retrieve?api-version="),
            "https://search.azure.com/.default",
            {"intents": [{"type": "semantic", "search": "Complete approved instructional snapshot"}],
             "outputMode": "extractiveData", "retrievalReasoningEffort": {"kind": "minimal"},
             "includeActivity": True,
             "knowledgeSourceParams": [{
                 "kind": "searchIndex", "knowledgeSourceName": source,
                 "filterAddOn": filters, "alwaysQuerySource": True,
                 "includeReferences": True, "includeReferenceSourceData": True,
                 "resultsProcessing": "none", "failOnError": True,
             }]},
            settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS,
        )
        if payload.get("error") or any(a.get("error") for a in payload.get("activity", [])):
            raise ValueError("Search retrieval failed")
        references = payload["references"]
        if len(references) != 1:
            raise ValueError("Search snapshot missing or ambiguous")
        reference = references[0]
        activities = [a for a in payload["activity"] if a["id"] == reference["activitySource"]]
        if (
            reference["type"] != "searchIndex" or len(activities) != 1
            or activities[0]["type"] != "searchIndex"
            or activities[0]["knowledgeSourceName"] != source
            or activities[0].get("count") != 1
            or not reference["docKey"]
        ):
            raise ValueError("unexpected Search source")
        return reference["sourceData"]["snapshot"], (
            f"{endpoint}/{source}/{reference['docKey']}"
        )
