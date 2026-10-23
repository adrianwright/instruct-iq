import base64
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from fabric import FABRIC, finish
from publish import (
    SearchClient, model_definition, publish_search, refresh_model, search_definitions, snapshot_table, snapshots,
)


class PublishTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location("generator", root / "data" / "instruct" / "generate.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        self.registry = generator.generate()
        self.config = {
            "tenantId": "tenant-live", "workspaceId": "workspace", "lakehouseId": "lakehouse",
            "deploymentId": "deployment",
            "syntheticApproverId": "ba12c12b-23b2-5b85-a3fe-89361cf8a461",
        }
        self.values = snapshots(self.registry, self.config, "https://instruction.search.windows.net")

    def test_complete_native_projection(self):
        self.assertEqual(self.values["fabric"]["recordCount"], 70)
        self.assertEqual(self.values["foundry"]["recordCount"], 6)
        self.assertEqual(snapshot_table(self.values["fabric"])[1], 70)
        self.assertNotIn("test_double", json.dumps(self.values))
        for source, value in self.values.items():
            self.assertEqual(value["tenantId"], "tenant-live")
            for record in value["records"]:
                self.assertNotIn("evidenceRefs", record["fact"])
                self.assertEqual(record["revision"].__len__(), 64)
                self.assertTrue(record["locator"].startswith("fabric://" if source == "fabric" else "https://"))
                self.assertEqual(record["approval"] is None, source == "fabric")

    def test_reproducible_content_revisions(self):
        self.assertEqual(self.values, snapshots(self.registry, self.config, "https://instruction.search.windows.net"))
        self.registry["sources"][0]["facts"][0]["objective"] = "Changed objective"
        changed = snapshots(self.registry, self.config, "https://instruction.search.windows.net")
        self.assertNotEqual(self.values["foundry"]["revision"], changed["foundry"]["revision"])

    def test_approval_requires_explicit_operator_object_id(self):
        for invalid in [None, "", "synthetic-district-authority"]:
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError)):
                snapshots(self.registry, {**self.config, "syntheticApproverId": invalid},
                          "https://instruction.search.windows.net")
        self.assertTrue(all(r["approval"]["approvedBy"] == self.config["syntheticApproverId"]
                            for r in self.values["foundry"]["records"]))

    def test_write_target_must_match_canonical_arm_endpoint(self):
        config = {**self.config, "appSubscriptionId": "subscription",
                  "searchResourceId": "/subscriptions/subscription/resourceGroups/rg-instruct-iq/"
                  "providers/Microsoft.Search/searchServices/instruction"}
        actual = {"tags": {"project": "instruct-iq", "managedBy": "instruct-phase-c"},
                  "properties": {"endpoint": "https://instruction.search.windows.net", "status": "running"}}
        with patch("publish.az_json", side_effect=[{"tenantId": "tenant-live"}, actual]):
            SearchClient(actual["properties"]["endpoint"], config).verify_target()
        with patch("publish.az_json", side_effect=[{"tenantId": "tenant-live"}, actual]):
            with self.assertRaisesRegex(ValueError, "endpoint"):
                SearchClient("https://different.search.windows.net", config).verify_target()

    def test_existing_demo_target_refused_without_arm_call(self):
        config = {**self.config, "appSubscriptionId": "subscription",
                  "searchResourceId": "/subscriptions/subscription/resourceGroups/old-demo/"
                  "providers/Microsoft.Search/searchServices/demo"}
        with patch("publish.az_json") as az:
            with self.assertRaisesRegex(ValueError, "isolated"):
                SearchClient("https://demo.search.windows.net", config).verify_target()
        az.assert_not_called()

    def test_target_failure_prevents_all_data_plane_calls(self):
        class Client:
            def verify_target(self):
                raise ValueError("untracked target")
            def request(self, *args, **kwargs):
                raise AssertionError("must not reach data plane")
        with self.assertRaisesRegex(ValueError, "untracked"):
            publish_search(Client(), self.config, self.values["foundry"])

    def test_model_contains_exact_adapter_columns(self):
        definition = model_definition(self.values["fabric"])
        bim = json.loads(base64.b64decode(definition["parts"][0]["payload"]))
        table = bim["model"]["tables"][0]
        self.assertEqual(table["name"], "InstructSnapshots")
        self.assertEqual([c["name"] for c in table["columns"]],
                         ["TenantId", "ClassId", "AssessmentId", "PlanningCutoff", "Snapshot"])
        self.assertEqual(table["partitions"][0]["mode"], "import")

    def test_scope_fields_filterable_and_snapshot_retrievable(self):
        definitions = search_definitions(self.config)
        fields = {f["name"]: f for f in definitions[0][1]["fields"]}
        for name in ["tenantId", "classId", "assessmentId", "planningCutoff"]:
            self.assertTrue(fields[name]["filterable"])
        self.assertTrue(fields["snapshot"]["retrievable"])
        self.assertNotIn("models", definitions[2][1])

    def test_regional_location_uses_canonical_operation_uuid(self):
        class Client:
            def request(self, method, url):
                self.url = url
                return 200, {}, {"status": "Succeeded"}
        client = Client()
        with patch("fabric.time.sleep"):
            finish(client, (202, {"LOCATION": "https://regional.analysis.windows.net/v1/operations/x",
                                 "X-MS-OPERATION-ID": "11111111-2222-3333-4444-555555555555"}, {}))
        self.assertEqual(client.url, FABRIC + "/operations/11111111-2222-3333-4444-555555555555")

    def test_search_conflict_prevents_all_writes(self):
        calls = []
        class Client:
            def verify_target(self):
                pass
            def request(self, method, path, *args, **kwargs):
                calls.append(method)
                return {"description": "another-deployment"}
        with self.assertRaisesRegex(ValueError, "ownership"):
            publish_search(Client(), self.config, self.values["foundry"])
        self.assertEqual(calls, ["GET"])

    def test_search_all_reads_precede_conditional_creates(self):
        calls = []
        class Client:
            def verify_target(self):
                pass
            def request(self, method, path, body=None, create=False):
                calls.append((method, create))
                if method == "GET":
                    raise HTTPError(path, 404, "Not found", {}, None)
                return {"value": [{"status": True}]}
        publish_search(Client(), self.config, self.values["foundry"])
        self.assertEqual(calls[:3], [("GET", False)] * 3)
        self.assertEqual(calls[3:6], [("PUT", True)] * 3)

    def test_missing_index_then_foreign_source_never_creates_index(self):
        calls = []
        class Client:
            def verify_target(self):
                pass
            def request(self, method, path, *args, **kwargs):
                calls.append(method)
                if len(calls) == 1:
                    raise HTTPError(path, 404, "Not found", {}, None)
                return {"description": "foreign"}
        with self.assertRaisesRegex(ValueError, "ownership"):
            publish_search(Client(), self.config, self.values["foundry"])
        self.assertEqual(calls, ["GET", "GET"])

    def test_same_marker_but_drifted_source_is_not_overwritten(self):
        definitions = dict(search_definitions(self.config))
        source = definitions["/knowledgesources('instruct-approved-source')"]
        source["searchIndexParameters"]["sourceDataFields"] = [{"name": "generatedAnswer"}]
        calls = []
        class Client:
            def verify_target(self):
                pass
            def request(self, method, path, *args, **kwargs):
                calls.append(method)
                return definitions[path]
        with self.assertRaisesRegex(ValueError, "snapshot mapping"):
            publish_search(Client(), self.config, self.values["foundry"])
        self.assertEqual(calls, ["GET", "GET"])

    def test_completed_refresh_is_not_replayed(self):
        calls = []
        class Client:
            def request(self, method, path, body=None):
                calls.append(method)
                return {"value": [{"status": "Completed"}]}
        refresh_model(Client(), self.config, "model")
        self.assertEqual(calls, ["GET"])

    def test_live_kb_null_defaults_preserve_guarded_idempotency(self):
        definitions = dict(search_definitions(self.config))
        definitions["/knowledgebases('instruct-approved-kb')"]["knowledgeSources"][0].update(
            enableImageServing=None, enableFreshness=None,
        )
        class Client:
            def verify_target(self):
                pass
            def request(self, method, path, *args, **kwargs):
                return definitions[path] if method == "GET" else {"value": [{"status": True}]}
        result = publish_search(Client(), self.config, self.values["foundry"])
        self.assertEqual(result["documents"], 1)

    def test_pending_refresh_is_polled_not_replayed(self):
        calls = []
        class Client:
            def request(self, method, path, body=None):
                calls.append(method)
                return {"value": [{"status": "Unknown" if len(calls) == 1 else "Completed"}]}
        with patch("publish.time.sleep"):
            refresh_model(Client(), self.config, "model")
        self.assertEqual(calls, ["GET", "GET"])


if __name__ == "__main__":
    unittest.main()
