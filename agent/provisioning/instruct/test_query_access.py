import unittest
from unittest.mock import Mock

from query_access import ensure_viewer
from test_fabric import CONFIG, WS, DEP
from fabric import marker


class QueryAccessTests(unittest.TestCase):
    def client(self, role=None, owned=True):
        assignment = {"principal": {"id": DEP, "type": "ServicePrincipal"}, "role": role or "Viewer"}
        workspace = {
            "id": WS, "displayName": CONFIG["workspaceName"],
            "description": marker(CONFIG) if owned else "unowned",
            "capacityId": CONFIG["fabricCapacityId"],
        }
        client = Mock()
        client.request.side_effect = [
            (200, {}, workspace), (200, {}, {"value": [assignment] if role else []}),
            (201, {}, assignment), (200, {}, {"value": [assignment]}),
        ]
        return client

    def test_grant_and_verify_viewer_only(self):
        client = self.client()
        self.assertEqual(ensure_viewer(client, {**CONFIG, "workspaceId": WS}, DEP)["role"], "Viewer")
        self.assertEqual(client.request.call_args_list[2].args[2], {
            "principal": {"id": DEP, "type": "ServicePrincipal"}, "role": "Viewer",
        })

    def test_existing_viewer_is_noop(self):
        client = self.client("Viewer")
        ensure_viewer(client, {**CONFIG, "workspaceId": WS}, DEP)
        self.assertEqual(client.request.call_count, 2)

    def test_refuses_unowned_workspace(self):
        client = self.client(owned=False)
        with self.assertRaisesRegex(ValueError, "ownership"):
            ensure_viewer(client, {**CONFIG, "workspaceId": WS}, DEP)
        self.assertEqual(client.request.call_count, 1)

    def test_refuses_different_existing_role(self):
        client = self.client("Admin")
        with self.assertRaisesRegex(ValueError, "role differs"):
            ensure_viewer(client, {**CONFIG, "workspaceId": WS}, DEP)
        self.assertEqual(client.request.call_count, 2)
