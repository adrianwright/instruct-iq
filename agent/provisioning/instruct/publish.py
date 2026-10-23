"""Explicit isolated synthetic snapshot publishing; no application runtime seed reads."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import time
from pathlib import Path
from uuid import UUID
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from fabric import (
    Client, FABRIC, az_json, collection, ensure_targets, finish, marker, owned,
    seed, seed_tables, validate,
)

VERSION = "2026-08-01-preview"
INDEX = "instruct-approved-snapshots"
SOURCE = "instruct-approved-source"
KB = "instruct-approved-kb"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshots(registry, config, endpoint):
    if registry.get("synthetic") is not True or registry.get("schemaVersion") != "instruct.seed.v1":
        raise ValueError("Explicit synthetic seed required")
    approver = str(UUID(config["syntheticApproverId"]))
    result = {}
    for batch in registry["sources"]:
        source = batch["source"]
        if source not in {"fabric", "foundry"}:
            continue
        native = (f"fabric://{config['workspaceId']}/{config['lakehouseId']}/Tables/InstructSnapshots"
                  if source == "fabric" else f"{endpoint}/indexes/{INDEX}/docs/instruct-snapshot")
        records = []
        for original in batch["facts"]:
            fact = {k: v for k, v in original.items() if k != "evidenceRefs"}
            records.append({
                "recordId": fact["factId"], "revision": digest(fact),
                "locator": native + "#" + fact["factId"],
                "title": f"Ingested synthetic {fact['kind']}",
                "fact": fact,
                "approval": None if source == "fabric" else {
                    "approvalId": fact["approvalId"], "approvedBy": approver,
                    "approvedAt": fact["effectiveFrom"], "status": "approved",
                },
            })
        result[source] = {
            "schemaVersion": "instruct.native-snapshot.v1", "tenantId": config["tenantId"],
            "classId": registry["class"]["classId"], "assessmentId": registry["class"]["assessmentId"],
            "planningCutoff": registry["scenario"]["planningCutoff"],
            "revision": digest(records), "recordCount": len(records), "records": records,
            "completeKinds": (["roster", "assessment", "observation"] if source == "fabric"
                              else ["curriculum", "support", "schedule", "resource"]),
        }
    return result


def snapshot_table(snapshot):
    stream = io.StringIO(newline="")
    columns = ["TenantId", "ClassId", "AssessmentId", "PlanningCutoff", "Snapshot"]
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for record in snapshot["records"]:
        writer.writerow(dict(zip(columns, [
            snapshot["tenantId"], snapshot["classId"], snapshot["assessmentId"],
            snapshot["planningCutoff"], json.dumps({**snapshot, "records": [record]}),
        ])))
    return stream.getvalue().encode(), len(snapshot["records"])


def model_definition(snapshot):
    # Import the exact published projection. Explicit refresh is needed after a
    # future publication; this is not an automatically synchronized Direct Lake model.
    payload, _ = snapshot_table(snapshot)
    expression = (
        'let Source = Csv.Document(Binary.FromText("' + base64.b64encode(payload).decode()
        + '", BinaryEncoding.Base64),[Delimiter=",",Encoding=65001,QuoteStyle=QuoteStyle.Csv]),'
        ' Headers = Table.PromoteHeaders(Source,[PromoteAllScalars=true]) in Headers'
    )
    columns = ["TenantId", "ClassId", "AssessmentId", "PlanningCutoff", "Snapshot"]
    bim = {"compatibilityLevel": 1600, "model": {
        "culture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "tables": [{"name": "InstructSnapshots",
                    "columns": [{"name": c, "dataType": "string", "sourceColumn": c,
                                 "summarizeBy": "none"} for c in columns],
                    "measures": [{"name": "Snapshot Record Count",
                                  "expression": "COUNTROWS('InstructSnapshots')"}],
                    "partitions": [{"name": "InstructSnapshots", "mode": "import",
                                    "source": {"type": "m", "expression": expression}}]}]}}
    return {"parts": [
        {"path": name, "payloadType": "InlineBase64",
         "payload": base64.b64encode(json.dumps(value).encode()).decode()}
        for name, value in (("model.bim", bim), ("definition.pbism", {"version": "1.0", "settings": {}}))
    ]}


def publish_model(client, config, snapshot):
    base = f"{FABRIC}/workspaces/{config['workspaceId']}/semanticModels"
    name = "instruct-snapshots-" + snapshot["revision"][:12]
    existing = owned(collection(client, base), name, marker(config))
    if existing:
        return existing["id"]
    created = finish(client, client.request("POST", base, {
        "displayName": name, "description": marker(config), "definition": model_definition(snapshot),
    }), result=True)
    return created["id"]


class PowerBIClient:
    def __init__(self, config):
        self.config = config
        self.token = None

    def request(self, method, path, body=None):
        if not path.startswith(("/groups/", "/datasets/")):
            raise ValueError("Unexpected Power BI path")
        if not self.token:
            self.token = az_json("account", "get-access-token", "--subscription",
                                 self.config["appSubscriptionId"],
                                 "--resource", "https://analysis.windows.net/powerbi/api")["accessToken"]
        from urllib.request import HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("Authenticated redirect refused")
        req = Request("https://api.powerbi.com/v1.0/myorg" + path,
                      data=None if body is None else json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
                      method=method)
        with build_opener(NoRedirect()).open(req, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}


def refresh_model(client, config, model_id):
    base = f"/groups/{config['workspaceId']}/datasets/{model_id}/refreshes"
    history = client.request("GET", base).get("value", [])
    # Never replay an ambiguous POST while refresh history reports pending work.
    if not history:
        client.request("POST", base, {"notifyOption": "NoNotification"})
    elif history[0]["status"] == "Completed":
        return
    elif history[0]["status"] not in {"Unknown", "InProgress", "NotStarted"}:
        raise RuntimeError("Existing refresh failed; inspect history before retry")
    for _ in range(24):
        time.sleep(5)
        history = client.request("GET", base).get("value", [])
        if history and history[0]["status"] == "Completed":
            return
        if history and history[0]["status"] not in {"Unknown", "InProgress", "NotStarted"}:
            raise RuntimeError("Semantic model refresh failed")
    raise TimeoutError("Refresh still pending; inspect before retry")


def verify_fabric(config, model_id, endpoint=None):
    """Query actual provider records, then run the installed normalizer/policy."""
    import asyncio
    from datetime import datetime, timezone
    from uuid import UUID
    from app.config import Settings
    from app.instruct_adapters import NativeTransports, normalize
    from app.instruct_contracts import ClassGrantV1, PlanRequestV1
    from app.instruct_runtime import InstructRuntime
    from app.instruct_sources import empty_batch, validate_batch
    from app.instruct_policy import build_plan
    from app.schemas import Source
    model_id = str(UUID(model_id))
    settings = Settings(_env_file=None, APP_ENVIRONMENT="test",
                        INSTRUCT_FABRIC_SEMANTIC_MODEL_ID=model_id,
                        INSTRUCT_SEARCH_ENDPOINT=endpoint or "",
                        INSTRUCT_SEARCH_API_VERSION=VERSION if endpoint else "",
                        INSTRUCT_FOUNDRY_KB_NAME=KB if endpoint else "",
                        INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE=SOURCE if endpoint else "")
    request = PlanRequestV1.model_validate_json(json.dumps({
        "schemaVersion": "instruct.request.v1", "classId": "class-science-7a",
        "assessmentId": "assessment-20261016", "scenario": {
            "assessmentDate": "2026-10-16", "lessonDate": "2026-10-19",
            "timezone": "America/New_York", "planningCutoff": "2026-10-19T07:00:00-04:00",
            "lessonMinutes": 35, "studentCount": 24,
        }, "includeWork": False, "includeWeb": False,
    }))
    grant = ClassGrantV1.model_validate_json(json.dumps({
        "grantId": "operator-ingestion-verification",
        "principal": {"tenantId": config["tenantId"], "subject": "synthetic-teacher"},
        "classId": request.classId, "checkedAt": datetime.now(timezone.utc).isoformat(),
        "membershipRevision": "synthetic-ingestion-v1",
    }))
    contexts = InstructRuntime(settings).contexts(request, grant)
    client = PowerBIClient(config)
    search = SearchClient(endpoint, config) if endpoint else None
    async def post(url, scope, body, timeout):
        if search and url.startswith(endpoint + "/"):
            return search.request("POST", url[len(endpoint):].split("?")[0], body)
        prefix = "https://api.powerbi.com/v1.0/myorg"
        if not url.startswith(prefix + "/"):
            raise ValueError("Unexpected verification endpoint")
        return client.request("POST", url[len(prefix):], body)
    async def get(url, scope, timeout):
        if not search or not url.startswith(endpoint + "/"):
            raise ValueError("Unexpected Search verification endpoint")
        return search.request("GET", url[len(endpoint):].split("?")[0])
    async def run():
        context = next(c for c in contexts if c.source == Source.FABRIC)
        raw, native = await NativeTransports(settings, post=post).fabric(context)
        batch = validate_batch(context, normalize(raw, context, native, []))
        foundry = None
        if endpoint:
            foundry_context = next(c for c in contexts if c.source == Source.FOUNDRY)
            foundry_raw, foundry_native = await NativeTransports(settings, post=post, get=get).foundry(foundry_context)
            foundry = validate_batch(foundry_context, normalize(
                foundry_raw, foundry_context, foundry_native, [str(UUID(config["syntheticApproverId"]))],
            ))
        batches = [
            batch if c.source == Source.FABRIC else
            foundry if c.source == Source.FOUNDRY and foundry is not None else
            empty_batch(c, "unavailable", "Foundry not verified in Fabric-only check.")
            if c.source == Source.FOUNDRY else empty_batch(c, "not_requested", None)
            for c in contexts
        ]
        result = build_plan(request, grant.principal, batches, plan_id="ingestion-verification",
                            request_id="ingestion-verification", generated_at=datetime.now(timezone.utc))
        return {"semanticModelId": model_id, "executeQueriesRows": len(batch.facts),
                "nativeEvidenceRecords": len(batch.evidence), "normalizedFabricState": batch.state,
                "foundryFacts": len(foundry.facts) if foundry is not None else None,
                "foundryEvidenceRecords": len(foundry.evidence) if foundry is not None else None,
                "normalizedFoundryState": foundry.state if foundry is not None else None,
                "policyStatus": result.status, "snapshotRevision": json.loads(raw)["revision"]}
    return asyncio.run(run())


class SearchClient:
    def __init__(self, endpoint, config):
        from urllib.parse import urlsplit
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname
                or not parsed.hostname.endswith(".search.windows.net")
                or parsed.path or parsed.query or parsed.fragment or parsed.port or parsed.username):
            raise ValueError("Explicit Search endpoint required")
        self.endpoint, self.config, self.token = endpoint, config, None

    def verify_target(self):
        """Bind writes to the explicitly tracked new resource, not an arbitrary service."""
        resource = self.config["searchResourceId"]
        expected = (f"/subscriptions/{self.config['appSubscriptionId']}/resourceGroups/"
                    "rg-instruct-iq/providers/Microsoft.Search/searchServices/")
        if not resource.startswith(expected) or "/" in resource[len(expected):]:
            raise ValueError("Search must be an explicitly tracked isolated resource")
        account = az_json("account", "show", "--subscription", self.config["appSubscriptionId"])
        if account["tenantId"].lower() != self.config["tenantId"].lower():
            raise ValueError("Search subscription tenant mismatch")
        actual = az_json("rest", "--method", "get", "--url",
                         f"https://management.azure.com{resource}?api-version=2026-09-01-preview")
        if (actual["properties"]["endpoint"].rstrip("/") != self.endpoint
                or actual.get("tags", {}).get("managedBy") != "instruct-phase-c"
                or actual.get("tags", {}).get("project") != "instruct-iq"
                or actual["properties"]["status"] != "running"):
            raise ValueError("Search endpoint or isolated ownership mismatch")

    def request(self, method, path, body=None, create=False):
        if not self.token:
            self.token = az_json("account", "get-access-token", "--subscription",
                                 self.config["appSubscriptionId"],
                                 "--resource", "https://search.azure.com")["accessToken"]
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                   "Prefer": "return=representation"}
        if create:
            headers["If-None-Match"] = "*"
        from urllib.request import HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("Authenticated redirect refused")
        req = Request(self.endpoint + path + "?api-version=" + VERSION,
                      data=None if body is None else json.dumps(body).encode(),
                      headers=headers, method=method)
        with build_opener(NoRedirect()).open(req, timeout=60) as response:
            if response.status not in {200, 201, 204}:
                raise ValueError("Partial Search response refused")
            data = response.read()
            return json.loads(data) if data else {}


def search_definitions(config):
    description = marker(config)
    fields = [{"name": name, "type": "Edm.String", "retrievable": True,
               "filterable": name in {"tenantId", "classId", "assessmentId", "planningCutoff"},
               "searchable": name in {"content", "snapshot"}, **({"key": True} if name == "id" else {})}
              for name in ["id", "tenantId", "classId", "assessmentId", "planningCutoff", "content", "snapshot"]]
    return [
        (f"/indexes('{INDEX}')", {
            "name": INDEX, "description": description, "fields": fields,
            "semantic": {"defaultConfiguration": "instruct", "configurations": [{
                "name": "instruct", "prioritizedFields": {
                    "prioritizedContentFields": [{"fieldName": "content"}]}}]},
        }),
        (f"/knowledgesources('{SOURCE}')", {
            "name": SOURCE, "kind": "searchIndex", "description": description,
            "searchIndexParameters": {"searchIndexName": INDEX, "semanticConfigurationName": "instruct",
                                      "searchFields": [{"name": "content"}],
                                      "sourceDataFields": [{"name": "snapshot"}]},
        }),
        (f"/knowledgebases('{KB}')", {
            "name": KB, "description": description, "knowledgeSources": [{"name": SOURCE}],
            "outputMode": "extractiveData", "retrievalReasoningEffort": {"kind": "minimal"},
        }),
    ]


def publish_search(client, config, snapshot):
    # Read all coordinates before any write; exact ownership prevents adopting
    # existing resources, and conditional create protects concurrent publishers.
    client.verify_target()
    missing = []
    for path, definition in search_definitions(config):
        try:
            actual = client.request("GET", path)
        except HTTPError as error:
            if error.code != 404:
                raise
            missing.append((path, definition))
            continue
        if actual.get("description") != marker(config):
            raise ValueError("Search resource ownership mismatch")
        if path.startswith("/indexes"):
            fields = {f["name"]: f for f in actual.get("fields", [])}
            for required in definition["fields"]:
                field = fields.get(required["name"], {})
                if any(field.get(k, False) != v for k, v in required.items()):
                    raise ValueError("Search index field contract mismatch")
        if path.startswith("/knowledgesources") and actual.get("searchIndexParameters", {}).get("searchIndexName") != INDEX:
            raise ValueError("Search source index mismatch")
        if path.startswith("/knowledgesources"):
            params = actual.get("searchIndexParameters", {})
            for key in ("semanticConfigurationName", "searchFields", "sourceDataFields"):
                if params.get(key) != definition["searchIndexParameters"][key]:
                    raise ValueError("Search source snapshot mapping mismatch")
        sources = actual.get("knowledgeSources", [])
        if path.startswith("/knowledgebases") and (
            not isinstance(sources, list)
            or [{k: v for k, v in item.items() if v is not None} for item in sources]
            != [{"name": SOURCE}]
        ):
            raise ValueError("Search KB source mismatch")
        if path.startswith("/knowledgebases") and (
            actual.get("models") or actual.get("outputMode") != "extractiveData"
            or actual.get("retrievalReasoningEffort") != {"kind": "minimal"}
        ):
            raise ValueError("Search KB must remain model-free minimal extractive")
    for path, definition in missing:
        client.request("PUT", path, definition, create=True)
    response = client.request("POST", f"/indexes('{INDEX}')/docs/index", {"value": [{
        "@search.action": "upload", "id": "instruct-snapshot",
        **{k: snapshot[k] for k in ["tenantId", "classId", "assessmentId", "planningCutoff"]},
        "content": "Complete approved instructional snapshot. Synthetic curriculum support schedule resource. "
                   + " ".join(json.dumps(r["fact"]) for r in snapshot["records"]),
        "snapshot": json.dumps(snapshot),
    }]})
    if len(response["value"]) != 1 or not response["value"][0]["status"]:
        raise ValueError("Search document publication failed")
    return {"index": INDEX, "source": SOURCE, "knowledgeBase": KB, "documents": 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("data") / "instruct" / "registry.json")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--apply", choices=["fabric", "search"])
    parser.add_argument("--verify-model", help="Read-only Fabric normalization/policy check (requires API PYTHONPATH)")
    parser.add_argument("--verify-connected", action="store_true",
                        help="Retrieve Foundry as well as live Fabric; requires --verify-model")
    parser.add_argument("--inspect-search", action="store_true",
                        help="Read-only ownership and index/source/KB existence check")
    args = parser.parse_args()
    config = validate(json.loads(args.config.read_text(encoding="utf-8")))
    if args.inspect_search:
        if args.apply or args.verify_model or args.verify_connected:
            parser.error("--inspect-search is a separate read-only operation")
        client = SearchClient(args.endpoint, config)
        client.verify_target()
        results = {}
        for path, definition in search_definitions(config):
            try:
                actual = client.request("GET", path)
                results[path] = {"exists": True, "owned": actual.get("description") == marker(config)}
            except HTTPError as error:
                if error.code != 404:
                    raise
                results[path] = {"exists": False}
        print(json.dumps(results, indent=2))
        return
    if args.verify_connected and not args.verify_model:
        parser.error("--verify-connected requires --verify-model")
    if args.verify_model:
        if args.apply:
            parser.error("--verify-model cannot be combined with --apply")
        print(json.dumps(verify_fabric(config, args.verify_model,
                                      args.endpoint if args.verify_connected else None), indent=2))
        return
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    values = snapshots(registry, config, args.endpoint)
    if args.apply == "fabric":
        client = Client(config)
        ensure_targets(client, config)
        seed(client, config["workspaceId"], config["lakehouseId"], {
            **seed_tables(args.registry), "InstructSnapshots": snapshot_table(values["fabric"]),
        })
        model_id = publish_model(client, config, values["fabric"])
        print(json.dumps({"semanticModelId": model_id}), flush=True)
        refresh_model(PowerBIClient(config), config, model_id)
        print(json.dumps({"refresh": "Completed"}))
    elif args.apply == "search":
        print(json.dumps(publish_search(SearchClient(args.endpoint, config), config, values["foundry"])))
    else:
        print(json.dumps({s: {"recordCount": v["recordCount"], "revision": v["revision"]}
                          for s, v in values.items()}, indent=2))


if __name__ == "__main__":
    main()
