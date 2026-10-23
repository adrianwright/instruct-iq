"""Idempotent Viewer grant on an explicitly owned new Fabric workspace.

This does not grant model Build: Power BI's dataset-user POST/PUT APIs explicitly
exclude service principals. Never substitute Contributor for Read + Build.
"""
import argparse
import json
from pathlib import Path
from uuid import UUID

from fabric import Client, FABRIC, collection, marker, validate


def ensure_viewer(client, config, principal_id):
    config = validate(config)
    workspace_id = str(UUID(config["workspaceId"]))
    principal_id = str(UUID(principal_id))
    base = f"{FABRIC}/workspaces/{workspace_id}"
    workspace = client.request("GET", base)[2]
    if (
        workspace.get("id") != workspace_id
        or workspace.get("displayName") != config["workspaceName"]
        or workspace.get("description") != marker(config)
        or workspace.get("capacityId") != config["fabricCapacityId"]
    ):
        raise ValueError("Refusing workspace without exact deployment ownership")
    assignments = collection(client, base + "/roleAssignments")
    existing = [a for a in assignments if a["principal"]["id"] == principal_id]
    if existing:
        if (
            len(existing) != 1 or existing[0]["role"] != "Viewer"
            or existing[0]["principal"].get("type") != "ServicePrincipal"
        ):
            raise ValueError("Existing role differs; refusing implicit privilege changes")
        return existing[0]
    client.request("POST", base + "/roleAssignments", {
        "principal": {"id": principal_id, "type": "ServicePrincipal"}, "role": "Viewer",
    })
    verified = [a for a in collection(client, base + "/roleAssignments")
                if a["principal"]["id"] == principal_id and a["role"] == "Viewer"
                and a["principal"].get("type") == "ServicePrincipal"]
    if len(verified) != 1:
        raise ValueError("Viewer grant could not be verified")
    return verified[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = validate(json.loads(args.config.read_text(encoding="utf-8-sig")))
    principal_id = str(UUID(args.principal_id))
    if not args.apply:
        print(json.dumps({"workspaceId": config["workspaceId"], "principalId": principal_id,
                          "role": "Viewer", "apply": False, "modelBuildGranted": False}))
    else:
        print(json.dumps(ensure_viewer(Client(config), config, principal_id)))
