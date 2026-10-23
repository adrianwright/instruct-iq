"""Synthetic deployment coordinates, loaded before tests import Work IQ modules."""
import os

os.environ.update({
    "INSTRUCT_WORKIQ_TENANT_ID": "d9eb725c-64c7-5769-8557-418fda0f460f",
    "INSTRUCT_WORKIQ_API_CLIENT_ID": "242fb8bd-1383-55d3-a6ff-c5ef09ff0de2",  # gitleaks:allow -- synthetic public client ID
    "INSTRUCT_WORKIQ_OPERATOR_ID": "ba12c12b-23b2-5b85-a3fe-89361cf8a461",
    "INSTRUCT_WORKIQ_SUBSCRIPTION_ID": "6a0d8700-ca33-5e7f-be54-b49e0a61a15b",
    "INSTRUCT_WORKIQ_IDENTITY_PRINCIPAL_ID": "0e29e0f2-ca26-588f-a314-f5a7905f046f",
    "INSTRUCT_WORKIQ_VAULT_NAME": "instruct-test-kv",
    "INSTRUCT_WORKIQ_API_RESOURCE_ID": (
        "/subscriptions/6a0d8700-ca33-5e7f-be54-b49e0a61a15b/resourceGroups/rg-instruct-iq"
        "/providers/Microsoft.App/containerApps/instruct-test-api"
    ),
    "INSTRUCT_WORKIQ_EXPECTED_IMAGE": "instructtest.azurecr.io/instruct-api:test",
})
