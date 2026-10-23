# Instruct IQ: bounded delegated collaboration context

## Public configuration and privacy

Deployment identifiers below are synthetic examples, not usable environment
coordinates. Keep exact identities, native source locators and operational
evidence in ignored `.local\` storage. Never use real learner/customer content.

The dedicated `INSTRUCT_WORKIQ_TENANT_ID`, `INSTRUCT_WORKIQ_API_CLIENT_ID` and
`INSTRUCT_WORKIQ_OPERATOR_ID` settings replace hard-coded deployment identities.
The existing `WORK_IQ_CLIENT_ID` must match the dedicated instructional client;
legacy Work IQ applications are not accepted. Missing configuration fails closed.
Provide runtime values through environment variables. Local provisioning may
also load ignored `.local\instruct-iq-deployment\workiq.env`; a working-directory
`.env` and process environment override that file. Do not publish either file.
See `infra\instruct\runtime.env.example` for the provisioning variables, including
the exact approved API resource ID and expected image. The image guard remains
mandatory. Public MCP client and Microsoft service identifiers are unchanged.

## Latest confirmed status — combined live chat succeeded

The user raised the actual `instruct-chat-luna` deployment allocation to
152,000 TPM / 152 RPM; the API still targets that exact deployment.
Subsequent immediate attempts returned genuine upstream HTTP 429. On the
later attempt, chat completed with **HTTP 200 at 21:15:12 UTC** and a
Fabric/Foundry-grounded interpretation. It correctly reported that Work IQ
had failed rather than inventing a Teams comparison. At 21:15:05 UTC, the
adapter recorded `WorkIQProtocolError`; that revision logged the exception
class, not the particular protocol failure.

The answer also claimed no citation references were available. This exposed a
backend bug: `model_facts` removed each fact's `evidenceRefs`, and the retrieval
tool output explicitly supplied an empty reference inventory. The server still
held the references, but the model could not see their IDs. The fix preserves
fact-to-reference IDs and sends only citation ID/source/title, not native
locators, provenance or document bodies. Selected facts still automatically
include their server-owned citations.

Image `20261015-workiq-v4`, build `cja`, digest
`sha256:337960da6d81743001210b2125c9c5d58cead16afa103aaf18f3290df29e24e2`,
is ready as revision `0000008`, with `/healthz` returning 200 and anonymous
class access returning 401. It includes that citation fix and
fixed-reason/numeric-code Work IQ protocol diagnostics; free-form service
messages, prompts, tokens and native content are not logged by those diagnostics.
Focused tests cover both Fabric and Foundry citation visibility, error
preservation and protocol-message redaction.

The user reported Copilot identified `-32001` as an MCP timeout. The deployed
Work IQ request deadline had been 50 seconds (maximum 60), while the overall
chat deadline was 90 seconds (maximum 120). Both are now 120/180 seconds by
default (maximums 180/240) in image `20261015-workiq-v5`, build `cjb`, digest
`sha256:8ad3d4aaf282f6cbcf48c0fae52499f5b9b00988469d12a39403d26f15423820`,
ready revision `0000009`. Health is 200 and anonymous class access remains 401.
This lengthens the caller-side wait; it cannot override a timeout enforced
inside Work IQ or its MCP tool. The observed `-32001` arrived as a Work IQ
JSON-RPC error after about 32 seconds, before the prior caller deadline. A later
user-submitted request on revision `0000009` returned a successful combined
answer using assessment/curriculum information and the Teams planning discussion,
including its unresolved question. The UI explicitly described the Teams result
as a **synthetic collaboration summary**, not a verified native transcript.
This is the first reported successful combined live chat after the timeout and
reference-ID changes; Work IQ citations passed the adapter's approved-source
identity check for this request. It establishes that the flow can succeed; it
does not prove that increasing the client deadline alone resolved the earlier
service-side `-32001` timeout. No additional consent, source scope, model
substitution or M365 writes occurred.

## Earlier live attempts and citation/error handling

The signed-in web request reached Work IQ through the backend's real OBO/A2A
path and received an answer. Sign-in is not the demonstrated failure.
Image `20261015-workiq-v3`, build `cj9`, revision `0000007`, is ready;
`/healthz` returns 200 and anonymous class access returns 401.

The earlier chat route re-awaited an already failed task during cleanup,
overwriting its prepared error response with the generic "Authorization
unavailable" envelope. Cleanup now only cancels and awaits unfinished work,
and chat errors retain their safe original message. Server diagnostics record
the failing stage/status without prompts, tokens or upstream response bodies.

Teams attribution matching now compares the exact verified chat/message
identity, accepting equivalent percent encoding and valid optional owner/tenant
context. Conflicting owner/tenant context, ambiguous query parameters and other
message identities remain unavailable; rendered citations use the server-owned
verified URL.

The subsequent user request on revision `0000007` logged two separate blockers:
at 21:09:16 UTC, Work IQ supplied a structurally valid Teams attribution whose
entity was outside the approved inventory; at 21:09:17 UTC, the next model
request returned **HTTP 429** and chat returned 503. The rejected entity's exact
identity was not logged. Do not assume that it is an equivalent self-chat alias
or authorize it without native verification. The observed 429 proves throttling
for this attempt, not whether the earlier attempt had the same cause or whether
the token or request limit was exceeded. No quota, source scope or permissions
were expanded, and no fallback answer was produced.

**Still unverified:** successful approved-source Work IQ citation acceptance and
a complete signed-in cross-IQ answer.

## Native source and authentication setup

The corrected `workiq-notes-readback` process successfully authenticated the
approved demo operator and verified actual `/me` plus the **three exact
user-created notes** through the direct `48:notes` message routes:
discussion `<native-message-id>`, recap `<native-message-id>`, resource `<native-message-id>`.
Native IDs, sender ownership, class/marker/role labels and service-created
timestamps passed; every source has `contentVerified: true` and a returned
native Teams URL. **No native writes occurred.**

`workiq.json` is now `native_seed_verified`, with
`origin: user_created_teams_self_chat`, three verified sources and no pending
mutation. The runtime manifest uses each verified `nativeWebUrl` as primary
`url`, preserving the original user-provided link as `suppliedUrl`. This is
verified native Graph readback; live Work IQ retrieval is separately evidenced
by the web-request diagnostics above.

The chosen runtime architecture is the **backend agent with delegated WorkIQ
A2A OBO**, not a newly created Foundry agent resource. API per-operator
`WorkIQAgent.Ask` consent and a new certificate in dedicated
`instructexample-kv` are configured. After the user enabled Key Vault
public access, the deployed API identity successfully loaded the certificate
using its scoped Secrets User access to the backing secret. That confirms
certificate access only. Work IQ was subsequently enabled on revision
`0000006`; its actual signed-in web request received a Work IQ answer.
Revision `0000007` preserves that configuration and adds the citation/error
handling fixes described above. Neither native Graph readback nor certificate
loading alone is presented as successful live Work IQ inference.

The dedicated Windows DPAPI cache now supports silent Graph access/refresh
reuse while credentials remain valid. `--silent-only` performs no device
sign-in; no extra device prompt is needed for a valid cached Graph readback.
This does not authenticate the browser or replace the backend caller's token.
Tokens remain unlogged and encrypted at rest; no AMC cache/credential is reused.
Earlier blockers below are historical, not the current native-readback status.

## Current mode: read-only verification of three user-created Teams notes

### Corrected reserved notes alias and dedicated encrypted cache

The later verifier process `workiq-manual-readback` authenticated successfully,
verified `/me`, then received **HTTP 400** for `/chats/48:notes/members`.
That run did not capture a Graph machine error code; it is not labeled a
permission denial or a particular `BadRequest` payload. No new device flow
or live probe was initiated while correcting this.

Read-only AMC prior art
`agent\provisioning\live\seed_m365_workiq.py`, `list_teams_self_chat_messages`
(around line 1645), addresses its `TEAMS_SELF_CHAT_ID = "48:notes"` directly
through `/chats/48:notes/messages`, not `/members`. The verifier's added
membership metadata call was not part of that proven notes route.
The correction applies **only to the exact literal `48:notes` signed-in notes
alias**: after validated tenant/operator/client claims and actual `/me`,
user-supplied URL owner context plus each exact returned message ID, sender,
class/marker/role labels and native timestamp establish the requested
user-bound evidence. It performs exactly **four GETs**: `/me` and the three
supplied messages. The notes `/members` path is no longer even allowlisted.
**All ordinary chat IDs still require the exact single-operator membership
check** before any message read; the general ownership boundary was not removed.
The supplied alias is never generalized to arbitrary chats or identities.

Future verifier invocations use an app-specific **Windows DPAPI encrypted**
MSAL cache at
`%LOCALAPPDATA%\Instruct IQ\msal\<dedicated-client-id>.bin`, never AMC's cache
or a plaintext fallback. MSAL access and refresh records are encrypted; normal
OIDC `offline_access` enables refresh reuse but no Graph workload permission
is added. Only the matching cached operator/tenant account is selected, every
successful cached token rechecks client/tenant/operator/scopes, and actual
`/me` is reread before source verification. Wrong-owner cache entries fail
closed; no cache is cleared or imported. The `--silent-only` flag refuses to
start device authentication when no valid dedicated cached sign-in exists.

The older process at that checkpoint had neither this cache nor a safe module
reload hook; its credential could not retroactively populate the new cache.
The subsequent successful `workiq-notes-readback` invocation uses the corrected
cache-aware verifier described in the latest status above. Tests also include
a real Windows DPAPI roundtrip using only a clearly synthetic placeholder.

Graph failures now include only an allowlisted **observed** native machine
code when present (for example, HTTP 400 plus `BadRequest`), not the response
body or free-form error text. HTTP 401/403 remain terminal. Unknown error codes
are not echoed. This improves future diagnosis without guessing the earlier
400's body or relabeling it as missing consent.

The user chose manual self-chat posting. Automated Graph seed process `285`
was stopped before authentication; no assistant-created event or message is
required by this mode. Parent-supplied candidates are in ignored
`workiq-manual-sources.json`, initially unverified and now **all three verified**
by native readback:

- discussion: `<native-message-id>`
- recap: `<native-message-id>`
- resource: `<native-message-id>`

`agent\provisioning\instruct\workiq_graph_verify.py` uses the existing isolated
public app, requesting **only User.Read and Chat.Read**. It does not modify
registration/consent or call WorkIQ MCP. Its transport rejects all non-GET
operations, history/listing paths and every entity except `/me`, the exact
ordinary-chat membership when applicable and those three exact message paths.
After tenant/client/operator claim verification, the exact notes alias uses
**four bounded Graph GETs**; ordinary chats use five including single-member
ownership verification. No calendar,
mail, broader message history or seeding call occurs.

Every supplied link must identify the same native chat/message and operator
context. Each returned message must have the exact ID, actual operator sender,
synthetic marker, `class-science-7a` label, expected discussion/recap/resource
label and a native timezone-bearing creation timestamp. A missing Graph
`webUrl` is acceptable: the supplied URL is retained as the citation after
exact entity verification. If Graph returns a URL, its chat/message identity
and any owner/tenant context must agree. No URL or timestamp is fabricated.

Only after **all three** reads pass is `workiq.json` written with
`status: native_seed_verified`, `origin: user_created_teams_self_chat`,
`transport: microsoft_graph`, `pending: null`, three verified source identities/
citations/native timestamps and `nativeWritesByAssistant: 0`. Message bodies
are not copied into the runtime or used to fake live retrieval. This verifies
native sources only; backend WorkIQ A2A OBO/certificate and actual cited
retrieval are separate work.

Graph 401/403 failures stop immediately. Other protocol failures retain the
same token in memory for up to 600 seconds with no automatic replay.
`authControl` in `workiq-graph-app.json` may use a fresh request ID and
`resume-manual-verification` to reread only the explicit supplied sources, or
`close` to terminate. Tokens/device credentials are not logged; future access/
refresh cache persistence is DPAPI encrypted as described above.
The focused verifier suite includes the complete
same-process read-only sign-in/control flow.

```powershell
$env:PYTHONPATH='services\api'
python -m pytest -q agent\provisioning\instruct\test_workiq_graph_verify.py -p no:cacheprovider
python -u agent\provisioning\instruct\workiq_graph_verify.py
# Reuse only existing dedicated encrypted credentials, with no device flow:
python -u agent\provisioning\instruct\workiq_graph_verify.py --silent-only
```

## Newly approved isolated Graph seeding architecture

After the MCP denial below, the user explicitly approved a **distinct** AMC-style
architecture: a newly registered operator-only Graph public-client seeder and
separate dedicated backend WorkIQ A2A OBO. The denied MCP schema/create operation
is not retried. No AMC registration, credential, synthetic content or resource is
reused. Backend A2A/certificate provisioning is separate from this seed helper.

`agent\provisioning\instruct\provision_workiq_graph.py` provisioned and verified:

- Name: **Instruct IQ synthetic M365 seeder**
- Tenant: `d9eb725c-64c7-5769-8557-418fda0f460f`
- Client ID: `6005dd0c-5765-528d-b564-97b82d97e24d`
- Application object: `d4490e6e-577f-56af-a8b5-178b10f75f62`
- Service principal: `01aa7041-ba0b-57f9-9ba4-2362d6bd2288`
- Only assigned user: `ba12c12b-23b2-5b85-a3fe-89361cf8a461`;
  `appRoleAssignmentRequired=true`.
- Single tenant; public-client device flow; **no secret or certificate**.
- Exactly delegated Graph **User.Read, Chat.Read, ChatMessage.Send,
  Calendars.ReadWrite**. Scope IDs were resolved from the exact Graph resource.
- Consent is **Principal**, bound to that operator only, **not AllPrincipals**.
  No application permissions, other users/groups, mailbox/files permissions,
  directory-write API permission or tenant-wide consent was added to this app.

Metadata lives in ignored
`.local\instruct-iq-deployment\workiq-graph-app.json`. Provisioning rereads exact
owned objects, assignments and consent, refuses unexpected state and checkpoints
ambiguous creation before mutation. Existing directory-admin authorization is
used only to provision the newly approved registration; its memory-only token
is never passed to the seeder. Native directory HTTP avoids Windows `az.cmd`
interpreting OData ampersands as shell commands.

`agent\provisioning\instruct\workiq_graph_seed.py` uses its own public client's
tenant-specific MSAL device flow; Graph tokens stay in memory, with no disk
cache or token logging. That same process verifies ID-token client/tenant/operator
claims, exactly the four approved scopes, and actual `/me`, resolves the self-chat
from one bounded 25-chat metadata page, and independently checks the exact
returned chat's members. It never assumes `48:notes`, creates a chat, or sends
to colleagues. Only the three labeled sample notes and a private no-attendee
agenda from `data\instruct\work\evidence.json` are written. The event has a
deterministic transaction ID, and every mutation still has a write-ahead pending
checkpoint; ambiguous results are never replayed.

The same process reads every exact returned native identity, verifies operator
authorship/event ownership, real service-created timestamps and returned source
URLs, then rereads all four. No URL, author, meeting occurrence or creation time
is fabricated. The manifest preserves the earlier MCP denial history and uses
`transport: microsoft_graph`, `status: native_seed_verified`, four unique
source keys `discussion/recap/resource/agenda` and `pending: null` **only after
successful complete readback**. This proves native Graph evidence, not WorkIQ
retrieval or deployed backend OBO.

Graph 401/403 responses are terminal. Other recoverable failures retain the
token in process memory for up to 600 seconds, without automatic replay.
An explicit unique `authControl` request in `workiq-graph-app.json` may request
`resume-seed` only when the seed manifest has no pending mutation; `close`
ends the wait. No permission escalation or endpoint/identity switch is attempted.

```powershell
$env:PYTHONPATH='services\api'
python -m pytest -q agent\provisioning\instruct\test_workiq_graph_seed.py -p no:cacheprovider
python agent\provisioning\instruct\provision_workiq_graph.py
python -u agent\provisioning\instruct\workiq_graph_seed.py
```

The focused suite has **9 passing tests**, covering exact per-user provisioning,
idempotency, private event semantics, ownership, token/client/scope validation,
denial, secret redaction and ambiguous-write no replay. Live registration/
assignment/consent verification succeeded. Automated seeding was stopped before
authentication and superseded by the user's three manually posted notes;
their successful readback is documented at the top of this page.

## Historical checkpoints

### Historical MCP attempt: schema access denied (that permission path remains terminal)

The corrected seed-mode process, shell **268**, verified tenant
`d9eb725c-64c7-5769-8557-418fda0f460f` and approved operator
`ba12c12b-23b2-5b85-a3fe-89361cf8a461` through authenticated `/me`.
It resolved the operator-only self-chat, passed the exact ownership check,
and then stopped at **`schema_discussion`** with observed safe error
**`workiq_access_denied`**, `authorizationFailureObserved: true`, exit 1.
This was `get_schema` with `operationType: create` for the verified self-chat
messages collection, **not** a content-creation request.

The local manifest was reread after this attempt: **`pending` is null and
`sources` is empty**. The seeder writes its pending checkpoint before every
native mutation; no such checkpoint was reached. **Zero native messages or
calendar events were created**, and there are no seeded citations/readbacks.
The process stopped on the explicit denial rather than retaining credentials
for retry. No live token/session remains.

**Terminal permission path:** do not retry sign-in/schema requests, use direct
Graph or another endpoint/tool/identity, broaden consent or substitute local
content as native WorkIQ evidence. No further live M365 calls were made after
the denial. Earlier diagnostic uncertainty below is historical; this latest
attempt has a precise observed stage and explicit denial.

**Supported next step:** provide the WorkIQ service/tenant administrator or
provider support this exact operation and stage for investigation of its
authorization/policy. The authenticated public client was
`ba081686-5d24-4bc6-a0d6-d034ecffed87`; the resource metadata advertised scope
`fdcc1f02-fc51-4226-8753-f668596af7f7/WorkIQAgent.Ask`. These identify the tested
integration, **not a proposed new grant**. No HTTP status, request ID, missing
Graph scope or required consent change was reported by the captured diagnostic.
Therefore no specific admin-consent scope/action is asserted or requested.
Do not assume granting `Chat.*` or changing tenant-wide settings fixes this.
The deployed API's separate dedicated-app OBO remains unconfigured/unverified.

**Failed seed-mode attempt, shell `264`:** the same approved tenant/operator and
authenticated `/me` were verified. The process then returned only
`workiq_auth_or_protocol_failed`, exit 1. The manifest has no pending write
checkpoint or sources; the guarded seeder therefore did not reach any native
write. The exact failed stage inside self-chat discovery/seed preflight was
not recorded. No HTTP status, policy denial, schema payload or original
exception was retained, so the actual live protocol cause cannot be recovered
or honestly labeled a 403. Credentials disappeared when that process exited.
No additional device flow was initiated during diagnosis.

Installed `ClientSession.__aexit__` delegates to an AnyIO task group, which can
wrap an inner `WorkContextError` in an exception group. A test using the real
installed SDK reproduces that wrapping. The prior broad outer catch erased
such details; this is a **confirmed diagnostic bug**, not proof that a specific
inner error caused the failed live run. Group-aware safe diagnostics now emit
stage, fixed codes/types, and only actually observed HTTP/RPC status codes.
Native stages identify owner reads, chat resolution, each schema, write and
readback. No exception body, token, device credential or content is logged.

For a future explicitly requested seed-mode run, nonauthorization failures
retain credentials in process memory for at most 600 seconds, without automatic
replay. A trusted operator may add
`"authControl":{"requestId":"unique-nonsecret-id","command":"resume-seed"}`
to ignored `workiq.json` to resume using the same in-memory credential only
when there are **no sources and no pending native write**. A `close` command
ends the wait. Explicit observed authorization failures terminate immediately;
pending/partial native writes require reconciliation and cannot be resumed by
this control. It never changes identity/API, acquires another token, stores
tokens or bypasses a denial. No such memory handle exists for exited `264`.

**2026-10-15, after the user's completed device sign-in:** existing process
`260` reported `demo_profile_verified`, tenant
`d9eb725c-64c7-5769-8557-418fda0f460f`, operator
`ba12c12b-23b2-5b85-a3fe-89361cf8a461`, after an authenticated WorkIQ `/me`
read. It then exited successfully in verification-only mode with zero native
writes. Its memory-only credentials no longer exist; the completed device flow
cannot be resumed and there is no IPC/session handle to continue. No new
authentication was initiated following that completion. A subsequent explicitly
requested sign-in must run the seed operation in that same process, supplying
an exact verified self-chat target. No seeded-source retrieval, source URLs,
deployed API OBO or Copilot-host account change is claimed.

Initial Copilot-host connection (distinct from the isolated helper):
WorkIQ MCP `fetch /me?$select=id,displayName,userPrincipalName` returned HTTP
200 for `operator@example.invalid`, object
`eb34b608-0cb2-55e4-b02d-858d3a1e4667`. This is **not** the approved demo
operator. No demo write was attempted and no native evidence was created.
The connected profile read did not establish its tenant; no tenant was inferred.
No other tenant mailbox, chat list or files were enumerated.

Target tenant is `d9eb725c-64c7-5769-8557-418fda0f460f`; approved operator object
is `ba12c12b-23b2-5b85-a3fe-89361cf8a461`, from the dedicated application-auth
manifest, not an OS/git identity. Required next interaction: authenticate the
WorkIQ host as that demo operator, with host-verified tenant and object claims,
and provide the exact operator-only self-chat ID. Its membership must contain
only that operator, in the target tenant. The operator's actual UPN has not
been established by the approved profile read; do not guess one.

## Native seed contract

### Isolated demo sign-in (not `az login` or host logout)

Live public discovery on 2026-10-15 confirmed
`https://workiq.svc.cloud.microsoft/.well-known/oauth-protected-resource/mcp`
advertises resource `https://workiq.svc.cloud.microsoft/mcp`, scope
`fdcc1f02-fc51-4226-8753-f668596af7f7/WorkIQAgent.Ask`, and the organizations
authorization server. The target tenant's OpenID metadata advertises its
tenant-specific `/oauth2/v2.0/devicecode` and token endpoints.
The skill documents public client `ba081686-5d24-4bc6-a0d6-d034ecffed87`;
device-code initiation must additionally be accepted for this actual
client/tenant/scope before presenting any code. Issuance is not proof of consent
or successful sign-in. No app registration is created or changed.
Actual initiation returned a device credential and the Microsoft verification
URL `https://login.microsoft.com/device`, confirming initiation support for
this public client/tenant/scope. The helper's initial stricter URL allowlist
stopped before displaying a code; it was updated only after inspecting that
nonsecret actual URL. No authentication denial was bypassed.

`agent\provisioning\instruct\workiq_auth.py` discovers/pins that metadata,
initiates MSAL public-client device flow and prints only the real user code,
Microsoft verification URL and nonsecret target identity. Tokens and device
credentials remain in memory; no refresh/access token cache, CLI host logout,
Azure CLI identity change or shared settings change occurs. Use only the
approved approved demo tenant demo operator; stop if administrator approval is requested.
No app-only, employee-account or alternate API fallback is attempted.

```powershell
$env:PYTHONPATH='services\api'
python -u agent\provisioning\instruct\workiq_auth.py
```

Without `--self-chat-id`, this verifies tenant/operator claims and `/me` only,
then exits without seeding. With an exact approved operator-only self-chat ID,
the same in-memory authenticated session proceeds to the bounded seeder.
The helper does **not** authenticate the deployed API's dedicated OBO provider
or change Copilot's existing WorkIQ connection. A successful verification-only
run intentionally persists no token, so a later invocation requires sign-in
again. This distinction is explicit rather than promising reusable auth.

**Actual approved seeding mode (fixes the initial verification-only launch):**

```powershell
$env:PYTHONPATH='services\api'
python -u agent\provisioning\instruct\workiq_auth.py --seed
```

`--seed` retains the authenticated MCP session through all native operations.
After `/me` verification it inspects exactly one documented
`/me/chats?$expand=members` metadata page, without reading other chat messages
or following pagination. It requires exactly one one-on-one target whose sole
member is the approved demo operator in the approved tenant, then independently
verifies the exact target before seeding. No self-chat ID is guessed and no
colleague chat is selected. If that bounded page cannot identify the exact
operator-only chat, it stops without creating a chat or posting content.
After seeding it reruns the idempotent verifier on the same four exact native
IDs, prints source citations and closes the session only after readback.
No new scope, consent grant, alternate identity or API is attempted on denial.
The CLI seed flag and session lifetime are covered by focused tests before
the actual seed-mode sign-in is launched.

`agent\provisioning\instruct\workiq_seed.py` exports async
`seed(DelegatedSession, self_chat_id=..., manifest_path=...)`.
It never acquires CLI tokens or switches identities. A trusted authenticated
MCP host supplies the session binding (not a model/client claim). The seeder
verifies `/me` and exact self-chat membership before any schema/write call.
Three self-chat posts carry fictional discussion, written recap and a
fictional colleague-shared graph resource sample. A private no-attendee event
is scheduled seven days after execution, carrying the proposed agenda.
There is no real colleague attribution, invitation, completed meeting,
transcript, student data or curriculum-approval claim.

Content is in `data\instruct\work\evidence.json`. Scenario date is distinct
from service-created `createdDateTime`. The graph resource is inline text,
**not a claimed uploaded or genuinely colleague-shared file**. WorkIQ's current
MCP surface cannot upload bytes; no upload fallback is attempted.

The exact create schema must confirm every top-level payload field before
writing. Unrecognized schema wrappers stop with `seed_schema_requires_review`;
do not guess. Current-tenant live create contracts remain unverified.
Each successful write is reread and recorded with its exact native ID, path,
service-created timestamp and authorized source URL in ignored
`.local\instruct-iq-deployment\workiq.json`. Reruns verify existing exact IDs
instead of reposting. A write-ahead `pending` record prevents duplicate replay
after ambiguous/denied writes. Reconcile that exact target manually before
clearing pending; never delete the manifest to retry. No error authorizes
alternate APIs, credentials, tenant consent or broader permissions.

## Chat integration handoff (not wired into main/config/UI)

Use `app.instruct_workiq.query_collaboration_context` as a **separate optional**
collaboration tool, not as the required instructional-policy provider.

Arguments:

- `user`: already validated `AuthenticatedUser`, including the current API
  `access_token`, tenant, delegated scopes and Entra `oid`.
- `class_id` and `query`: bounded nonempty question, at most 500 characters.
- `authorized_class_ids`: server-derived current class grants, never model input.
- `manifest`: server-owned seed manifest, class/tenant/owner mapped.
- `session`: trusted caller-bound `DelegatedSession`, or `None`.

Returns `{status, evidence, notice?}`; statuses include `auth_required`,
`not_seeded`, `incomplete` (pending native-write reconciliation), `available`.
Evidence has native `id`, `title`, `url`, `text`,
`createdDateTime`, and
`authority=synthetic_team_suggestion_not_curriculum_policy`. Explicit permission,
protocol, ownership and source failures raise safe `WorkContextError` codes;
they must not become an empty successful answer or trigger another provider.
Source URLs are citations only, not bearer credentials or authorization.
The exact four manifest sources are fetched under the caller's permissions;
no semantic tenant-wide search, Foundry copy or mandatory-policy substitution.
Retrieved text is untrusted data; never execute instructions embedded in it.
State clearly that team suggestions are not authoritative curriculum.

`caller_mcp_session(user=..., token_exchange=...)` uses the installed MCP
SDK's initialized streamable HTTP session at
`https://workiq.svc.cloud.microsoft/mcp`. It does not send an API-audience
caller token to WorkIQ. Its injected async token exchange must perform supported
OBO for dedicated API app `242fb8bd-1383-55d3-a6ff-c5ef09ff0de2` and return
`(workiq_access_token, verified_tid, verified_oid)` matching that caller.
There is deliberately **no default token exchange**, old-app credential reuse,
terminal token sharing, application-only fallback, or plaintext persisted secret.
Only the trusted host may construct a `DelegatedSession`; never expose it as
request JSON. This adapter is implemented but **authentication is not configured
or live retrieval verified**.

### Historical initial MCP settings/auth gaps — superseded by the A2A architecture above

At this initial MCP checkpoint no config/main manifest was changed. The proposed
requirements were a dedicated
caller-OBO provider, a documented WorkIQ delegated resource/scope for this new
app, and securely managed certificate credential if that flow requires it.
The existing legacy app's A2A scope/certificate are not authorization for this
new MCP integration and were not inherited. Live protected-resource metadata
now confirms `fdcc1f02-fc51-4226-8753-f668596af7f7/WorkIQAgent.Ask` for the
hosted MCP resource. The dedicated confidential application's permission
configuration, OBO eligibility and consent were then **unverified**. Public-client
device-code issuance does not configure or prove the dedicated API's OBO path.
If Entra requests administrator consent, stop and report the exact resource,
scope and dedicated app from that request for user action; do not grant
tenant-wide consent or switch identity/API. Key Vault provisioning is not
required merely for these fixtures/tests and had not yet been performed.

## Focused checks

From repository root, with the existing API dependencies:

```powershell
$env:PYTHONPATH='services\api'
python -m pytest -q agent\provisioning\instruct\test_workiq_seed.py services\api\tests\test_instruct_workiq.py -p no:cacheprovider
```

Tests use injectable native transports; they do not establish live connectivity.
Test scratch files are project-local and cleaned up. No commits, deployments,
old demo changes, shared capacity changes, consent or native writes are made
by these tests.

## Current backend OBO configuration and acceptance boundary

The selected backend-agent A2A integration now has dedicated API per-operator
WorkIQ consent and a new securely stored certificate; actual deployed-identity
certificate retrieval from `instructexample-kv` succeeded. Backend image
`workiq-v2` revision `0005` was ready, and the later runtime enablement revision
is awaiting readiness. Only the three verified manual native source URLs are
configured, with original supplied links preserved.

This is **configured / enablement submitted**, not completed live acceptance.
Actual caller-delegated OBO token exchange, WorkIQ A2A inference, exact citation
matching and the signed-in web-chat journey remain **unverified**. Normal
signed-in web-chat validation after readiness is the remaining acceptance step;
no new Graph device sign-in or Foundry agent resource is required for that step.
