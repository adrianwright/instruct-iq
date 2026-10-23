# Instruct IQ API

FastAPI backend hosting the GPT-5.6 Luna classroom chat agent and optional
instructional planning. Foundry hosts the model; the agent tool loop and
principal-scoped conversation history run in this API, not Foundry Agent Service.

```powershell
Push-Location services\api
python -m uvicorn app.main:app --reload --port 8000
Pop-Location
```

Primary endpoints:

- `GET /api/instruct/v1/classes`
- `POST /api/instruct/v1/chat`
- `POST /api/instruct/v1/plan`
- `POST /api/instruct/v1/plan/stream`
- `GET /api/instruct/v1/classes/{class_id}/plans/{plan_id}/evidence/{ref_id}`

Instructional routes require configured Entra authentication and explicit class
grants, even in development. Provider coordinates alone do not authorize a user.
The existing commercial routes remain temporarily for regression coverage.

Run tests from this directory with `python -m pytest`.

Chat sends each retrieved fact's evidence IDs and a minimal citation inventory
(ID, source and title) to the model. Citation locators and provenance remain
server-owned; selecting facts automatically includes their verified citations.
An unavailable Work IQ source does not remove Fabric or Foundry evidence.

## Connected adapters (implementation checkpoint)

Instructional runtime does not read seed files or accept generated provider
answers as facts. Its raw ingestion boundary is
`app.instruct_adapters.NativeSnapshot` (`instruct.native-snapshot.v1`).
This is an application ingestion contract, **not** a vendor-native schema.
It has tenant/class/assessment/cutoff, native snapshot revision, complete kind
coverage, record count, and records with native ID/revision/locator/title,
typed fact fields (without evidenceRefs), and approval metadata. Foundry
approvals must bind the fact approval ID, precede effectiveness/cutoff, and name
an operator-authorized approver. The ingestion publisher must populate and
maintain authentic source revisions, complete histories and approval records;
declaring this schema alone is not evidence of ingestion or live readiness.

Required settings:

- `INSTRUCT_FABRIC_SEMANTIC_MODEL_ID`: dedicated Fabric semantic model UUID.
  The read-only Power BI Execute Queries API queries an `InstructSnapshots`
  table with string columns `TenantId`, `ClassId`, `AssessmentId`,
  `PlanningCutoff` (ISO timestamp), and `Snapshot` (snapshot JSON fragment).
  Each row contains exactly one record, with identical repeated snapshot metadata
  and the total snapshot `recordCount`. This avoids semantic-model text-cell
  limits. Rows are assembled only when manifests agree; the total count and
  unique record IDs must match, including after a silent truncated response.
  No arbitrary model/table selection.
  Requires read/build rights, the tenant Execute Queries setting, and a compatible
  identity. Service principals cannot query models with RLS/SSO. No impersonation
  or consent/activation is performed by this code.
- `INSTRUCT_SEARCH_ENDPOINT`, `INSTRUCT_FOUNDRY_KB_NAME`,
  `INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE`,
  `INSTRUCT_SEARCH_API_VERSION=2026-08-01-preview`: dedicated Search-backed
  Foundry IQ KB with exactly the named search-index knowledge source.
  Filterable string fields: `tenantId`, `classId`, `assessmentId`,
  `planningCutoff`; sourceData must include a retrievable `snapshot` string.
  Exactly one reference and one matching source activity/result are required.
  The adapter discovers KB source membership, requests extractive data and
  reference sourceData, applies deterministic scope filters, and never uses
  synthesized text. Missing fields, partial/error results and ambiguity fail.
- `INSTRUCT_APPROVER_IDS_JSON`: explicit JSON array of authorized curriculum,
  support, schedule and resource approver IDs; empty denies Foundry retrieval.
- `INSTRUCT_CLASS_GRANTS_JSON` remains explicit, operator-maintained authorization,
  **not** a connected roster/membership authority. Provider identities use
  `DefaultAzureCredential`; grants authorize class/assessment before retrieval.
  Search identity additionally needs KB-definition read and data-read access.

Fabric MCP is documented as a question/grounded-answer tool, not an
authenticated raw-record API. Existing generic MCP/legacy narrative clients
are intentionally not promoted to factual authority or changed. Their
workspace/tool settings alone do not enable this raw semantic-model path.
Work is optional and disabled until its separate delegated configuration and
native-source verification are complete. Web remains unavailable. The runtime preserves independent source
results, enforces provider/request deadlines, and rejects invalid evidence.

Protocol references checked October 15, 2026:
[Fabric MCP](https://learn.microsoft.com/fabric/data-science/data-agent-mcp-server),
[Execute Queries](https://learn.microsoft.com/rest/api/power-bi/datasets/execute-queries),
[Search retrieve](https://learn.microsoft.com/rest/api/searchservice/knowledge-retrieval/retrieve?view=rest-searchservice-2026-08-01-preview).
No cloud endpoints, identities, records, ingestion, approval authority, model
rights, or connected completeness were live-verified in this implementation.

## Optional live Work IQ in chat

`app.instruct_workiq_a2a` reuses the certificate-backed `WorkIQClient` for
caller-delegated, read-only A2A queries. It never uses the Graph verification
helper's token or the Copilot CLI account. Graph provisioning/verification and
Work IQ retrieval are separate operations with separate token audiences.

Enable only after native source readback:

- `INSTRUCT_WORKIQ_ENABLED=true`
- `INSTRUCT_WORKIQ_MANIFEST_JSON`: server-owned verified source manifest, matching
  the caller's tenant, Entra object ID, and authorized class. Accepts the three
  manually created self-chat sources, or the original four-source inventory.
  Pending, unverified, duplicate, foreign or incomplete sources fail closed.
- `WORK_IQ_CLIENT_ID`: dedicated Instruct IQ API application.
- `WORK_IQ_ENDPOINT=https://workiq.svc.cloud.microsoft/a2a/`
- `WORK_IQ_SCOPE=api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask`
- `WORK_IQ_KEY_VAULT_URL`, `WORK_IQ_CLIENT_CERTIFICATE_SECRET_NAME`: dedicated
  exportable OBO certificate, accessed using the API managed identity.
- `INSTRUCT_WORKIQ_TIMEOUT_SECONDS`: bounded Work IQ request timeout, default
  120 seconds (maximum 180). Overall chat timeout defaults to 180 seconds.
  These client deadlines do not override a timeout enforced inside Work IQ or
  its MCP tools.

Work IQ answers are explicitly labelled AI summaries of fictional collaboration,
not verbatim native records, student observations or approved curriculum.
Only citations matching the approved source identities are accepted, including
equivalent Teams links with matching message, chat and owner/tenant context; uncited or
out-of-scope answers are unavailable, not successful empty results. Conversation
access signatures include the Work IQ manifest and enabled state, preventing
reuse after operator configuration changes. Nothing is posted or published.
Protocol failures log only a fixed reason and numeric JSON-RPC code, not native
content, prompts, tokens or the service's free-form error message.

`agent\provisioning\instruct\workiq_obo.py` configures only the dedicated API,
per-operator `WorkIQAgent.Ask` consent, and a new certificate in its own Key Vault.
Private keys never leave Key Vault through the provisioning script. The API
identity receives secret-read access only to that certificate's backing secret.
Successful provisioning does not prove a live OBO exchange or retrieval.
