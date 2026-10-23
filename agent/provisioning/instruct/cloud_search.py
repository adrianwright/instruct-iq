"""Bounded ACA publisher entrypoint; credentials remain in managed-identity memory."""
import asyncio
import json
import os
import sys
import types
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from azure.identity import ManagedIdentityCredential


def main(payload):
    config, endpoint = payload["config"], payload["endpoint"]
    credential = ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"])
    modules = {}
    for name in ("fabric", "publish"):
        module = types.ModuleType(name)
        sys.modules[name] = module
        exec(compile(payload[name], name + ".py", "exec"), module.__dict__)
        modules[name] = module
    publisher = modules["publish"]

    def az_json(*args):
        if args[:2] == ("account", "show"):
            token = credential.get_token("https://management.azure.com/.default").token
            import base64
            claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
            return {"tenantId": claims["tid"]}
        if args[:2] == ("account", "get-access-token"):
            scope = args[args.index("--resource") + 1] + "/.default"
            return {"accessToken": credential.get_token(scope).token}
        if args[:3] == ("rest", "--method", "get"):
            url = args[args.index("--url") + 1]
            expected = "https://management.azure.com" + config["searchResourceId"]
            if url != expected + "?api-version=2026-09-01-preview":
                raise ValueError("Unexpected management coordinate")
            token = credential.get_token("https://management.azure.com/.default").token
            with urlopen(Request(url, headers={"Authorization": "Bearer " + token}), timeout=30) as response:
                return json.load(response)
        raise ValueError("Unsupported cloud operation")

    publisher.az_json = az_json
    client = publisher.SearchClient(endpoint, config)
    try:
        print(json.dumps({"existingKnowledgeBase": client.request(
            "GET", f"/knowledgebases('{publisher.KB}')")}), flush=True)
    except Exception as error:
        from urllib.error import HTTPError
        if not isinstance(error, HTTPError) or error.code != 404:
            raise
    snapshot = publisher.snapshots(payload["registry"], config, endpoint)["foundry"]
    if not payload.get("readOnly"):
        print(json.dumps({"publication": publisher.publish_search(client, config, snapshot)}), flush=True)
    from app.config import Settings
    from app.instruct_adapters import NativeTransports, normalize
    from app.instruct_contracts import ClassGrantV1, PlanRequestV1
    from app.instruct_runtime import InstructRuntime
    from app.instruct_sources import validate_batch
    from app.schemas import Source
    if payload.get("adapter"):
        import app.instruct_adapters as adapters
        exec(compile(payload["adapter"], "instruct_adapters.py", "exec"), adapters.__dict__)
        NativeTransports, normalize = adapters.NativeTransports, adapters.normalize
    registry = payload["registry"]
    request = PlanRequestV1.model_validate_json(json.dumps({
        "schemaVersion": "instruct.request.v1", "classId": registry["class"]["classId"],
        "assessmentId": registry["class"]["assessmentId"], "scenario": registry["scenario"],
        "includeWork": False, "includeWeb": False,
    }))
    grant = ClassGrantV1.model_validate_json(json.dumps({
        "grantId": "operator-ingestion-verification",
        "principal": {"tenantId": config["tenantId"], "subject": config["syntheticApproverId"]},
        "classId": request.classId, "checkedAt": datetime.now(timezone.utc).isoformat(),
        "membershipRevision": "synthetic-ingestion-v1",
    }))
    settings = Settings(
        _env_file=None, APP_ENVIRONMENT="test", INSTRUCT_SEARCH_ENDPOINT=endpoint,
        INSTRUCT_SEARCH_API_VERSION=publisher.VERSION, INSTRUCT_FOUNDRY_KB_NAME=publisher.KB,
        INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE=publisher.SOURCE,
    )
    responses = {}

    async def post(url, scope, body, timeout):
        path = url[len(endpoint):].split("?")[0]
        response = client.request("POST", path, body)
        responses["retrieve"] = response
        print(json.dumps({"retrieveProtocol": {
            "topLevel": list(response), "references": response.get("references"),
            "activity": response.get("activity"),
        }}), flush=True)
        return response

    async def get(url, scope, timeout):
        response = client.request("GET", url[len(endpoint):].split("?")[0])
        responses["definition"] = response
        return response

    async def verify():
        context = next(c for c in InstructRuntime(settings).contexts(request, grant)
                       if c.source == Source.FOUNDRY)
        raw, native = await NativeTransports(settings, post=post, get=get).foundry(context)
        batch = validate_batch(context, normalize(raw, context, native, [config["syntheticApproverId"]]))
        print(json.dumps({"liveFoundry": {"state": batch.state, "facts": len(batch.facts),
              "evidence": len(batch.evidence), "snapshotRevision": json.loads(raw)["revision"]},
              "responses": responses}), flush=True)

    asyncio.run(verify())
    credential.close()


if __name__ == "__main__":
    import base64
    import zlib
    from urllib.error import HTTPError
    try:
        main(json.loads(zlib.decompress(base64.b64decode(sys.argv[1]))))
    except HTTPError as error:
        print(json.dumps({"httpError": error.code, "providerError": error.read().decode()}), flush=True)
        raise SystemExit(1)
