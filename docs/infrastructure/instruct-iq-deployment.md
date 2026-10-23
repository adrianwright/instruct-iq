# Instruct IQ: isolated foundation deployment

Public-release note: environment identifiers and service coordinates in this
historical narrative have been replaced with synthetic examples. Supply your
own explicit, approved values; these examples are not deployment defaults.
The chat-model template requires an explicit `foundryAccountName`.

## Confirmed chat truncation and output-budget fix - October 16, 2026

Diagnostic request `45c8d276-48da-5475-bee8-8f11c8d2e82a` established the cause of
the reproduced browser failure: model turn 2 returned `status=incomplete`,
`incomplete_reason=max_output_tokens` while emitting an `answer` tool call.
Retrieval had already completed. The model consumed all **1,400 output tokens**
(including **123 reasoning tokens**) after **9,004 input tokens**. The server
correctly refused to publish the truncated structured answer; authentication or
session expiration was not the cause of this request's failure.

**Deployed** an increased per-response allowance of **4,096 output tokens**,
retaining low reasoning, the same model/deployment, tool schemas, validation,
timeouts and fail-closed behavior. This is an inference-request bound, not a
model-capacity increase. If truncation recurs, the user-facing error now names
the response-length limit and includes its diagnostic ID rather than suggesting
model access or source availability.

ACR build **cjf**, immutable image
`instructexample.azurecr.io/instruct-api@sha256:fb836b070daaf98d5024fd9eb5d5c8ff30508bb05c795a5e02bc3abe600aa078`.
Latest and ready revision **`instruct-example-api--0000013`** is Running,
provisioning Succeeded; health returned 200. The image-only release guard
confirmed unchanged protected runtime configuration, identities, grants,
provisioned model allocation and scaling. No UI deployment.

All **54 targeted chat tests passed**, including a transport assertion that the
actual Responses request uses 4,096 tokens and JSON/SSE truncation errors remain
correlated and fail closed. Python compilation passed.

The exact suggested Fabric/Foundry question was then exercised inside the new
deployed container using the configured synthetic operator/class grant. Both
sources and final validation succeeded: **27 observations and 27 citations**.
The final model response was completed, with 9,004 input tokens, 869 output tokens
and 154 reasoning tokens. Generation varies between runs; this successful
response did not itself need more than the old limit. The observed failure's
explicit `max_output_tokens` reason, plus the transport regression, establishes
the fix rather than attributing the problem to unavailable sources.

This is hosted integration evidence, not a user-authenticated browser journey.
Start a new conversation before the browser retry because rollout replaces
in-memory sessions. Ignored live evidence:
`.local\instruct-iq-deployment\chat-output-budget-live-verification.txt`.

## Request-correlated chat diagnostics - October 16, 2026

**Deployed** an API-only diagnostic update. Every server-owned chat validation
failure now logs a distinct reason code, request ID, model-turn/tool counts, and
allowlisted response metadata: completion status, incomplete reason, tool counts,
input/output tokens and reasoning tokens. Unknown status/reason/tool names are
reduced to `other`. Prompts, source content, tool arguments, model prose,
credentials and upstream exception messages are not logged. JSON and streaming
requests use the same request ID in the diagnostic log and error response; generic
chat failures now display that diagnostic ID in the existing UI.

ACR build **cje**, immutable image
`instructexample.azurecr.io/instruct-api@sha256:6fd85fad40f959dcd3afa9420d9fa0512e210f6cf3f841504268b5d2433a8270`.
Latest and ready revision **`instruct-example-api--0000012`** is Running,
provisioning Succeeded. Health returned 200; anonymous classes and streaming chat
remain 401. The image-only release guard confirmed unchanged protected runtime
configuration, identities, grants, model allocation and scaling. No UI release.
The rollout replaces in-memory conversations; start a new conversation before
retrying the failed question.

All **53 targeted chat tests passed**, including JSON/SSE request correlation,
incomplete responses, malformed arguments, mixed tools, budget failures and
content-safe logging. Python compilation passed. Repository-wide Pyright remains
blocked by 10 errors in existing logic; it is not reported as passing.

A clearly labeled synthetic incomplete-response injection inside the deployed
container verified the exact reason code, token metadata, diagnostic-ID
correlation and refusal to publish an answer. A separate real model/Fabric/Foundry
invocation then completed with **21 observations and 21 citations**. This is
hosted runtime evidence, not a user-authenticated browser journey. No new real
chat failure was present in the final console-log check.

The historical 08:46 Eastern rejection is still undetermined: its discarded
exception detail cannot be recovered. These diagnostics enable an exact
classification on recurrence; successful probes do not establish its cause.
Ignored release evidence:
`.local\instruct-iq-deployment\chat-diagnostics-live-verification.txt`,
`conversation-api-release.json`.

## Parallel source retrieval and empty-start conversation — October 16, 2026

**Deployed** to the same production UI/API. The model may select independent
Fabric, Foundry, and Work retrievals in one turn. The server validates and
authorizes every call before starting any source, restricts each batch to one
class/assessment and one call per source, then runs it concurrently. Each source
retains independent timing and status; the next model call waits for every result.
Dependent retrievals can still run in later turns. Mixed answer/retrieval batches
are rejected, the existing six-call total budget remains enforced, and errors or
cancellation join outstanding tasks before releasing the session. Final access
and citation validation remain required.

Removed the entire “Start with a question” section and all sample-question
buttons. The empty conversation opens directly to the message composer. The
activity panel indicates simultaneous retrievals and continues showing the
remaining active source when its siblings finish.

ACR build **cjd**, image
`instructexample.azurecr.io/instruct-api:20261016-parallel-iq-123857`,
latest/ready revision **`instruct-example-api--0000011`**, **Running**,
provisioning **Succeeded**, API health **200**. Protected runtime configuration
was unchanged. The image-only release guard now compares matching fresh
Container App reads rather than differently serialized update/read responses.

Production assets `index-ynE9Hts9.js` and `index-BsDYBCbf.css` match the release
build. Edge verified removal of the introductory section and sample buttons,
visible message composer and backend panel, desktop/mobile layouts, dark theme,
no horizontal overflow at 390px/320px, and no JavaScript errors. Anonymous classes
and streaming chat remain **401**. Deterministic tests verify actual overlap,
out-of-order completion, per-source timing, authorization-before-start,
unavailable sources, sibling cancellation, and refusal to publish after access
changes. Live authenticated multi-source inference was not exercised for this
release.

Ignored release evidence: `.local\instruct-iq-deployment\parallel-iq-*`.

## Streamlined workspace and live backend activity — October 16, 2026

**Deployed and verified** at https://ui.example.invalid.
The workspace now uses a simpler Microsoft Learn-inspired layout with a
persistent backend activity panel. Chat requests SSE progress for actual model
calls, Fabric/Foundry/Work retrievals, and answer validation. Step results retain
timing, evidence counts, and availability reasons. Uncalled sources are not
presented as successful; Web remains unavailable in classroom chat. Existing
JSON chat clients remain supported.

ACR build **cjc**, image
`instructexample.azurecr.io/instruct-api:20261016-live-status-122116`,
API latest/ready revision **`instruct-example-api--0000010`**. The API
was stopped and required the supported Container Apps start action after rollout;
final running status is **Running**, provisioning **Succeeded**, health **200**.
The image-only release guard flagged service-populated storage and scaling
defaults. Follow-up revision reads confirmed unchanged environment variables,
CPU, memory, minimum/maximum replicas, and the expected managed identity. No
authorization, provider, consent, capacity, or model settings were changed.

Production JavaScript `index-BfE99FCW.js` and CSS `index-DIndOzUh.css` match the
release build byte-for-byte. Installed Edge confirmed the visible backend panel,
desktop two-column layout, no overflow at 390px and 320px, dark theme, disabled
anonymous Send, and no JavaScript errors. Anonymous classes and streaming chat
both return **401**. The authenticated deployed chat journey was not exercised
for this release; local streaming, cancellation, and authorization regressions
passed before publication.

Ignored release evidence and desktop/mobile screenshots are under
`.local\instruct-iq-deployment\live-status-*`.

## General classroom chatbot release — October 15, 2026

**Deployed and rollout verified**, superseding the bounded-command/canvas UI
described in historical entries below. The primary experience is pure classroom
chat: no required class/assessment selectors or separate lesson canvas.

- UI: https://ui.example.invalid
- API: https://instruct-example-api.example.invalid
- ACR build **cj6**, immutable API image digest
  `sha256:db56cd0789d5f0616fde182697150415c1df94a409e11609a67d03bb758f07d9`.
  Latest **and ready** revision:
  **`instruct-example-api--0000004`**, provisioning **Succeeded**,
  running container ready with zero restarts at verification.
- API health **200**; anonymous classes **401**, anonymous chat **401**.
  Dedicated auth/grants, existing F4, identity and resource capacity unchanged.
- Runtime settings point to exact **`gpt-5.6-luna`**, deployment
  **`instruct-chat-luna`**, resource root
  `https://instruct-example-ai.openai.azure.com`, Azure Responses v1,
  UAMI token scope `https://cognitiveservices.azure.com/.default`.
  The separately verified model handoff covers strict function calls and
  continuation, `store:false`, low reasoning and 1,400 output-token budget.
- A bounded invocation **inside the actual hosted API container** called its
  installed `ChatService`, actual model, and actual Foundry source with a
  server-configured synthetic operator/class grant. Authorization ran before
  tools; the result contained **4 observations, 4 citations and model prose**.
  No HTTP authentication bypass endpoint, browser token or terminal WorkIQ
  token was created or used. This is runtime integration evidence, **not**
  proof of a user-authenticated browser journey.
- SWA HTML and entry JavaScript/CSS hashes exactly matched the release build.
  Entry JavaScript: `index-OtGqMaGO.js`. Installed Edge at 390px rendered heading
  **Your classroom, in conversation**, document title
  **Instruct IQ · Teacher Workspace**, zero selectors/canvas, disabled anonymous
  Send, no horizontal overflow and no JavaScript errors.
- Validation: full API suite **226 passed** before two final additional tests;
  final targeted chat suite **14 passed**. All **43 frontend tests**, lint and
  production build passed, including the preserved first-login/account-reset
  regression. Prior REST/SSE plan tests remain passing.

**Known limits:** WorkIQ explicitly reports setup-needed; caller-delegated OBO,
downstream scope and exact source manifest are not configured. No collaboration
evidence is invented. Web is not exposed as a chat tool. Model allocation remains
**5,000 TPM / 5 RPM**; the full 70-Fabric-fact chat payload has not been live load
tested. Rate limiting produces an actionable error, never another model or a
simulated answer. The authenticated browser conversation still requires normal
operator sign-in; it was not claimed complete.

Ignored release evidence:
`.local\instruct-iq-deployment\chat-release-verification.json`.
The initial long ACA exec probe hit a websocket handshake 404 before executing;
the compact retry connected and passed. No failed application rollout remained.

## First-sign-in lifecycle fix — October 15, 2026

Deployed a frontend-only correction to the existing production SWA. The previous
authentication bridge included both the MSAL account list and a revision bumped
on every login/active-account event in the workspace React key. The first popup
login therefore unmounted its own calling workspace, aborting the pending class
load and returning the UI to its pre-login state.

The workspace key now changes only when an established account is replaced or
removed, or logout starts. First identity establishment and repeated same-account
events preserve the pending operation. Unmount invalidates operation counters
before aborting requests; a late popup result cannot load classes into a cleared
workspace. Class loading shows explicit progress/success/error; authentication
errors expose sanitized MSAL/AADSTS codes and correlation IDs, never raw payloads.
Tokens remain memory-only; draft storage remains principal/class/plan scoped.

Verification: **43 frontend tests**, lint and production build passed. Added real
React/DOM regressions for first interactive sign-in completing authorized class
loading, same-account event stability, account switch clearing catalog/draft/
conversation, pending-login invalidation on logout, and actionable consent errors.
Production entry JavaScript matched the release build. Installed Edge smoke
verified the deployed workspace, responsive layout and zero JavaScript errors;
API health **200**, anonymous classes/conversation **401**. API, registration,
grants, protected configuration and infrastructure were not changed.

**Live authenticated acceptance remains unverified:** the existing visible Edge
session had no remote-debugging endpoint available for safe attachment. No tokens
or credentials were inspected. Refresh the production page, then click **Sign in /
load classes** and complete normal sign-in; a second class-load click should no
longer be necessary. Report any displayed MSAL/AADSTS code if consent blocks it;
do not grant tenant-wide consent. Ignored release evidence:
`auth-lifecycle-release-verification.json`, `conversation-browser-verification.json`.

## Conversation + lesson-canvas release — October 15, 2026

Published the first bounded-command conversational increment to the **same**
new UI/API URLs below. API ACR build `cj5`, immutable digest
`sha256:63c9e7cc601d2de99e1e15d2fabbbc621240600de765cd2596766913ecca8cd6`;
latest/ready ACA revision `instruct-example-api--0000003`, Succeeded.
Used the existing ignored manifest and release scripts, with an image-only API
release path; no auth/grant/capacity/model/infrastructure changes were requested.
The API release verification initially stopped **after** successful rollout
because it compared SDK JSON serialization; follow-up reads checked the
authorization scope/revision and runtime coordinates instead. A damaged
display-title character in the earlier saved release artifact was not treated
as an authorization change and no grant rewrite was performed.

`GET` of the dedicated Foundry account's deployment collection returned **[]**.
The delivered conversation is explicitly **deterministic bounded commands**,
not an undisclosed model call or general chat. Planning preserves actual
Fabric/Foundry retrieval/policy; explain/differentiate reuse authorized baseline
facts; revisions are scoped, reviewable proposals, never automatic application.
See `docs\contracts\instruct-v1.md` for supported prompts and exact limits.

Verification: **204 API tests**, **40 frontend tests**, production build and
lint passed. Live `/healthz` **200**, anonymous classes/conversation **401**,
new route present in served OpenAPI. Headless installed Edge verified actual
deployed two-column desktop/one-column 390px layout, visible conversation and
canvas, disabled pre-auth commands, no seeded transcript, no horizontal
overflow and no JavaScript errors. Ignored evidence:
`conversation-api-release.json`, `conversation-browser-verification.json`.

**Authenticated deployed plan/explain/apply/export remains unverified pending
normal operator interactive sign-in.** No bypass, user-token substitution,
consent or identity changes were used. The prior UAMI live-source proof remains
historical provider evidence, not an authenticated conversational journey.

## Deployed browser acceptance — October 15, 2026, 14:33 Eastern

**Checkpoint: operator interaction required; authenticated acceptance is not
complete.** Used the already-installed Python Playwright and visible Microsoft
Edge against the actual production site, without installing packages.

- UI https://ui.example.invalid returned **200**.
  The teacher workspace, disabled pre-authentication class/assessment selectors,
  and fixed **October 16 assessment → October 19 lesson, 35 minutes, 24 learners,
  October 19 07:00 America/New_York cutoff** rendered correctly. No browser
  JavaScript errors were observed. An unauthenticated full-page screenshot is
  retained only in ignored local artifacts.
- Clicking **Sign in / load classes** opened the real
  `login.microsoftonline.com` popup. It displayed the account/email input with
  no AADSTS error. No credentials were entered or scraped; the bounded browser
  session closed after waiting for operator interaction.
- Read-only Entra registration checks verified the dedicated SPA's exact
  production redirect URI, required delegated API scope, enabled user-consent
  scope, and API v2 token configuration. The actual API revision remains
  **`instruct-example-api--0000002`**, provisioning **Succeeded**.
  Runtime audience and required scope match the dedicated registration.
  The exact operator/class/assessment grant is currently valid
  (`2026-10-15T00:00Z` through `2026-11-15T00:00Z`).
- Live API
  https://instruct-example-api.example.invalid
  returned **200** on `/healthz` and **401** on anonymous
  `/api/instruct/v1/classes`. A separate supported attempt to use the existing
  Azure CLI login for **this API's exact delegated scope** failed with
  **AADSTS135010**. No token was printed or saved, no provider/ARM token was
  substituted, and no consent or permission changes were made.
- **Not verified:** authenticated classes, `/plan` or `/plan/stream`, UI groups,
  protected evidence, lesson/supports/exit ticket, local edits/reload, review
  invalidation, or Markdown/JSON exports. The earlier actual API-UAMI
  **70 Fabric + 6 Foundry / complete policy** proof remains valid but is not a
  substitute for this user-authenticated journey.

**Required operator action:** open the UI above, click **Sign in / load
classes**, select the operator account in tenant
`d9eb725c-64c7-5769-8557-418fda0f460f`, and complete normal sign-in/MFA and any
per-user consent for **Access Instruct IQ**. If administrator approval is
requested, stop and report it; do not grant tenant-wide consent. If classes do
not appear immediately after sign-in, click **Sign in / load classes** again.
Select `class-science-7a` and `assessment-20261016`, leave optional Work/Web
unchecked, and click **Build instructional plan**. The remaining acceptance
checks above can then proceed with that real authenticated session.

Updated the ignored manifest's stale top-level runtime blockers/readiness to
match the later successful UAMI proof and this browser checkpoint. Older
timestamped nested checkpoints and release snapshots remain historical.
Evidence: `.local\instruct-iq-deployment\browser-acceptance.json`,
`browser-unauthenticated.png`, and `operator-api-acceptance.json`.
No application code, registrations, grants, networks, resources or deployments
were changed; no redeployment or unit-suite rerun was needed. The intentional
Contributor grant, existing F4 and old demo resources remain unchanged.

## Fabric permission resolution — October 15, 2026, 14:30 Eastern

**Supersedes the blocked Fabric checkpoint below.** The user granted API identity
`instruct-example-api-identity` (principal/object ID
`0e29e0f2-ca26-588f-a314-f5a7905f046f`, client ID
`f3a13e63-b9ab-5b9b-8850-98b64917ffcb`) **Contributor only on the new workspace**
`d9996489-d2f4-5b55-b1cb-93e94f4f5ddc` in the Fabric portal. This intentional
grant remains in place; it was not rolled back.

- Fresh role-assignment and dataset-user reads confirm **Contributor** and
  **ReadWriteExplore**, respectively. Contributor is the lowest workspace role
  that inherits Build, but also grants Write across this workspace's items:
  it is **not** a model-only Read + Build grant. Member/Admin are unnecessary
  for the tested Execute Queries path. No capacity, old workspace, subscription
  grant, tenant setting, consent or model definition was changed.
- Actual hosted API revision `instruct-example-api--0000002`, using its
  installed native adapters and UAMI, retrieved and validated **Fabric 70 facts /
  70 connected evidence records**, **Foundry 6 facts / 6 connected evidence
  records**, and returned policy **complete**. No operator token, runtime seed
  fallback or publisher credential was supplied to the container.
- A separate short read-only hosted probe verified token claims in memory:
  audience `https://analysis.windows.net/powerbi/api`, the tenant above, exact
  UAMI object/client IDs and managed-identity ARM ID. Only those nonsecret claims
  were emitted; no token was printed or saved. Workspace GET, workspace dataset
  listing and exact dataset GET all returned **200** for that UAMI. This rules
  out a wrong token audience, wrong model ID and a blocking service-principal
  tenant policy for this tested identity/path. No tenant-policy inventory was
  needed.
- Before the user's portal change, a temporary Contributor diagnostic was
  granted and **restored to Viewer**, with both final membership and inherited
  model Read reread. Its runtime probe was inconclusive because ACA exec failed
  its websocket handshake before executing code. The subsequent user-applied
  Contributor grant is distinct. Long encoded exec commands produced handshake
  404; shorter commands against the explicit healthy replica succeeded. These
  transport failures are not Power BI permission responses.
- Ignored evidence: `fabric-permission-diagnostic.json` (temporary grant and
  verified rollback), `fabric-final-permissions.json` (user-applied final grant),
  `fabric-final-runtime.txt` (identity/visibility), and
  `api-mi-query-probe.txt` (actual adapter counts and complete policy), all under
  `.local\instruct-iq-deployment`.

### Supported permission mechanisms and least-privilege follow-up

Microsoft's [semantic-model permissions table](https://learn.microsoft.com/power-bi/connect-data/service-datasets-permissions)
explicitly gives Contributor Read + Build + Write and Viewer only Read.
The [PUT dataset-user documentation](https://learn.microsoft.com/rest/api/power-bi/datasets/put-dataset-user-in-group)
explicitly excludes permission updates to service principals (`App`) despite
including `App` in its general principal enum. The equivalent POST restriction
also remains documented. No unsupported app-target dataset grant was attempted.
The current [Fabric Core Items API catalog](https://learn.microsoft.com/rest/api/fabric/core/items)
does not expose a generic item Build-permission grant operation; a guessed
`items/update-item-permissions` documentation URL is not a supported API.

For a future reduction to model-only Read + Build, open the
[exact semantic model](https://app.powerbi.com/groups/d9996489-d2f4-5b55-b1cb-93e94f4f5ddc/datasets/da016571-4589-5d47-8fca-5f408490e85a)
(`instruct-snapshots-b1a7d54affe4`) and select **Manage permissions → Direct
access → identity (…) → Add Build**, or **Add user** if a separate grant is
needed. Keep Reshare and Write unselected. The
[supported UI guide](https://learn.microsoft.com/power-bi/connect-data/service-datasets-manage-access-permissions)
documents these controls for people/groups; direct UAMI Build-only eligibility
has **not** been verified here. An inherited **Workspace Contributor** entry
alone is not proof that a separate Read + Build grant exists. Do not demote the
working Contributor grant until an explicit supported lower-privilege grant is
verified and the actual UAMI adapter probe still succeeds. The checked-in
`query_access.py` intentionally remains Viewer-only and rejects a differing
existing role, so it will not silently undo the user's Contributor choice.

The [Execute Queries reference](https://learn.microsoft.com/rest/api/power-bi/datasets/execute-queries)
requires Read + Build and service-principal tenant eligibility and excludes
RLS/SSO models. This model's published definition is an embedded import model
with no role definitions or SSO source. The general embedding guide recommends
Member/Admin for embedding, but the live Contributor test establishes that
those higher roles are unnecessary for this narrower API use case.

No application code/template change or deployment was necessary. Browser
interactive sign-in and end-to-end authenticated UI plan submission remain
separate, unverified acceptance checks.

## API identity query-access checkpoint — October 15, 2026

- Granted API UAMI principal `0e29e0f2-ca26-588f-a314-f5a7905f046f`
  **only** `Microsoft.Search/searchServices/knowledgeBases/read` through custom
  role `d3214599-ff51-59cf-a0a4-4b290f717e85`, assigned on the original **new**
  Search service. Assignment `f8c027fc-4eab-5d2e-b313-85c91d57d599`.
  Existing Search Index Data Reader supplies retrieval. No Search Service
  Contributor, key access, metadata writes or document writes were added.
  `infra\instruct\search-query-access.bicep` reproduces this independently;
  the foundation template includes the same module. The role definition is
  assignable only within the isolated RG; the actual assignment is service-scoped.
- Source integrity checks remain intact: every retrieval still reads the live
  KB definition and rejects source mapping drift. **Live ACA exec using the
  deployed API's UAMI and installed adapter succeeded: Foundry 6 facts / 6
  connected evidence records**, not a publisher identity or operator token.
- Granted and reread **Viewer** on only workspace
  `d9996489-d2f4-5b55-b1cb-93e94f4f5ddc`, after verifying its deployment ownership
  marker, name, ID and capacity. The role assignment ID equals the principal ID.
  Idempotent reproduction:
  `python agent\provisioning\instruct\query_access.py --config .local\instruct-iq-deployment\environment.json --principal-id 0e29e0f2-ca26-588f-a314-f5a7905f046f --apply`.
  Without `--apply`, this prints the intended target without cloud calls.
- **Exact remaining Fabric blocker:** post-grant dataset-user reread reports the
  UAMI as `principalType=App`, `datasetUserAccessRight=Read`, **not ReadExplore
  (Read + Build)**. The same live API UAMI still receives **404
  PowerBIEntityNotFound** from Execute Queries on model
  `da016571-4589-5d47-8fca-5f408490e85a`. Actual normalized-source policy is
  **blocked**, not complete. This is insufficient to conclude the tenant
  service-principal setting is disabled.
- The documented [POST dataset-user](https://learn.microsoft.com/rest/api/power-bi/datasets/post-dataset-user-in-group)
  and [PUT dataset-user](https://learn.microsoft.com/rest/api/power-bi/datasets/put-dataset-user-in-group)
  APIs explicitly do **not** support service-principal permission grants.
  No undocumented endpoint, unsupported App grant, directory group workaround,
  workspace Contributor escalation, tenant setting change or operator token
  injection was attempted. **Next required operator action:** use the new
  semantic model's supported Manage permissions UI to grant this identity Build
  without Write, if the UI supports it; then rerun the API-UAMI query.
  If unavailable, a supported scoped Build-grant path is still needed.
  Service-principal Execute Queries also requires tenant eligibility and excludes
  RLS/SSO models; no broad setting enablement is authorized.
- Real deployed async credential acquisition exposed a missing **aiohttp**
  dependency (previous transport tests mocked token acquisition). Added it and
  its pinned dependencies; ACR build **cj4** succeeded. Lock regeneration was
  attempted with normal/native TLS and offline resolution but failed on local
  package-host handshake/cache availability. New pins use installed distribution
  metadata; the remote image build successfully resolved and installed the lock.
  Released `instructexample.azurecr.io/instruct-api:20261015-query-access`
  as healthy revision `instruct-example-api--0000002`.
  Added a real async transport-open regression test. **189 full backend tests
  (including 35 adapter tests) and 34 publisher/provisioning tests pass**;
  integrated Bicep compiles.
- Live health **200**, unauthenticated classes **401**, approved SWA CORS
  preflight **200** with exact allow-origin. Authenticated `/classes`/`/plan`
  and browser sign-in remain **unverified**: no suitable dedicated-API delegated
  user token was acquired. No headless scraping/password use.
- Safe exact grants, dataset access reread and ACA query log are retained in
  ignored `.local\instruct-iq-deployment` and referenced by the manifest.
  No old resources, shared Active F4, networking, tenant consent/settings,
  recovery resources, commits or pushes were changed. Ingestion write roles
  remain removed.

## Cloud ingestion checkpoint — October 15, 2026, 13:58 Eastern

- **Published and retrieved on the original selected Search endpoint**, without
  changing networking or creating/switching Search services. Local DNS was
  rechecked once and still returned NXDOMAIN; Azure HTTPS works.
  Recovery Search remains tracked, retained and unused.
- A manual, single-replica ACA job `instruct-search-ingestion` reused the existing
  East US 2 hosting environment and API image. It has a 240-second replica timeout
  and zero automatic retries; it exposes no ingress/admin route. Dedicated UAMI
  `instruct-search-ingestion` received Search Service Contributor and Search Index
  Data Contributor **only on the original new Search service**, plus AcrPull only
  on the new registry. Both Search assignments were subsequently deleted and an
  assignment reread returned `[]`. The API identity never received write roles.
  Tokens came from managed identity into process memory, not arguments or files.
- Actual guarded publication created the dedicated index, knowledge source and
  model-free minimal/extractive KB, then uploaded one complete native snapshot:
  curriculum, two mandatory supports, original 60-minute schedule, superseding
  35-minute amendment and approved resource. Explicit operator UUID approvals,
  native IDs, record hashes and locators were retained. No model was deployed.
- Execution `instruct-search-ingestion-ac3oddh` returned actual Search activity
  `type=searchIndex`, numeric `id=0`, `count=1`, dedicated knowledge source, and
  one reference with `activitySource=0`, `docKey=instruct-snapshot` and dictionary
  `sourceData.snapshot`. Minimal reasoning reported zero reasoning tokens.
  Existing adapter normalization and batch validation **succeeded: 6 facts,
  6 connected native evidence records**, revision
  `c20684689a63869fd9eca1b33b6b89063b2003924931bc0bb58f670ffcba7d25`.
- A fresh operator-delegated Fabric Execute Queries returned **70 facts / 70
  native evidence records**. Combining that live query with the **captured actual
  cloud Search HTTPS response** through the actual normalizer and policy returned
  **complete**. This is cross-environment provider-evidence validation, not an
  authenticated end-to-end API/browser acceptance test or a test-double result.
  Safe synthetic responses and exact job/identity/assignment IDs are retained
  under ignored `.local\instruct-iq-deployment`.
- Live Search GET expands the KB source reference with `enableImageServing:null`
  and `enableFreshness:null`. Publisher and adapter now ignore null reference
  properties while still rejecting non-null drift/additional sources. Added
  regression coverage; **188 full backend tests and 30 provisioning tests pass**.
  ACR build **cj3** succeeded and corrected image
  `instructexample.azurecr.io/instruct-api:20261015-1355` deployed as API
  revision `instruct-example-api--0000001`; `/healthz` returned live **200**.
- **Remaining runtime blockers are explicit:** a separate read-only cloud job
  using the actual API UAMI (not ingestion identity) received **403 on KB
  definition GET**, before retrieval. Its existing Search Index Data Reader
  assignment does not establish metadata-read access. No privileged role was
  added to bypass that. Fabric API MI still has the separately documented
  `404 PowerBIEntityNotFound`; browser sign-in/consent is unverified.
  Consequently the deployed API is **not** claimed to produce complete plans.
  Next work must resolve least-privilege KB metadata discovery/query design and
  separately authorize Fabric model access; no runtime seed fallback was added.
- No old demos, shared F4, tenant settings, recovery cleanup, commits or pushes
  changed. The manual job and UAMI remain tracked for later cleanup; Search write
  privileges are removed.

## Runnable app release — October 15, 2026, 13:48 Eastern

- Published the actual API image with ACR remote build `cj2`:
  `instructexample.azurecr.io/instruct-api:20261015-1345`,
  digest `sha256:21b581b468371d039438c8217fd08cc2bedfe3f03099042b9cda72faa3322c6d`.
  Deployed only the new API into the **existing succeeded East US 2**
  environment; no foundation redeploy, failed Central US retry, resize or
  existing-demo mutation. Exact API ID/revision are retained in the ignored
  manifest. `infra\instruct\runtime.bicep` is an app-only release template that
  consumes existing environment/registry/identity IDs rather than updating them.
- API: https://instruct-example-api.example.invalid
  `/healthz` returned **200**, `{"status":"ok","mode":"live"}`.
  Unauthenticated `/api/instruct/v1/classes` returned **401** with the sanitized
  `instruct.error.v1` envelope, no student/provider details.
- UI: https://ui.example.invalid
  Published the actual Vite build to production using installed SWA CLI 2.0.7.
  The deployment token was retrieved into the publisher process environment,
  removed in `finally`, and never printed or saved to a file.
  HTTPS returned **200**, actual title **Instruct IQ · Teacher Workspace**,
  and JS/CSS plus the lazy-loaded MSAL asset all returned **200**.
  Published MSAL asset contains the new dedicated SPA ID/API scope and
  **memoryStorage** (no browser token persistence).
- Created dedicated single-tenant SPA/API registrations and their service
  principals, with only API `access_as_user` delegated permission (`User` consent
  type), SPA's exact HTTPS redirect and v2 API access tokens. No Graph permission,
  application secret, existing registration modification, tenant-wide consent,
  admin consent grant or tenant setting change. Exact new nonsecret IDs live in
  ignored `application-auth.json` and manifest. **Interactive sign-in/user
  consent and authenticated browser/API acceptance have not been verified.**
  If tenant policy requires admin consent, that remains a blocker, not permission
  to grant it.
- Configured actual model/workspace, original selected Search endpoint,
  dedicated knowledge base/source and explicit synthetic approver. Added a
  time-bounded operator-maintained grant for only the actual signed-in operator
  object ID and `class-science-7a` / `assessment-20261016`; it expires November 15.
  This is **not** a claim of live school membership. Instructional principal
  mapping uses verified Entra `oid` (legacy tokens without it retain `sub`);
  cross-tenant grants still fail. Required provider failures remain failed,
  partial/blocked with no runtime seed fallback.
- Correct exact-origin CORS: approved SWA preflight **200** with its own origin
  and Authorization header allowed; unrelated origin **400**, no allow-origin.
- Read-only new dataset access listing returned only the operator User with
  `ReadWriteReshareExplore`, **not the API managed identity**. No Fabric grants
  or broad service-principal tenant enablement were attempted. A private
  in-container probe then acquired a Power BI token using the **actual API
  managed identity** and called Execute Queries on only the new model:
  **404 `PowerBIEntityNotFound`**. The model is not visible/queryable to that MI;
  operator-delegated success does not transfer to it. This result alone cannot
  distinguish missing model rights from service-principal tenant eligibility.
  No credentials were printed, persisted or forwarded into the hosted app.
- **Important DNS distinction:** a private ACA exec `getent hosts` resolved
  **both** original and recovery Search canonical hosts from Azure, while local
  resolution previously returned NXDOMAIN. A second private exec made standard
  certificate-verified HTTPS requests to `/indexes?api-version=2026-08-01-preview`
  on both canonical hosts: **original 401, recovery 401**, as expected without
  credentials. DNS/TCP/TLS/HTTPS therefore work from the deployed Azure runtime.
  This establishes an environment/resolver-specific difference, not a Search
  firewall issue or proof of a globally unpublished Azure service. It is not
  authenticated retrieval/publication proof. Public access/networking were not changed.
  No Search services, endpoint switch, index/source/KB writes or new roles in
  this app-release batch.
- Validation: **27 backend runtime/auth tests**, **34 adapter tests** and
  **37 frontend tests** passed; frontend build/typecheck, lint and app-only
  Bicep compilation passed. Health is application/process readiness only:
  it does not establish authenticated access or required-provider acceptance.

## Search DNS recovery checkpoint — October 15, 2026, 13:37 Eastern

- The user-supplied exact URL
  `https://instruct-example-search.search.windows.net` is **identical**
  to the attempted URL and ARM's `properties.endpoint`. No typo/configuration
  correction exists. GET with `2025-05-01`, `2026-03-01-preview`, and
  `2026-09-01-preview` returned that endpoint, succeeded/running, Standard 1×1,
  public access Enabled, empty IP rules and no private endpoints.
  None returned a separate `hostName`.
- Local, Cloudflare, Google and the authoritative
  `ns1-05.azure-dns.com` returned NXDOMAIN. Direct HTTPS curl failed name
  resolution, before TLS/authentication. This is a provider DNS publication
  inconsistency, not evidence of missing data-plane roles or a need for
  consent. No IP override, host-file edit or TLS bypass was used.
- A supported same-value PATCH (public access Enabled, one replica/partition)
  returned 200 but did not repair authoritative DNS. A subsequent
  `2026-09-01-preview` PATCH for documented
  `autoGeneratedDomainNameLabelScope=SubscriptionReuse` returned 400:
  **"Updating AutoGeneratedDomainNameLabelScope of an existing search service
  is not allowed."** No service settings changed through that rejected call.
- Before the user's URL follow-up, created **one tracked recovery resource**,
  `instruct-example-search-dns`, in the same isolated RG/Central US,
  Standard 1×1, Entra-only, generated-domain scope SubscriptionReuse.
  PUT returned 201. ARM returned its canonical endpoint:
  `https://instruct-example-search-dns-ctbvhud9gxbbc2dt.sg.search.windows.net`.
  This is an ARM-returned URL, not an inferred hostname. The original service
  remains tracked and retained; both services are potentially billable.
  **Recovery is still Provisioning, not a verified usable replacement.**
  No additional creation attempts, deletes, runtime endpoint switch or roles
  were performed. The selected local configuration still pins the original
  user-supplied endpoint/resource.
- Exact original/new IDs, recovery request, 201 response, identity and latest
  ARM read are in ignored `search-dns-recovery.json` and `manifest.json`.
  New recovery identity: `6c25b0cb-3a1c-5bf9-a189-b0702d384a91`.
- Hardened `agent\provisioning\instruct\publish.py`: validate exact tracked
  isolated ARM endpoint/tenant/ownership/running state before data-plane
  writes; read every coordinate before conditional creation; refuse mismatched
  fields, snapshot source mapping or nonminimal/model-backed KB; refuse partial
  HTTP responses. Synthetic approvals now require an explicit operator object
  UUID in `syntheticApproverId`, not the generic synthetic authority string.
  Approval effective timestamps remain **fictional scenario metadata**, not a
  claim that the real operator approved historical district records.
- Prepared one native document with all **six** raw Foundry facts: curriculum,
  two mandatory supports, original 60-minute schedule and its **35-minute**
  superseding amendment, and approved graph resource. Native IDs, per-record
  hashes, scoped metadata and complete `snapshot` sourceData are preserved.
  **No Search document/index/source/KB is yet claimed published.**
- Re-ran actual operator-delegated Fabric adapter: **70 facts/70 native evidence
  records**, `succeeded`, policy **partial**. Foundry remains unavailable.
  Publisher-to-normalizer-to-policy integration passes with both complete
  projections offline; this is boundary validation, **not live Foundry proof**.
- Final focused validation: **29 publisher/Fabric tests and 34 adapter tests
  passed** (including the actual publisher projection boundary).

Relevant official schemas rechecked:
[management update](https://learn.microsoft.com/rest/api/searchmanagement/services/update?view=rest-searchmanagement-2026-09-01-preview&preserve-view=true),
[creation/generated DNS](https://learn.microsoft.com/rest/api/searchmanagement/services/create-or-update?view=rest-searchmanagement-2026-09-01-preview&preserve-view=true),
[knowledge source](https://learn.microsoft.com/rest/api/searchservice/knowledge-sources/create-or-update?view=rest-searchservice-2026-08-01-preview&preserve-view=true),
[knowledge base](https://learn.microsoft.com/rest/api/searchservice/knowledge-bases/create-or-update?view=rest-searchservice-2026-08-01-preview&preserve-view=true),
[retrieve](https://learn.microsoft.com/rest/api/searchservice/knowledge-retrieval/retrieve?view=rest-searchservice-2026-08-01-preview&preserve-view=true),
and [Search RBAC](https://learn.microsoft.com/azure/search/search-security-rbac).
Minimal intents/extractive retrieval has no required model deployment; none was
deployed. Native adapter protocol and claim semantics were not changed without
live evidence.

New repeatable read-only and combined checks (after canonical DNS resolves):

```powershell
$cfg='.local\instruct-iq-deployment\environment.json'
$endpoint='https://instruct-example-search.search.windows.net'
python agent\provisioning\instruct\publish.py --config $cfg --endpoint $endpoint --inspect-search
$env:PYTHONPATH='services\api'
python agent\provisioning\instruct\publish.py --config $cfg --endpoint $endpoint --verify-model da016571-4589-5d47-8fca-5f408490e85a --verify-connected
```

Do not select the pending recovery until its exact ARM/DNS/HTTPS state is
verified. No new operator role has been granted. If needed once reachable,
Search Service Contributor plus Search Index Data Contributor must be scoped
only to the selected **new** Search; runtime reader binding to a recovery is
also unverified. API Fabric identity eligibility/Read+Build, dedicated SPA/API
auth, and actual runtime caller grants remain unresolved. No frontend/full-app
deployment, model, shared capacity, existing-demo, tenant, consent, commit or
push change occurred.

## Live ingestion checkpoint — October 15, 2026, 13:30 Eastern

- Inspected actual workspace items, empty Lakehouse tables and empty Power BI
  dataset listing before applying. Reverified ownership marker and F4 capacity;
  no capacity changes, old-demo mutations, tenant changes or consent.
- Loaded **24 membership, 3 item, 68 response and 70 InstructSnapshots rows**
  into the new Lakehouse. Four managed Delta tables were reread successfully.
  Snapshot fragments contain one record each and the repeated total count 70.
- Created isolated semantic model **da016571-4589-5d47-8fca-5f408490e85a**,
  `instruct-snapshots-b1a7d54affe4`; refreshed successfully. Live Execute Queries
  returned **70**. The installed native adapter fetched all 70 fragments,
  normalized/validated 70 facts and native evidence records, and the actual
  policy returned **partial**, correctly withholding complete curriculum claims.
- This is a **versioned import projection of the published synthetic snapshot**,
  not Direct Lake or an automatically synchronized Lakehouse semantic model.
  It retains the adapter's exact scope columns, record fragments and an actual
  semantic `Snapshot Record Count` measure. Each content revision gets a new
  marker-owned model; refresh history is inspected before requesting processing.
  API runtime reads the model only, never generator files.
- Native record revisions are content hashes and locators reference the new
  Lakehouse table or dedicated Search document. Synthetic approval metadata is
  explicitly labeled `synthetic-district-authority`, not real district approval.
  Fixture evidence/citations are not copied into connected provenance.
- **Foundry ingestion blocked by Search DNS**, not tenant rights:
  `instruct-example-search.search.windows.net` returned NXDOMAIN through
  local DNS and independent 1.1.1.1/8.8.8.8 resolvers. ARM confirms that exact
  endpoint, succeeded/running, public access Enabled, empty IP rules.
  No index/source/KB existence or data-plane permission claim is possible;
  none was written and no operator RBAC grants were added. Models remain off.
  Do not replace the endpoint with an old demo or guessed regional host.
- Fixed the Lakehouse LRO's actual regional Location response by polling the
  canonical Fabric operation UUID from `x-ms-operation-id`; Fabric tokens are
  never forwarded to the returned regional host. The initial membership load
  succeeded before this polling failure; table state was inspected before
  idempotent Overwrite recovery.
- Added `agent\provisioning\instruct\publish.py` and focused tests. Search
  publishing is prepared but **not live verified**: exact dedicated fields,
  semantic config, one complete document, minimal/extractive KB; reads all
  coordinates before conditional creation and refuses ownership conflicts.

Repeatable commands from repository root:

```powershell
$cfg='.local\instruct-iq-deployment\environment.json'
$endpoint='https://instruct-example-search.search.windows.net'
python agent\provisioning\instruct\publish.py --config $cfg --endpoint $endpoint
# Explicit idempotent synthetic publication (not necessary for read-only check):
python agent\provisioning\instruct\publish.py --config $cfg --endpoint $endpoint --apply fabric
$env:PYTHONPATH='services\api'
python agent\provisioning\instruct\publish.py --config $cfg --endpoint $endpoint --verify-model da016571-4589-5d47-8fca-5f408490e85a
# Only after DNS recovers: inspect data-plane access; scoped operator Search
# Service Contributor/Data Contributor may be needed. No broad grants/consent.
python agent\provisioning\instruct\publish.py --config $cfg --endpoint $endpoint --apply search
python -m unittest discover -s agent\provisioning\instruct -p 'test_*.py' -q
python -m pytest services\api\tests\test_instruct_adapters.py -q
```

Validation: **23 publisher/Fabric tests and 33 adapter tests passed**.
Live operator-delegated Fabric queries are established; API managed identity
eligibility/Read+Build, dedicated SPA/API identity, Search retrieval and full
connected acceptance remain separate. No API/UI publication or commits.

## Live foundation checkpoint — October 15, 2026

**Final verification, 13:03 Eastern:** backing foundation resources are created
and verified. Search is now **succeeded/running** (Standard, 1 replica,
1 partition); Foundry parent/project, Basic registry, monitoring and the
**East US 2** ACA environment are succeeded. The API user-assigned identity
exists and all **four** template-scoped assignments were reread: API `AcrPull`
on the new registry, API `Search Index Data Reader` on the new Search, and
API/Search `Cognitive Services User` on the new Foundry parent. SWA shell
responded **HTTP 200**. App Insights also generated its new failure-anomaly
smart-detector rule inside the dedicated RG; that is not a budget alert.

The initial subscription deployment ended **Failed solely because of the
Central US ACA capacity error**; the separate prepared-module hosting recovery
deployment ended **Succeeded**. Do not erase or misreport that history.
The failed new Central US environment object is retained and explicitly
identified in the manifest; runtime/future parameters point to the succeeded
East US 2 environment, not that failed object. No whole-stack redeployment
or unrelated cleanup was performed just to turn the original deployment green.

Final exact new IDs, states, principal IDs, scoped roles, region choices,
operation history and returned outputs are persisted in ignored
`.local\instruct-iq-deployment\manifest.json` and `resource-ids.json`.
There is **no unresolved foundation permission blocker**. Connected query
permissions/ingestion and app release remain unverified separate prerequisites.
The final ARM reread still returned the shared capacity **F4/Active**.

The user explicitly authorized paid **new** foundation resources and clarified
that the shared capacity was resumed at **F4**, with **no resize authorized**.
No budget or bounded-uptime input is required for this authorized batch. These
instructions supersede the historical preparation gates below.

- Verified the exact parent-created `rg-instruct-iq`, its application
  subscription/tenant and `project=instruct-iq` tag, and that it was empty.
  Added only its authorized `managedBy=instruct-phase-c` ownership tag.
  The template now preserves the parent's `environment=demo` tag.
- ARM **and Fabric REST** independently returned the approved capacity
  **Active, F4**. No resume, resize, capacity role, tenant-setting change, or
  existing workspace/item mutation was performed. New workspace and Lakehouse
  creation succeeded on F4; this does not establish query performance or spare
  headroom for subsequent workloads.
- Initial service regions were **Central US**. Verified registered
  providers and resource-type regional availability, AIServices **S0** with no
  listed SKU restriction, and Search offerings including **Standard**. Current
  Microsoft regional documentation lists Central US agentic retrieval and
  semantic ranker support. Central US then rejected the **new** ACA environment
  with `ManagedEnvironmentCapacityHeavyUsageError` / `AKSCapacityHeavyUsage`.
  This is regional provider capacity, not insufficient permissions.
  Verified East US 2 environment support and completed an isolated recovery
  deployment through the **same prepared apps module**, using
  `environmentLocation=eastus2`; new environment name
  `instruct-example-env-eastus2`. Registry, identity, monitoring, Foundry,
  Search and SWA remain Central US. No existing resource was relocated.
  The canonical parameter now supports this environment-only region choice.
  `instruct-hosting-eastus2` and the new East US 2 environment both returned
  **Succeeded**. The failed Central US environment is recorded separately;
  it is not a runnable hosting environment.
- Verified the caller's existing inherited Owner/role-assignment authority.
  No broad roles or tenant consent were added.
- Final what-if: **12 creates, 1 unchanged, 1 unsupported**. The unsupported
  result is only the deterministic `AcrPull` assignment whose name depends on
  the new identity's principal ID; its scope was inspected as the **new ACR**.
  No capacity or existing-demo resource is in the template. ARM validation
  succeeded. Started actual subscription deployment
  `instruct-iq-foundation-20261015`, not just another plan.
  At the approximately ten-minute checkpoint, Search remained provisioning and
  the initial deployment had not reached a terminal state; do not label the
  entire foundation successful while recovery is pending. The final result is
  recorded above, distinctly from that intermediate checkpoint.
- Fabric created and reread the new `instruct-iq` workspace and `instruct_iq`
  Lakehouse, verifying the persistent deployment-description marker and exact
  approved capacity ID. Exact new IDs and local ownership inputs are retained
  in ignored `.local\instruct-iq-deployment\environment.json`,
  `fabric-created-verified.json` and `manifest.json`. **No seed writes** were
  included in this foundation batch.
- Fixed two live Windows/CLI prerequisite failures in the prepared Fabric
  utility: resolve the `az.cmd` executable, and request a token using the
  explicit subscription after independently verifying its tenant (the CLI
  rejects simultaneous `--subscription` and `--tenant`). No default context
  change or authentication bypass was used.
- Validation: **14 Fabric unit tests** and **3 wrapper checks** passed; Bicep
  compiled and live ARM validation/what-if succeeded.

**Foundation is not connected acceptance.** Model deployments remain off, no
API container image was supplied, and SWA is an unpublished Free shell. Raw
table ingestion, the `InstructSnapshots` projection/new semantic model,
executeQueries Read + Build/identity eligibility, dedicated application auth,
Search index/knowledge source/KB ingestion and operator data-plane roles remain
separate work. Do not reuse old demo services to fill these gaps.

The current official
[retrieve schema](https://learn.microsoft.com/rest/api/searchservice/knowledge-retrieval/retrieve?view=rest-searchservice-2026-08-01-preview&preserve-view=true)
was rechecked: direct Search
`POST /knowledgebases('<name>')/retrieve?api-version=2026-08-01-preview`,
semantic `intents`, `outputMode=extractiveData`, minimal reasoning and source
references are the actual native adapter path, not MCP narrative. Minimal
extractive retrieval does not require blindly selecting a catalog chat model.
Live KB/query readiness is not implied by ARM success.

### Historical preparation record

The remainder records the earlier preparation-only batch. Its dated F16/paused
observations and proposed approval gates are historical, not current capacity
state or a new request for approval.

**Phase C preparation, 2026-10-15.** This preparation batch made no cloud writes.
The parent session separately reported successful, user-authorized creation of
**`rg-instruct-iq` in Central US** in the explicitly selected application
subscription/tenant. No paid resources were created and capacity was not changed.
Keep those actual coordinates in ignored local deployment inputs, not these
examples. RG creation is not stack deployment or query acceptance. Follow the
active implementation plan for subsequent gates.

## Concrete template reuse

- `infra\instruct\resources.bicep` directly invokes the existing, unchanged
  `infra\modules\identity.bicep` and `infra\modules\observability.bicep`, with
  instructional names and tags only. Monitoring retains that module's 90-day
  retention and Log Analytics workspace-key mechanism; no existing workspace or
  key is referenced. Its secure key output feeds only the **new** ACA environment.
- `infra\instruct\apps.bicep` is a reduced adaptation of
  `infra\modules\apps.bicep`: same Container Apps environment/API, Basic ACR,
  managed-identity image pull, `AcrPull` scope, HTTPS ingress on 8000, and Static
  Web Apps architecture/API versions. Direct invocation is unsafe because the old
  interface requires ISV/Web keys, Work certificates and old provider settings.
  Those integrations were removed, not supplied dummy or existing credentials.
  Instructional hosting scales 0–1; SWA Free serves the separately built UI.
- The Search reader role assignment follows `infra\modules\search-role.bicep`
  (same public built-in ID, service scope and deterministic GUID). That module
  targets an existing service, so the instructional assignment instead targets
  the **new** service in the same template.
- New Foundry parent/project/model and Search definitions are necessary because
  legacy `infra\main.bicep` only references existing Search and vault content.
  The subscription entry point creates only `rg-instruct-iq`, then scopes the
  stack to it. Legacy templates, hooks, defaults and deployments are unchanged.
- Fabric seeding retains the existing `load_fabric_lakehouse.py` mechanism:
  OneLake create/append/flush followed by Fabric CSV-to-Delta `Overwrite` load.
  It is reimplemented with standard-library transport so no legacy environment,
  token variables, IDs, retrying ambiguous POSTs, or demo manifests are inherited.

## Prepared resources and serving path

Browser → new SWA HTTPS origin → new ACA FastAPI endpoint. The built SPA must use
the new API URL; the API must validate the dedicated tenant/audience/scope and
enforce its own CORS and instructional authorization. No SWA linked-backend,
cookie proxy, Entra registration, consent or authentication configuration is
implicitly established by these templates.

| Resource | Purpose / smallest prepared configuration |
| --- | --- |
| ACA environment, Basic ACR, conditional API | Existing hosting pattern; 0.5 vCPU/1 GiB, HTTPS 8000, min 0/max 1. API is **not created** with empty image input. First create foundation, then build/push the instructional image to the new registry and supply its digest on a separately authorized update. |
| SWA Free | New static UI host; no repository binding or deployment token fetched. Actual UI publication remains Phase E. |
| User-assigned API identity | Existing identity module, new identity; `AcrPull` on new ACR, Search Index Data Reader on new Search, Cognitive Services User on new Foundry parent. No subscription-wide or capacity roles. |
| Foundry AIServices S0 + project | `allowProjectManagement: true`, Entra-only, new parent/project identities; not a legacy ML hub/project. No hosted-agent capability host, Cosmos DB or agent deployment is assumed. |
| Conditional chat + embedding deployments | `deployModels=false` initially. Exact model/version/SKU/capacity inputs required before enabling. Model deployments belong to the parent account, not the project. |
| Search Standard, 1 replica/1 partition | New agentic-retrieval backing service, Entra-only, system identity and semantic free allowance. Search identity has Cognitive Services User on the new Foundry parent. Single replica is a demo cost choice, not an availability SLA. |
| Log Analytics + App Insights | Existing monitoring module, isolated resources. App/ACA wiring exists, but application trace instrumentation, synthetic-data redaction, sampling and billing alerts still need verification. |
| Fabric workspace + Lakehouse | New objects on the approved existing capacity; no capacity ARM resource, role, resume, assignment migration or resize operation exists in these templates/utilities. |

No Key Vault or Blob storage is created merely by convention. The prepared path
uses managed identity and eventual direct Search-index document push, not a Blob
indexer. Key Vault/certificates belong only to a later approved Work OBO path.
There is no Work/Web provisioning, seed or consent operation here.

## Decisions required before any live operation

1. Populate the **app subscription and tenant** with the parent's now-selected
   coordinates and retain the RG-create evidence. The capacity subscription is
   separate and derived only from its approved ARM ID. A shared tenant is
   currently required by the utility. Do not change CLI defaults.
2. Choose RG metadata, Foundry/model, Search, ACA and SWA regions separately.
   Capacity is Central US F16, observed **Paused/Inactive** in dated discovery;
   that is not a region mandate for other services. Shared-capacity reuse is
   approved, but activation and workload headroom are not. Obtain separate
   activation authorization and measured contention/headroom before execution.
3. Approve costs using current regional prices and a workload estimate:
   Search = 1 search unit × regional hourly rate × hours (rough planning order:
   hundreds USD/month); Basic ACR = daily registry charge + storage/egress
   (typically low single digits USD/month at demo volume); ACA = billable
   vCPU/GiB seconds + requests beyond grants; model tokens and agentic/semantic
   usage add variable charges; monitoring = ingested GB + retention beyond
   included allowance. SWA Free has no base hosting charge within its limits.
   Existing F16 activation can dominate shared spend and add contention; **no
   capacity price, spare CU or resume duration is approved here**. Calculate an
   explicit regional budget, bounded uptime and alerts; these are estimates,
   not a quote or a spending cap.
4. Select chat and embedding versions, SKU, capacity units, residency, safety
   policy and quota. Discovery's gpt-5.5 catalogue entry does **not** prove Search
   planner compatibility; do not select it automatically. GlobalStandard is not
   a residency approval and quota `Count` is not automatically TPM.
5. Deploying identity/RBAC requires resource deployment rights plus role assignment
   permission at the new resource scopes. Provider registration, regional policy,
   name availability, model quota and data-plane permissions remain live gates.
   Search provisioning/ingestion operator needs Search Service Contributor and
   Search Index Data Contributor on **new Search only**; these user grants are
   intentionally not silently added. API has query, not ingestion privileges.
6. Fabric requires workspace-create permission, capacity contributor/admin rights,
   workspace Contributor, Lakehouse write permission and applicable tenant
   service-principal settings. ARM Owner alone does not grant them. Verify
   delegated Workspace.ReadWrite.All / Lakehouse.ReadWrite.All as applicable;
   do not request consent or grant membership during this preparation.
7. Dedicated SPA/API registrations, accepted audiences/scopes and redirect URIs,
   Fabric backend identity access and the actual new Data Agent/ontology/semantic
   model query path must be established independently. No existing demo identity
   is approved for reuse.

## Official schemas and current compatibility

Official references inspected during preparation, not guessed endpoints:

- [Foundry parent 2025-06-01](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-06-01/accounts),
  [project](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-06-01/accounts/projects),
  [model deployments](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-06-01/accounts/deployments).
- [Search ARM 2025-05-01](https://learn.microsoft.com/azure/templates/microsoft.search/2025-05-01/searchservices)
  is separate from Search **data-plane** knowledge-base APIs.
- [Current knowledge-base instructions](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)
  document **2026-04-01 GA minimal/extractive retrieval** and
  **2026-08-01-preview for LLM planning/answer synthesis**. They require Cognitive
  Services User for Search-to-model Entra access. The discovery report recorded
  the legacy repository's `2026-05-01-preview`; that version is **not established
  as a supported current contract** by these docs. Resolve   the exact supported model/region before implementing/activating data-plane
  assets. The now-completed native adapter explicitly requires
  `2026-08-01-preview`; it uses extractive minimal retrieval, not synthesized
  answers. Do not claim ARM provisioning enables knowledge-base retrieval.
- [Agentic retrieval overview](https://learn.microsoft.com/azure/search/agentic-retrieval-overview),
  [ACA 2024-03-01](https://learn.microsoft.com/azure/templates/microsoft.app/2024-03-01/containerapps).
- Fabric [workspace create](https://learn.microsoft.com/rest/api/fabric/core/workspaces/create-workspace)
  supports `capacityId` in the creation body;
  [Lakehouse create](https://learn.microsoft.com/rest/api/fabric/lakehouse/items/create-lakehouse)
  supports 201/202 with LRO;
  [load table](https://learn.microsoft.com/rest/api/fabric/lakehouse/tables/load-table)
  is a **preview API**, uses `Files/...`, CSV header and `Overwrite`.
  [OneLake](https://learn.microsoft.com/fabric/onelake/onelake-access-api) supports
  GUID-based ADLS paths and the Storage audience.

Foundry skill dependency check passed (existing dependencies ready). Project,
model and RBAC references were read; no azd command/provisioning was run. No live
discovery refresh was needed to prepare this stack.

## Local preparation / what-if (PowerShell, repository root)

Copy examples into ignored local storage, not shared environment files:

```powershell
New-Item -ItemType Directory -Force .local\instruct-iq-deployment | Out-Null
Copy-Item infra\instruct\environment.example.json .local\instruct-iq-deployment\environment.json
Copy-Item infra\instruct\main.parameters.example.json .local\instruct-iq-deployment\parameters.json
```

Fill all placeholders. Generate `deploymentId` once with `New-Guid` and retain it
through partial retries; do not copy discovery's candidate app subscription as
if it were already selected. Use only the exact approved Fabric ARM ID/UUID from
ignored discovery evidence. `workspaceId`/`lakehouseId` may be blank for the
**first** creation; pin the returned new IDs before subsequent seeds.

```powershell
az bicep build --file infra\instruct\main.bicep --stdout | Out-Null
python -m unittest discover -s agent\provisioning\instruct -p 'test_*.py' -v
pwsh -NoProfile -File infra\instruct\test-prepare.ps1
.\infra\instruct\prepare.ps1 `
  -ConfigPath .local\instruct-iq-deployment\environment.json `
  -ParametersPath .local\instruct-iq-deployment\parameters.json
```

Default `Validate` compiles and generates an **offline** seed plan: no login,
token acquisition or cloud calls. Filled local model values are still decisions,
not compatibility validation. No installs are needed by the standard-library
utility/tests.

Later, after reviewing target coordinates and authorizing read-only preflight:

```powershell
$cfg = Get-Content .local\instruct-iq-deployment\environment.json -Raw | ConvertFrom-Json
.\infra\instruct\prepare.ps1 `
  -ConfigPath .local\instruct-iq-deployment\environment.json `
  -ParametersPath .local\instruct-iq-deployment\parameters.json -Mode WhatIf `
  -ExistingOwnedGroupId "/subscriptions/$($cfg.appSubscriptionId)/resourceGroups/rg-instruct-iq"
```

The wrapper uses explicit `--subscription`, rejects wrong tenant/RG/placeholder
inputs and non-instructional image syntax, and calls **only what-if**, not create.
An existing group is rejected unless its exact previously created ID is supplied
using `-ExistingOwnedGroupId` and the instructional ownership tags match.
Never adopt another group's name or tag an existing demo to bypass the check.
The parent-created new RG must have `project=instruct-iq` and
`managedBy=instruct-phase-c` ownership tags verified before this path passes;
the preparation did not independently reread or change its tags.
Review every what-if change: only new instructional resources and their scoped
roles are acceptable; capacity resources, old groups or unrelated changes stop
the run. Recheck group noncollision immediately before any later separately
authorized `az deployment sub create`, using the same explicit subscription,
location, template and parameter file. There is deliberately no create wrapper
or automatic activation in this batch.

## Fabric future execution and recovery

```powershell
# Offline: validates explicit targets and seed row/digest plan only.
python agent\provisioning\instruct\fabric.py --config .local\instruct-iq-deployment\environment.json
# FUTURE WRITES: only after separate provisioning + workload authorization.
python agent\provisioning\instruct\fabric.py --config .local\instruct-iq-deployment\environment.json --apply
# FUTURE SEED WRITES: pin returned new IDs first, then:
python agent\provisioning\instruct\fabric.py --config .local\instruct-iq-deployment\environment.json --apply --seed
```

`--apply` validates enabled subscriptions in the selected tenant, requires an
exact Fabric-UUID → approved ARM-ID link and **Active** capacity before any
write. It never resumes capacity, modifies roles or moves an existing workspace.
Resources are recovered by exact instructional name **and** persistent random
deployment-description marker; unowned name collisions, duplicate names, wrong
explicit IDs and changed capacity stop without mutation. Save the original
deployment ID securely as nonsecret operational state. If a create response is
lost, inspect new objects/operations and rerun with the same marker; never invent
a new marker or broadly delete resources.

Seeds contain native tables `instruct_membership`, `instruct_items`,
`instruct_responses` derived from `data\instruct\registry.json`. They include
raw observations and membership/assessment keys, **not** precomputed cohorts,
normalized `test_double` provenance or claimed live citations. Content-addressed
CSV names and Delta `Overwrite` loads make identical reruns non-duplicating.
Loads wait for completion; ambiguous POST/network errors stop rather than replay.
Recover interrupted loads by inspecting the operation before rerun. Do not run
two writers concurrently. Tokens are acquired in memory using explicit tenant/
capacity-subscription context, never printed or saved; redirects and external
operation/pagination URLs are rejected.

**Still required for live acceptance:** verify native table schemas/types,
missing-value semantics, row counts (24 membership rows), SQL/Delta visibility,
item counts, revisions and content digests; build/configure new supported
semantic model with allowlisted access; verify backend
identity queries. This bounded utility does not invent their APIs or claim a
Lakehouse alone is a query-ready Fabric IQ source.

### Current native adapter contract (not the old MCP transport)

`infra\instruct\runtime.env.example` lists the actual current `INSTRUCT_*`
configuration names. No API files were changed in this preparation.

- Required Fabric transport: Power BI
  `POST /v1.0/myorg/datasets/{INSTRUCT_FABRIC_SEMANTIC_MODEL_ID}/executeQueries`,
  token scope `https://analysis.windows.net/powerbi/api/.default`.
  Configure the **new** `INSTRUCT_FABRIC_WORKSPACE_ID` and **new semantic-model
  dataset ID**; a Lakehouse or Data Agent ID is not sufficient.
- The new semantic model must expose **`InstructSnapshots`** with string columns
  **`TenantId`, `ClassId`, `AssessmentId`, `PlanningCutoff`, `Snapshot`**.
  DAX filters the four exact scope/cutoff strings. Each `Snapshot` cell contains
  one `instruct.native-snapshot.v1` fragment with exactly **one** native record,
  an identical repeated manifest and the **total** `recordCount`. Complete Fabric
  kinds are roster/assessment/observation. This utility's three raw Delta tables
  are staging inputs; the snapshot projection and semantic model are explicitly
  **not yet provisioned**.
- Confirm Power BI execute-queries tenant setting, dataset Read + Build access,
  identity eligibility and service-principal settings. Validate restrictions for
  RLS/SSO datasets before relying on the new managed identity. Fabric REST and
  OneLake access alone do not establish executeQueries readiness.
- Current Foundry transport reads the dedicated KB definition and invokes
  **`/knowledgebases('<name>')/retrieve?api-version=2026-08-01-preview`** with
  `outputMode=extractiveData`, minimal reasoning and a semantic intent. It uses
  Search scope `https://search.azure.com/.default`, not a Foundry-agent or MCP
  answer endpoint. Verify permission to read the KB definition as well as
  retrieve; the provisioned Search reader assignment alone has not been
  live-tested for that metadata operation.
- Required Search settings: `INSTRUCT_SEARCH_ENDPOINT`,
  `INSTRUCT_FOUNDRY_KB_NAME`, `INSTRUCT_FOUNDRY_KNOWLEDGE_SOURCE`,
  `INSTRUCT_SEARCH_API_VERSION=2026-08-01-preview`.
  KB definition must contain **only** the mapped source. The index must provide
  filterable string fields **`tenantId`, `classId`, `assessmentId`,
  `planningCutoff`**, returning exactly one complete snapshot document. Retrieval
  must return one search-index reference with its matching source activity,
  count=1 and `sourceData.snapshot`; generated narrative is never factual
  authority. Preserve native revision/locator and complete Foundry kinds:
  curriculum/support/schedule/resource.
- Snapshots must match grant tenant/class, assessment, exact serialized planning
  cutoff and record count. Every Foundry record requires approval ID, approver,
  approved timestamp and approved status. Populate
  `INSTRUCT_APPROVER_IDS_JSON` and `INSTRUCT_CLASS_GRANTS_JSON` only with approved
  new-environment values. Empty examples intentionally fail closed.
- `INSTRUCT_FABRIC_DATA_AGENT_ID`, `INSTRUCT_FABRIC_TOOL_NAME` and
  `INSTRUCT_FABRIC_QUESTION_ARGUMENT` are optional narrative mappings, **not**
  required factual ingestion or substitutes for a semantic model.
  Provider/request timeouts are 20/30 seconds, respectively.

Likewise Search is **backing infrastructure only**: ingestion index/knowledge
source/knowledge base, approval/effective/supersession metadata, supported model
connection, document counts and source-resolving citations are a later explicit
data-plane batch after the API-version decision. No speculative payload or
unverified knowledge-base deployment is shipped here.

## Cleanup: exact resource IDs only, after approval

Retain the actual new ARM IDs from deployment outputs and the two Fabric IDs.
Verify tenant, subscription, instructional tags, marker, workspace capacity and
the exact resources before destructive action. Fabric workspace/items are SaaS
objects and are **not** removed by Azure RG cleanup.

```powershell
# FUTURE DESTRUCTIVE COMMAND SHAPES ONLY; replace with recorded new IDs.
az resource delete --subscription <app-subscription> --ids <exact-new-resource-id>
# Workspace delete removes its new Lakehouse/items: inspect first; never capacity.
az rest --subscription <capacity-subscription> --resource https://api.fabric.microsoft.com `
  --method delete --url https://api.fabric.microsoft.com/v1/workspaces/<recorded-new-workspace-id>
```

For ARM cleanup delete only recorded new resources in dependency order (API,
SWA, ACR/environment, scoped assignments/identities, Search/Foundry child
deployments/project/parent, monitoring). Do not use broad name searches, `azd
down`, shared-capacity deletion, or subscription/group wildcard cleanup. Consider
Foundry soft-delete and retained monitoring costs before recreating names.
No cleanup command has been executed.

## Preparation validation checkpoint

- Mandatory Foundry dependencies: passed, existing tools ready; no installs.
- `az bicep build --file infra\instruct\main.bicep --stdout`: passed without
  warnings, including existing reused modules and isolated hosting adaptation.
- `python -m unittest discover -s agent\provisioning\instruct -p 'test_*.py' -v`:
  **12 passed** (separate subscriptions, wrong targets, ownership, inactive/wrong
  capacity, no-op rerun, partial creation recovery, deterministic seeds,
  overwrite reload, async polling and external-URL rejection).
- PowerShell preparation wrapper parser check: passed.
- `pwsh -NoProfile -File infra\instruct\test-prepare.ps1`: **3 offline checks
  passed** (default no-cloud path, explicit-subscription what-if dispatch,
  wrong-RG rejection before commands). Azure/Python command stubs only; this did
  not perform actual what-if.
- No what-if, paid provisioning, Fabric apply/seed, identity grants, consent,
  activation, application publication, or live integration assertion was made
  by this preparation batch. The parent-reported RG creation is the only
  separately reported cloud change.
