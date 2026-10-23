import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("instruct_fabric", Path(__file__).with_name("fabric.py"))
fabric = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fabric)

SUB = "11111111-1111-1111-1111-111111111111"
CAP = "22222222-2222-2222-2222-222222222222"
DEP = "33333333-3333-3333-3333-333333333333"
WS = "44444444-4444-4444-4444-444444444444"
LH = "55555555-5555-5555-5555-555555555555"
CONFIG = {
    "appSubscriptionId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "tenantId": SUB, "deploymentId": DEP, "fabricCapacityId": CAP,
    "capacityResourceId": f"/subscriptions/{SUB}/resourceGroups/shared/providers/Microsoft.Fabric/capacities/approved",
    "workspaceName": "instruct-iq", "lakehouseName": "instruct_iq",
}


class FakeClient:
    def __init__(self, workspace=True, lakehouse=True):
        self.calls = []
        self.capacity = {"id": CAP, "azureResourceId": CONFIG["capacityResourceId"], "state": "Active"}
        self.workspace = {
            "id": WS, "displayName": "instruct-iq",
            "description": fabric.marker(CONFIG), "capacityId": CAP,
        } if workspace else None
        self.lakehouse = {
            "id": LH, "displayName": "instruct_iq", "description": fabric.marker(CONFIG),
        } if lakehouse else None

    def request(self, method, url, body=None, **kwargs):
        self.calls.append((method, url, body))
        if method == "POST" and url.endswith("/workspaces"):
            self.workspace = {"id": WS, **body}
            return 201, {}, self.workspace
        if method == "POST" and url.endswith("/lakehouses"):
            self.lakehouse = {"id": LH, **body}
            return 201, {}, self.lakehouse
        if url.endswith("/capacities"):
            return 200, {}, {"value": [self.capacity]}
        if url.endswith("/workspaces"):
            return 200, {}, {"value": [self.workspace] if self.workspace else []}
        if url.endswith("/lakehouses"):
            return 200, {}, {"value": [self.lakehouse] if self.lakehouse else []}
        if url.endswith(WS):
            return 200, {}, self.workspace
        if url.endswith(LH):
            return 200, {}, self.lakehouse
        return 200, {}, {}


class FabricTests(unittest.TestCase):
    def test_azure_cli_uses_resolved_windows_launcher(self):
        with patch.object(fabric.shutil, "which", return_value=r"C:\Azure\az.cmd"), patch.object(
            fabric.subprocess, "run"
        ) as run:
            run.return_value.stdout = '{"state":"Enabled"}'
            self.assertEqual(fabric.az_json("account", "show"), {"state": "Enabled"})
            self.assertEqual(run.call_args.args[0][0], r"C:\Azure\az.cmd")

    def test_separate_capacity_and_application_subscriptions(self):
        config = fabric.validate(CONFIG)
        self.assertEqual(config["capacitySubscriptionId"], SUB)
        self.assertNotEqual(config["appSubscriptionId"], SUB)

    def test_token_rejects_wrong_tenant_before_acquisition(self):
        with patch.object(fabric, "az_json", return_value={"tenantId": DEP, "state": "Enabled"}) as az:
            with self.assertRaisesRegex(ValueError, "approved tenant"):
                fabric.Client(fabric.validate(CONFIG)).request("GET", fabric.FABRIC + "/capacities")
            self.assertEqual(az.call_count, 1)

    def test_wrong_names_and_arm_ids_rejected(self):
        for key, value in [
            ("workspaceName", "existing-demo"), ("lakehouseName", "isv"),
            ("capacityResourceId", "/subscriptions/shared"),
            ("lakehouseId", LH),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                fabric.validate({**CONFIG, key: value})

    def test_existing_owned_resources_are_noop(self):
        client = FakeClient()
        self.assertEqual(fabric.ensure_targets(client, CONFIG), (WS, LH))
        self.assertTrue(all(call[0] == "GET" for call in client.calls))

    def test_new_targets_and_partial_run_recovery(self):
        client = FakeClient(workspace=False, lakehouse=False)
        with patch.object(client, "request", wraps=client.request) as request:
            fabric.ensure_targets(client, CONFIG)
            self.assertEqual(sum(call.args[0] == "POST" for call in request.call_args_list), 2)
        # A prior workspace creation succeeded but the lakehouse request did not.
        client.lakehouse = None
        client.calls.clear()
        fabric.ensure_targets(client, CONFIG)
        self.assertEqual([call[1] for call in client.calls if call[0] == "POST"],
                         [f"{fabric.FABRIC}/workspaces/{WS}/lakehouses"])

    def test_wrong_capacity_and_inactive_fail_before_any_write(self):
        for key, value in [("state", "Inactive"), ("azureResourceId", "wrong"), ("id", DEP)]:
            client = FakeClient()
            client.capacity[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                fabric.ensure_targets(client, CONFIG)
            self.assertTrue(all(call[0] == "GET" for call in client.calls))

    def test_unowned_workspace_or_lakehouse_never_mutated(self):
        for item in ("workspace", "lakehouse"):
            client = FakeClient()
            getattr(client, item)["description"] = "Existing demo"
            with self.subTest(item=item), self.assertRaises(ValueError):
                fabric.ensure_targets(client, CONFIG)
            self.assertTrue(all(call[0] == "GET" for call in client.calls))

    def test_workspace_moved_capacity_and_wrong_explicit_id_rejected(self):
        client = FakeClient()
        client.workspace["capacityId"] = DEP
        with self.assertRaises(ValueError):
            fabric.ensure_targets(client, CONFIG)
        with self.assertRaises(ValueError):
            fabric.ensure_targets(FakeClient(), {**CONFIG, "workspaceId": DEP})

    def test_ambiguous_names_rejected(self):
        with self.assertRaises(ValueError):
            fabric.owned([{"displayName": "instruct-iq"}] * 2, "instruct-iq", "")

    def test_seeds_are_deterministic_synthetic_rows_not_test_double_provenance(self):
        path = Path(__file__).resolve().parents[3] / "data" / "instruct" / "registry.json"
        tables = fabric.seed_tables(path)
        self.assertEqual(tables, fabric.seed_tables(path))
        self.assertEqual(tables["instruct_membership"][1], 24)
        self.assertNotIn(b"test_double", b"".join(data for data, _ in tables.values()))

    def test_seed_rerun_uses_overwrite_not_append(self):
        client = FakeClient()
        tables = {"instruct_test": (b"studentId\nstudent-01\n", 1)}
        fabric.seed(client, WS, LH, tables)
        first = list(client.calls)
        client.calls.clear()
        fabric.seed(client, WS, LH, tables)
        self.assertEqual(first, client.calls)
        self.assertEqual(client.calls[-1][2]["mode"], "Overwrite")
        self.assertTrue(all(f"/{WS}/{LH}/" in url for method, url, _ in client.calls if method != "POST"))

    def test_async_load_waits_and_rejects_external_locations(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            fabric.finish(client, (202, {"Location": "https://example.com/token"}, {}))
        with patch.object(client, "request", return_value=(200, {}, {"status": "Succeeded"})), patch.object(fabric.time, "sleep"):
            self.assertEqual(fabric.finish(client, (202, {"Location": fabric.FABRIC + "/operations/123"}, {})),
                             {"status": "Succeeded"})

    def test_http_client_rejects_untrusted_host_before_token_acquisition(self):
        with patch.object(fabric, "az_json") as az:
            with self.assertRaises(ValueError):
                fabric.Client(fabric.validate(CONFIG)).request("GET", "https://example.com")
            az.assert_not_called()


if __name__ == "__main__":
    unittest.main()
