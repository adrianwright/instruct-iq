"""Explicit-target Fabric preparation. Offline by default; --apply is a separate live gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

FABRIC = "https://api.fabric.microsoft.com/v1"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
CAPACITY = re.compile(
    r"^/subscriptions/([0-9a-f-]{36})/resourceGroups/([^/]+)/providers/"
    r"Microsoft\.Fabric/capacities/([^/]+)$", re.I
)


def validate(config):
    config = dict(config)
    for key in ("appSubscriptionId", "tenantId", "deploymentId", "fabricCapacityId"):
        config[key] = str(UUID(config[key]))
    match = CAPACITY.fullmatch(config["capacityResourceId"])
    if not match:
        raise ValueError("An explicit approved Fabric ARM capacity ID is required")
    config["capacitySubscriptionId"] = str(UUID(match[1]))
    if not re.fullmatch(r"instruct-iq(?:-[a-z0-9-]+)?", config["workspaceName"]):
        raise ValueError("Workspace must be dedicated to instruct-iq")
    if not re.fullmatch(r"instruct_iq(?:_[a-z0-9_]+)?", config["lakehouseName"]):
        raise ValueError("Lakehouse must be dedicated to instruct_iq")
    for key in ("workspaceId", "lakehouseId"):
        if config.get(key):
            config[key] = str(UUID(config[key]))
    if config.get("lakehouseId") and not config.get("workspaceId"):
        raise ValueError("lakehouseId requires workspaceId")
    return config


def marker(config):
    return f"instruct-iq:{config['deploymentId']}"


def az_json(*args):
    result = subprocess.run(
        [shutil.which("az") or "az", *args, "--only-show-errors", "-o", "json"],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


class Client:
    def __init__(self, config):
        self.config = config
        self.tokens = {}

    def request(self, method, url, body=None, audience="https://api.fabric.microsoft.com", raw=False):
        expected_host = (
            "api.fabric.microsoft.com"
            if audience == "https://api.fabric.microsoft.com"
            else "onelake.dfs.fabric.microsoft.com"
        )
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != expected_host:
            raise ValueError("Refusing untrusted API/pagination/operation URL")
        if audience not in self.tokens:
            account = az_json("account", "show", "--subscription", self.config["capacitySubscriptionId"])
            if account["tenantId"].lower() != self.config["tenantId"] or account["state"] != "Enabled":
                raise ValueError("Capacity subscription must be enabled and in the approved tenant")
            self.tokens[audience] = az_json(
                "account", "get-access-token",
                "--subscription", self.config["capacitySubscriptionId"],
                "--resource", audience,
            )["accessToken"]
        payload = body if raw else (json.dumps(body).encode() if body is not None else None)
        req = Request(url, data=payload, method=method, headers={
            "Authorization": f"Bearer {self.tokens[audience]}",
            "Content-Type": "application/octet-stream" if raw else "application/json",
        })
        # Do not replay ambiguous POST failures. A rerun recovers by ownership marker.
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError("Refusing authenticated redirect")

        with build_opener(NoRedirect()).open(req, timeout=90) as response:
            data = response.read()
            return response.status, dict(response.headers), json.loads(data) if data else {}


def collection(client, url):
    values, seen = [], set()
    while url:
        if url in seen or len(seen) >= 100:
            raise RuntimeError("Invalid or excessive pagination")
        seen.add(url)
        _, _, page = client.request("GET", url)
        values.extend(page.get("value", []))
        url = page.get("continuationUri")
        if url and not url.startswith(FABRIC + "/"):
            raise ValueError("Refusing external pagination URL")
    return values


def finish(client, response, result=False):
    status, headers, body = response
    if status != 202:
        return body
    headers = {key.lower(): value for key, value in headers.items()}
    url = headers.get("location")
    # Lakehouse workload routing can return a regional analysis.windows.net
    # Location. Poll the documented Fabric endpoint using its operation UUID;
    # never forward the Fabric bearer to that returned host.
    if not url or not url.startswith(FABRIC + "/operations/"):
        operation_id = headers.get("x-ms-operation-id")
        if operation_id:
            url = f"{FABRIC}/operations/{UUID(operation_id)}"
    if not url or not url.startswith(FABRIC + "/operations/"):
        raise ValueError("Missing or untrusted Fabric operation URL")
    delay = min(max(int(headers.get("retry-after", "5")), 1), 60)
    for _ in range(60):
        time.sleep(delay)
        _, _, operation = client.request("GET", url)
        if operation.get("status") == "Succeeded":
            return client.request("GET", url.rstrip("/") + "/result")[2] if result else operation
        if operation.get("status") in {"Failed", "Cancelled"}:
            raise RuntimeError("Fabric operation failed; inspect operation ID without logging tokens")
    raise TimeoutError(f"Fabric operation still pending: {url}; inspect before rerunning")


def owned(items, name, description, explicit_id=None):
    matches = [item for item in items if item.get("displayName") == name]
    if len(matches) > 1:
        raise ValueError("Ambiguous target name")
    if explicit_id and (not matches or matches[0].get("id") != explicit_id):
        raise ValueError("Explicit target ID does not match the owned target")
    if matches and matches[0].get("description") != description:
        raise ValueError("Refusing preexisting resource without exact deployment ownership marker")
    return matches[0] if matches else None


def ensure_targets(client, config):
    config = validate(config)
    # Link the SaaS UUID to the separately provided ARM ID; never modify capacity.
    capacities = collection(client, FABRIC + "/capacities")
    matches = [c for c in capacities if c.get("id") == config["fabricCapacityId"]]
    if len(matches) != 1 or matches[0].get("azureResourceId", "").lower() != config["capacityResourceId"].lower():
        raise ValueError("Fabric capacity UUID/approved ARM ID mismatch")
    if matches[0].get("state") != "Active":
        raise ValueError("Approved capacity is not Active; activation is NOT authorized by this utility")
    description = marker(config)
    workspace = owned(
        collection(client, FABRIC + "/workspaces"), config["workspaceName"],
        description, config.get("workspaceId"),
    )
    if workspace is None:
        workspace = finish(client, client.request("POST", FABRIC + "/workspaces", {
            "displayName": config["workspaceName"], "description": description,
            "capacityId": config["fabricCapacityId"],
        }))
    workspace_id = str(UUID(workspace["id"]))
    workspace = client.request("GET", f"{FABRIC}/workspaces/{workspace_id}")[2]
    if (
        workspace.get("capacityId") != config["fabricCapacityId"]
        or workspace.get("description") != description
        or workspace.get("displayName") != config["workspaceName"]
    ):
        raise ValueError("Workspace ownership/capacity changed; no item writes permitted")
    base = f"{FABRIC}/workspaces/{workspace_id}/lakehouses"
    lakehouse = owned(
        collection(client, base), config["lakehouseName"],
        description, config.get("lakehouseId"),
    )
    if lakehouse is None:
        lakehouse = finish(client, client.request("POST", base, {
            "displayName": config["lakehouseName"], "description": description,
        }), result=True)
    lakehouse_id = str(UUID(lakehouse["id"]))
    lakehouse = client.request("GET", f"{base}/{lakehouse_id}")[2]
    if lakehouse.get("description") != description or lakehouse.get("displayName") != config["lakehouseName"]:
        raise ValueError("Lakehouse ownership changed")
    return workspace_id, lakehouse_id


def seed_tables(path):
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schemaVersion") != "instruct.seed.v1" or registry.get("synthetic") is not True:
        raise ValueError("Only instruct.seed.v1 synthetic ingestion is permitted")
    membership = registry["membership"]
    rows = {
        "instruct_membership": [
            {**{k: v for k, v in membership.items() if k != "studentIds"}, "studentId": student}
            for student in membership["studentIds"]
        ],
        "instruct_items": [
            {"itemId": key, **value, **registry["class"]}
            for key, value in registry["items"].items()
        ],
        "instruct_responses": [
            {**row, **registry["class"]} for row in registry["responses"]
        ],
    }
    output = {}
    for name, values in rows.items():
        if not values:
            raise ValueError(f"Empty seed table {name}")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted(values[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)
        output[name] = (stream.getvalue().encode("utf-8"), len(values))
    return output


def seed(client, workspace_id, lakehouse_id, tables):
    for name, (payload, _) in tables.items():
        # Content-addressed files + Overwrite table loads avoid duplicate rows on rerun.
        digest = hashlib.sha256(payload).hexdigest()
        relative = f"Files/{name}_{digest}.csv"
        url = f"{ONELAKE}/{workspace_id}/{lakehouse_id}/{relative}"
        options = {"audience": "https://storage.azure.com/", "raw": True}
        client.request("PUT", url + "?resource=file", **options)
        client.request("PATCH", url + "?action=append&position=0", payload, **options)
        client.request("PATCH", url + f"?action=flush&position={len(payload)}", **options)
        finish(client, client.request(
            "POST", f"{FABRIC}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables/{name}/load",
            {"relativePath": relative, "pathType": "File", "mode": "Overwrite",
             "formatOptions": {"format": "Csv", "header": True, "delimiter": ","}},
        ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("data") / "instruct" / "registry.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    config = validate(json.loads(args.config.read_text(encoding="utf-8")))
    tables = seed_tables(args.registry)
    summary = {name: {"rows": count, "sha256": hashlib.sha256(data).hexdigest()}
               for name, (data, count) in tables.items()}
    if not args.apply:
        print(json.dumps({"mode": "offline-plan", "tables": summary}, indent=2))
        return
    for subscription in {config["appSubscriptionId"], config["capacitySubscriptionId"]}:
        account = az_json("account", "show", "--subscription", subscription)
        if account["tenantId"].lower() != config["tenantId"] or account["state"] != "Enabled":
            raise ValueError("Explicit subscriptions must be enabled and in the approved tenant")
    client = Client(config)
    workspace_id, lakehouse_id = ensure_targets(client, config)
    # Print IDs before seeding so partial runs can be pinned explicitly on recovery.
    print(json.dumps({"workspaceId": workspace_id, "lakehouseId": lakehouse_id}))
    if args.seed:
        seed(client, workspace_id, lakehouse_id, tables)
        print(json.dumps({"loadOperationsSucceeded": summary, "queryReadiness": "NOT VERIFIED"}))


if __name__ == "__main__":
    main()
