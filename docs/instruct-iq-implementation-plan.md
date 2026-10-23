# Instruct IQ implementation plan

## Active checkpoint — conversational lesson canvas, October 15, 2026

Implemented the first functional **bounded-command** plan/explain/revise
experience. No general language model is connected. A fresh ARM deployment-list
read of the dedicated new Foundry account returned `[]`; no old model was
reused and no model/infrastructure/identity/capacity/permission changes were
made. Plans use the existing live adapters and deterministic policy.

- Side-by-side responsive conversation and persistent editable lesson canvas;
  real submitted messages only, supported prompts, accessible log/status/error
  handling, exact existing Clawpilot variables/theme detection and Segoe UI.
- Authorized catalog selectors remain explicit. History/proposals are scoped
  to the selected class/assessment and clear on scope/access changes. No
  guessed class resolution, fake typing, fake progress or seeded transcript.
- Versioned conversation endpoint preserves v1 plan/draft contracts. Explain
  reads actual item evidence from the authorized generated snapshot without
  another retrieval; differentiation uses actual baseline scaffolds/supports.
- Shorter introduction proposes a 35-minute rebalance; graph scaffolding
  appends to current modelling instructions. Reviewable diffs, Apply/Keep,
  inverse-edit undo, stale-snapshot rejection and review/citation invalidation
  preserve teacher control. Fresh regeneration into an existing canvas also
  requires explicit replacement. Protected evidence/edit/export remain.
- Scope/hash-bound edit replay uses the server snapshot in the existing
  15-minute reference index, never asserted browser evidence. Unsupported
  commands clarify; expired references require explicit regeneration.

Changed application/test files:
`services\api\app\instruct_conversation.py`, `instruct_routes.py`,
`instruct_runtime.py`; `services\api\tests\test_instruct_conversation.py`;
`apps\web\src\instruct\Workspace.tsx`, `client.ts`, `types.ts`,
`conversation.ts`, `workspace.css`, `instruct.test.tsx`.
Contract details and exact accepted commands: `docs\contracts\instruct-v1.md`.

Validation: targeted conversation **15 passed**, runtime **18 passed**;
full `python -m pytest services\api\tests -q` **204 passed**;
`npm test` **40 passed**; frontend `npm run lint` and `npm run build` passed.
No package installation or manifest changes were needed.

Released only the new API image to existing ACA and the existing new SWA using
the ignored manifest/release scripts; no commits, pushes or renames.
ACR build `cj5`, immutable image digest
`sha256:63c9e7cc601d2de99e1e15d2fabbbc621240600de765cd2596766913ecca8cd6`;
API latest/ready revision `instruct-example-api--0000003`, Succeeded.
The initial release-script verification compared SDK serialization, not
normalized configuration, and stopped after the successful image rollout;
follow-up inspection confirmed unchanged authorization scope/revision,
identities and provider coordinates. The previous saved artifact contains a
replacement character in the display-only class title, whereas live ARM
returns the correct em dash. No corrective grant mutation was performed.
Live post-release verification: `/healthz` **200**, anonymous classes and new
conversation endpoint **401**, conversation route present in served OpenAPI.
Installed Edge/Playwright verified the actual deployed conversation and canvas:
two desktop columns, one column at 390px, no horizontal overflow, disabled
pre-authentication commands, empty transcript and **no JavaScript errors**.
Evidence remains in ignored
`.local\instruct-iq-deployment\conversation-browser-verification.json`.

**Remaining limitations:** authenticated deployed interaction still requires
normal operator sign-in and is not claimed verified. General chat, arbitrary
lesson scenarios/commands, conversational class-name resolution and semantic
revalidation of teacher-authored content are not implemented. Work/Web are
optional availability states, not promised integrations. The historical
checkpoints below remain historical.

Status: implementation in progress following user authorization on October 15,
2026. Historical baseline and phase descriptions below precede implementation;
later checkpoints record actual delivered work. No commits or pushes authorized.

**Runnable app increment (October 15, 13:48 Eastern):** actual API image built
in the new ACR and deployed only to the existing succeeded East US 2 ACA
environment; `/healthz` 200 live and instructional unauthenticated route
sanitized 401. Actual SPA published to the new SWA: title/assets 200, exact-origin
CORS verified and other origin rejected. Dedicated single-tenant SPA/API
registrations created with only the custom delegated scope; no broad consent
or existing-app changes. Explicit operator-oid synthetic class grant configured,
MSAL tokens memory-only. Interactive sign-in remains unverified; dataset access
listing lacks API MI; actual in-container MI Execute Queries returns 404
`PowerBIEntityNotFound` (rights versus tenant eligibility not distinguished).
Private ACA DNS resolved both Search hosts, unlike local
NXDOMAIN, and private certificate-verified HTTPS returned 401 on both: Azure
runtime connectivity works, authenticated retrieval remains unverified. Distinguish
resolver environment from networking/auth and preserve
selected endpoint. No Search writes or shared-capacity changes. Validation:
27 backend auth/runtime, 34 adapter, 37 frontend tests; build/lint/Bicep pass.
Exact URLs, digest, scope and remaining readiness limits are in the deployment
checkpoint/ignored manifest. No authenticated/provider acceptance claim.

**Latest bounded continuation (October 15, 13:37 Eastern):** exact user Search
URL equals ARM and all prior attempts; authoritative NXDOMAIN persists despite
same-value reconciliation. Generated-DNS update on that service was rejected as
immutable. One explicitly tracked new generated-DNS Search recovery returned 201
and remains Provisioning; original retained, no endpoint switch or new roles.
No Foundry publication/retrieval claim. Publisher now enforces new-resource ARM
binding and explicit operator UUID approvals, preserves all six native Foundry
facts, and offers read-only inspection/combined live adapter verification.
Live Fabric still yields 70 facts/evidence and partial policy. See the current
infrastructure checkpoint and ignored manifest for exact IDs and outstanding
runtime rights. Native adapter claim semantics are unchanged.
Validation: **29 publisher/Fabric and 34 adapter tests passed**, including
publisher-generated native projections through the installed policy.

## Purpose and execution rules

This document supersedes the execution coordination, assignments, approval
ceremonies, and milestone dependencies in
`docs\instruct-iq-conversion-plan.md`. Keep that document and all prior artifacts
unchanged as historical records. Product requirements remain in force; this is
the active, direct implementation sequence.

Work in small, verifiable increments. Each increment ends with a brief checkpoint:
files changed, validation command and result, remaining blocker, and next step.
Record actual results rather than inferred completion. Do not require role
assignments, separate interface signoffs, or a change of author before fixing
findings. Resolve normal code and contract decisions directly. Escalate only
consequential cost, tenant, permissions, or deployment-target ambiguity.

Independent development tracks may overlap after their shared interfaces are
usable; parallelism is optional, not an execution dependency. Serialize changes
to shared entry points and configuration. Preserve all existing worktree content.
Do not rename the local `pb-iq` folder, bulk-rename incomplete commercial code,
commit, or push without explicit authorization.

## 1. Verified baseline

The following distinguishes files and checks observed during this planning pass
from implementation still to do.

| Area | Evidence and actual state |
| --- | --- |
| Git | `git status --short` reports the project contents as untracked. `git log -1` reports no commits on `main`. `origin` is `https://github.com/adrianwright/instruct-iq.git`; remote visibility/content was not queried. Preserve this worktree; do not treat untracked files as disposable. |
| Contracts | `services\api\app\instruct_contracts.py` contains strict Pydantic request, normalized provider, result, stream, draft, and export models. `docs\contracts\instruct-v1.md` describes their proposed behavior, not installed routes or a policy engine. Reuse and reconcile these artifacts rather than recreate them. |
| Examples | Nine payloads exist under `docs\contracts\examples`: request, provider, complete, partial, blocked, stream, error, draft, and export. The documented `validate_examples` command passed for all nine during this planning pass. These are explicitly development examples, not canonical seed data or live proof. |
| Persistent tests | No `test_instruct_*.py` file was present in `services\api\tests`. Existing commercial/auth/provider tests remain. Example validation does not establish policy, authorization, adapter, or UI correctness. No full test suite was run for this documentation task. |
| Infrastructure discovery | `docs\infrastructure\instruct-iq-capability-discovery.md` records dated read-only checks. Local evidence files exist under `.local\instruct-iq-discovery`; their sensitive/environment-specific contents were not reproduced here. This planning pass did not re-query cloud state. |
| Capacity | The discovery report links the approved capacity's ARM and Fabric identities and records Central US, F16, ARM Paused / Fabric Inactive. Capacity-list access is demonstrated; active capacity, headroom, workspace/item rights, and backend query access are not. |
| New resources | The discovery report explicitly records no cloud writes, no `rg-instruct-iq` creation, and no new deployment. Name availability was a point-in-time observation, not a reservation. Do not label resources provisioned. |
| Regional capability | The report records Central US model catalogue/quota and Search service-count observations. These do not prove available deployment capacity, residency approval, retrieval API support, or runtime permissions. |
| Runtime and UI | `services\api\app\main.py` still imports the commercial orchestrator and exposes commercial routes. `apps\web\src\App.tsx` still imports `ISVDashboard`. Connected instructional planning and the teacher workspace are not delivered. |
| Data and provisioning | The inspected data and provisioning trees contain the existing commercial domain; no instructional seed/provisioning implementation was identified. Existing `infra\main.bicep` is not isolated instructional IaC, according to the discovery report. |

Example validation completed from the repository root:

```powershell
$env:PYTHONPATH='services\api'; $env:PYTHONDONTWRITEBYTECODE='1'; python -c "from app.instruct_contracts import validate_examples; print(validate_examples(r'docs\contracts\examples'))"
```

Only this check was rerun here. Prior discovery results are attributed to the
discovery report and must be refreshed before consequential cloud operations.

## 2. Product and architecture constraints

- **Scenario:** one synthetic district, teacher, and 24-student grade-7 science
  class; graph interpretation and evidence selection. Assessment Friday
  October 16, 2026; lesson Monday October 19; cutoff 07:00 America/New_York.
- **Teacher outcome:** provisional evidence-backed groups and rationale,
  overlapping needs, one shared objective, differentiated scaffolds, approved
  curriculum and authorized supports, a 35-minute lesson including exit ticket,
  answer key, claim-level citations, and unresolved questions.
- **Instructional safety:** missing attempts or missing skill coverage mean
  insufficient evidence, never low mastery. Resolve authority before recency.
  Informal discussion cannot override mandatory curriculum, supports, or schedule.
  The approved 35-minute amendment is a required-source baseline; Work explains
  and changes practical delivery choices within those bounds.
- **Required connection:** real Fabric assessment evidence and real Foundry
  curriculum/requirements evidence determine generated output. Synthetic seed
  files populate new live resources; runtime never reads them as a fallback.
  Replace fixture-derived commercial synthesis, not just its labels/citations.
- **Optional connection:** Work is conditional on request and verified access.
  Web is an explicit optional request for authoritative USGS/EPA enrichment.
  Public queries contain only approved subject/grade/skill context, no student
  identifiers, responses, scores, class identifiers, or support information.
- **Source lifecycle:** use the existing contract's `not_requested`, `disabled`,
  `unavailable`, `failed`, `running`, and `succeeded` literals. In prose,
  “success” means validated retrieval, not proof that all required facts exist.
  Required failure yields bounded partial/blocked output; optional failure
  preserves a grounded core package.
- **Authorization and grounding:** class authorization precedes retrieval,
  progress disclosure, generation, and evidence access. Validate factual support
  at claim level, including native revision, locator, excerpt, and provenance.
  Citation presence alone is not entailment or authorization.
- **Editing:** browser-persisted synthetic drafts scoped by principal, class,
  plan, and schema; preserve generated baseline and ordered teacher edits.
  Editing resets review and invalidates affected generated citation support.
  Markdown and lossless JSON exports retain edits and original provenance.
- **Exclusions:** no real student data, student-facing tutor, automated grading,
  publishing, server draft store, or separate offline demo milestone.
  Test doubles support automated development only.
- **Reuse:** retain inspected generic FastAPI/authentication, REST/SSE transport,
  provider-client and evidence-display mechanisms. Replace commercial domain
  schemas, policy, data, prompts, synthesis, and dashboard.

## 3. Infrastructure boundaries and unresolved inputs

Reuse only the already approved existing `<approved-fabric-capacity>` Fabric capacity, leaving it in
its current resource group. Create a new Fabric workspace and new items.
All new noncapacity Azure resources belong in dedicated `rg-instruct-iq`.
Existing demo workspaces, apps, content, registrations, permissions, certificates,
secrets, and services remain untouched.

Azure CLI login was reported completed in the approved demo tenant tenant with default
subscription `<explicit-subscription>`. A default is not a deployment
selection. Use explicit subscription/tenant/resource coordinates in future
commands; do not switch defaults or silently reuse identities.

Before resource creation, resolve and record:

1. Intended subscription/tenant, RG metadata location, service-region and
   residency matrix. Creating the new RG is already authorized once coordinates
   are unambiguous; that does not authorize paid deployment.
2. Capacity activation/cost implications, measured shared headroom and contention,
   workspace assignment/item rights, and backend identity compatibility.
   Approved reuse is not permission to assume spare or active capacity.
3. The smallest required hosting, Foundry parent/project/model, retrieval/Search,
   storage, identity, secret and monitoring stack. Include Search only when the
   selected retrieval integration requires it; do not copy legacy dependencies.
4. Exact model versions/SKUs, region/quota/capacity, API versions and feature
   compatibility before spend. Search management API availability does not prove
   knowledge-base data-plane compatibility.
5. Dedicated browser/API/provider identities, audience/scope configuration,
   class-membership authority, and least-privilege grants. ARM roles and CLI
   reads do not prove Fabric/Foundry/Search data-plane rights.
6. Optional M365 tenant/content permissions and Web entitlement. Obtain explicit
   authorization before synthetic M365 writes or consequential consent changes.

No new cloud queries are needed to save this plan. Later read-only preparation
must answer a specific unresolved input, not repeat a broad inventory.

## 4. Bounded implementation sequence

### Phase A — Baseline, contracts, and capability alignment

**Prerequisite:** existing files and discovery report above.

| Increment | Concrete files/deliverables | Validation and checkpoint |
| --- | --- | --- |
| A1: Persist contract regression tests | Add `services\api\tests\test_instruct_contracts.py`; reuse `instruct_contracts.py` and the nine examples. Cover strict fields, missing-versus-incorrect observations, references/source integrity, terminal stream parity, draft scope/hash/edit invalidation, and export round-trip. | Targeted pytest and example validator; report tested structural guarantees separately from unimplemented semantic policy. |
| A2: Resolve interface gaps | Update `docs\contracts\instruct-v1.md` to reference this active plan and replace obsolete coordination requirements with technical open decisions. Make only necessary coordinated changes to models/examples/tests. Specify expected skill coverage, deterministic attempt selection, cancellation/deadlines, stable citations, and an authorized plan-reference resolver without server draft storage. | All contract tests pass; one explicit mapping for each required fact and each frontend field; unresolved live capabilities remain labeled unverified. |
| A3: Align capability and identity design | Extend `docs\infrastructure\instruct-iq-capability-discovery.md` with a concise decision/delta section for selected retrieval APIs, approval metadata backing, class grants, evidence resolution, and outstanding deployment inputs. | Trace each interface requirement to existing evidence or a specific future probe. No assumed endpoint, permission, or readiness claim; no provisioning. |

A1 can start immediately. A2/A3 inform each other; unsupported vendor behavior
must not become a fictional contract guarantee. No extra contract approval
ceremony is required.

### Phase B — Independent implementation tracks

**Prerequisite:** usable normalized interfaces from Phase A; cloud uncertainty
must remain explicit rather than block deterministic development.

| Increment | Concrete files/deliverables | Validation and checkpoint |
| --- | --- | --- |
| B1: Canonical synthetic data | Add `data\instruct\` registry, generator, approved documents, membership, skills/items/attempts, support and schedule history, and consistency tests. | Exactly 24 unique students; deterministic generation; complete expected coverage; missing attempts distinct; explicit approvals/effective dates/supersession. Derived counts/groups are not hand-maintained runtime inputs. |
| B2: Policy engine | Add `services\api\app\instruct_policy.py` and focused policy tests. Consume normalized facts to derive groups, rationales, objective/scaffolds, timed package, exit ticket/key, conflicts and issues. | Response-mutation tests change affected membership/rationale; insufficient evidence, overlapping needs, authority precedence, support preservation, timing and factual/proposal distinction tested. No seed imports. |
| B3: Authorization and transport | Add instructional runtime/routes and evidence-reference resolution modules; integrate narrowly in `main.py`, `auth.py`, `config.py` as needed. Use `/api/instruct/v1` classes, plan, stream and authorized evidence routes. | API tests deny cross-class/evidence access before retrieval or SSE headers; sanitized failures, cancellation, exactly one terminal event, interrupted EOF and REST/SSE final parity on one frozen snapshot. Inspect existing global auth test overrides so they cannot mask denial cases. |
| B4: Connected adapters | Add `instruct_sources.py` / `instruct_adapters\` using verified client mechanisms. Map live roster/observations and approved curriculum/support/schedule/resources into contracts. | External-boundary doubles test exact response normalization, approval/provenance checks, timeouts, source lifecycle and required failure behavior. No arbitrary first-tool selection or fixture narrative. Live proof waits for Phase D. |
| B5: Teacher workspace | Add `apps\web\src\instruct\` types, client integration, source/evidence views and components; wire `App.tsx` once coherent. | Vitest for source/error/stream states and draft logic; build/typecheck. Flow: class/assessment → learning needs → lesson → exit ticket → evidence. No production example-loading path. |
| B6: Editing and export | Add instructional draft persistence, constrained editing, canonical hashing, policy rechecks, Markdown/JSON export and frontend tests under `apps\web\src\instruct\`. | Edit/reload/export preserves scope, baseline, changes and provenance; sign-out/class switch clears active content; invalid schema/hash fails safely; edits reset review and suppress stale citation support. |

B1, B2, B5 and infrastructure preparation can overlap. B3/B4 share authorization
and normalized interfaces; serialize shared config edits. B6 depends on B5 and
the finalized draft contract. Each row may be split into smaller checkpoints;
do not accumulate an entire phase without a runnable check.

### Phase C — Prepare isolated provisioning

**Prerequisite:** Phase A capability mapping; B1 supplies ingestion schema.
This phase can overlap Phase B and does not create resources.

1. Add isolated IaC under `infra\instruct\` for the necessary new-resource stack;
   do not run legacy `infra\main.bicep` with renamed parameters.
2. Add explicit-target, idempotent utilities under `agent\provisioning\instruct\`
   for new workspace/items, required identities/connections and ingestion.
   Separate capacity coordinates from application subscription coordinates.
3. Add nonsecret environment templates and deployment instructions describing
   each resource, permissions, region/API/model choices, estimated cost,
   shared-capacity impact and resource-ID-scoped cleanup.
4. Validate templates with the existing tooling and provisioning unit tests;
   test wrong-target rejection, partial-run recovery and no existing-demo
   mutation. Do not install tooling merely to plan this work.

**Checkpoint:** deployment inputs and dry validation are explicit; no cloud
resource is reported created by a template-only check.

### Phase D — Provision, seed, and connect required sources

**Prerequisites:** Phase C, known target/permissions/cost inputs, and authorization
for the consequential operations. B1 ingestion assets must be ready.

Perform separate bounded operations, recording actual new IDs and checks:

1. Recheck target and RG name; create only `rg-instruct-iq` in the selected
   coordinates. Resolve capacity activation/headroom before workload execution.
2. Provision the minimum new Azure stack and dedicated identities. Validate
   model/retrieval compatibility against new resources before expanding spend.
3. Create the new Fabric workspace on the approved capacity and required new
   Lakehouse, semantic/ontology/Data Agent items supported by the selected path.
4. Seed synthetic instructional data and approved documents into actual new
   Fabric/Foundry backing resources. Verify ingestion completion, expected
   record/document counts, revisions, approval metadata, and query readiness.
5. Exercise backend identity queries for both required sources, then browser
   sign-in and API authorization. Record safe results, not credentials.

**Checkpoint:** connected normalized facts and resolving citations exist from
both required services. Provisioning success alone is not connected acceptance.
Failure stops dependent live work with a precise blocker, not a local fallback.

### Phase E — Connected core end-to-end

**Prerequisites:** B2–B6 and Phase D identity/ingestion readiness.

Deploy the instructional API/UI to the new hosting resources. Exercise the
Friday-to-Monday journey from authenticated browser through required retrieval,
policy, citations, editing, reload and both exports.

Add persistent integration/acceptance tests under
`services\api\tests\test_instruct_*.py` and instructional frontend tests.
Use doubles for deterministic automated mutations and bounded live checks for
actual grounding. In a controlled new-resource test record, mutate a relevant
assessment/approved requirement and verify the connected output changes; restore
or document the synthetic revision. Verify required-source outage produces no
seed-based substitute. Record IDs/revisions and safe acceptance results.

**Checkpoint:** deployed core is actually connected; actual evidence, not a
commercial fixture narrative with new citations, determines the package.

### Phase F — Conditional Work and optional Web

**Prerequisites:** normalized optional-source contracts and verified access;
preparation may overlap development. Live checks follow a working core.

- Work: use authorized, isolated synthetic teaching-team artifacts. Demonstrate
  a retrieved practical decision changing delivery while mandatory supports,
  curriculum and 35-minute baseline remain enforced. Preserve conflicting
  discussion as visible context, not overriding authority.
- Web: permit explicit USGS/EPA enrichment requests through verified access;
  test allowlisted public-query construction and authoritative citation mapping.
- Test omitted, disabled, unavailable, failed and successful optional sources;
  none may silently claim verification or erase grounded core output.

**Checkpoint:** report which optional capabilities actually passed live checks.
Unavailable integrations remain explicit limitations, not core blockers or
fabricated demonstrations.

### Phase G — Cleanup, documentation, and deployed acceptance

**Prerequisites:** connected replacements pass their relevant checks.

Update active branding to **Instruct IQ**, README, configuration/deployment/data
docs, environment templates, CI, and `scripts\dev.ps1`. Remove obsolete commercial
runtime/data/UI only after replacement validation; update imports, tests and
`pyproject.toml` discovery together. Preserve historical planning artifacts and
existing demo resources. Do not delete the shared capacity.

Run the existing relevant backend suite, frontend tests/lint/build, then the
deployed acceptance checklist below. Document start/stop, cost, known limitations
and cleanup by recorded new resource IDs. Final demo acceptance requires a
healthy connected deployment, not only local tests or screenshots.

## 5. Validation and completion criteria

Use the smallest applicable check after each increment; escalate to the broader
suite when shared behavior changes. Do not claim commands were run until they
have actual results. Do not restore/install dependencies unless a chosen command
reports missing dependencies or manifests change.

Planned commands from repository root:

```powershell
$env:PYTHONPATH='services\api'; python -m pytest services\api\tests\test_instruct_contracts.py -q
# Later: select the specific instructional modules touched, then shared regressions.
$env:PYTHONPATH='services\api'; python -m pytest services\api\tests -q
npm --prefix apps\web test
npm --prefix apps\web run lint
npm --prefix apps\web run build
```

| Acceptance condition | Required observable result |
| --- | --- |
| Relevant evidence changes | Groups/rationale/scaffolds or delivery change for a documented reason; unrelated facts need not change unaffected groups. |
| Missing submissions/coverage | Insufficient evidence, never fabricated incorrect responses or low-mastery labels. |
| Authority conflicts | Approved curriculum, supports and effective schedule control; conflicting informal guidance and unresolved mandatory conflicts are visible. |
| Required source absent/invalid | Explicit partial/blocked scope; no approved lesson invented and no seed/runtime fallback. |
| Optional capability omitted/fails | Correct distinct source state; no invocation when omitted; grounded core remains available. |
| Factual claim inspection | Supporting facts and authorized source locators/revisions/excerpts resolve and entail the claim; proposals are visibly proposals. |
| Unauthorized class/evidence | No student evidence, counts, source progress or existence disclosure; authorization precedes provider retrieval. |
| REST/SSE comparison | Equivalent final semantic result for the same fact snapshot; one terminal event; interrupted stream never succeeds implicitly. |
| Teacher changes/reload/export | Edits, baseline and provenance survive with correct scope; review resets; stale generated support is not attributed to edited claims. |
| New-resource deployed journey | Healthy UI/API, real sign-in and provider identities, query-ready seeded new resources, and live Fabric/Foundry facts determine output. |
| Resource isolation | Recorded new IDs only; existing demos untouched; only approved Fabric capacity shared; cleanup cannot target shared resources. |

## 6. Exact next first batch

Do this batch next; it is not executed by saving this plan.

1. Rerun the nine-example validator and capture its result.
2. Add `services\api\tests\test_instruct_contracts.py` with example loading plus
   focused negative/reference/source/terminal/draft/export cases. Do not add
   runtime routes, seed readers, or cloud calls.
3. Run only that test module. Fix directly related contract/example defects if
   found, retaining the proposed v1 behavior unless a documented technical
   inconsistency requires a coordinated change.
4. Update `docs\contracts\instruct-v1.md` to point here, remove obsolete execution
   signoff requirements, and list concrete technical gaps from Phase A.
   Append only a concise interface/capability delta to the discovery document
   if this batch establishes one; do not re-run a broad cloud inventory.
5. Report changed files, exact command results, unresolved live prerequisites
   and the next bounded task: expected-skill/attempt-selection specification
   and canonical synthetic data generation.

**First-batch stop:** persistent contract tests pass and technical gaps are
explicit. No provisioning, deployment, permission changes, optional tenant
seeding, commit, push, role approvals, or restart of prior execution machinery.

## 7. Implementation checkpoint — October 15, 2026

User subsequently authorized local implementation. This checkpoint records
actual local work, not cloud or connected readiness.

- **A1 complete (structural scope):** added
  `services\api\tests\test_instruct_contracts.py`: nine examples/round-trips,
  strict requests, missing-versus-incorrect observations, source/reference
  integrity, stream terminal/parity checks, draft hash/scope/edit/review
  invalidation and lossless export. Fixed empty edited groups and allowed
  blocked results to retain independent provider evidence when roster evidence
  is unavailable/ambiguous; no grouping may use an unresolved roster.
- **A2 local interface decisions complete:** updated
  `docs\contracts\instruct-v1.md` to use this active plan, replace historical
  role/signoff dependencies with technical decisions, map required facts and
  frontend fields, specify deadlines/cancellation, stable citation identities
  and a bounded authorized generated-reference index (not server draft storage).
  Added `AssessmentFactV1` to `services\api\app\instruct_contracts.py` for
  expected item/skill coverage and deterministic attempt selection. Existing
  nine examples remain unchanged, explicitly structural examples rather than
  canonical semantic fixtures. Live mapping and resolver implementation remain
  unverified/pending.
- **B1 complete locally:** added `data\instruct\generate.py`, `README.md`,
  canonical `registry.json`, and six `approved-*.md` documents (curriculum,
  resource, two supports, original/amended schedule). One synthetic district,
  teacher and exactly 24 unique learners; deterministic membership, three
  items covering two skills, raw responses, explicit missing submissions,
  absent observations, approval/effective metadata and schedule supersession.
  Added `services\api\tests\test_instruct_data.py`; generation matches every
  persisted artifact and checks normalized provenance/consistency. No derived
  grouping counts are seed inputs. Offline assets are not runtime fallbacks.
- **B2 core complete; optional composition pending:** added
  `services\api\app\instruct_policy.py` and `test_instruct_policy.py`.
  Pure normalized-fact input, stable snapshot ordering, cutoff filtering,
  item-level attempt selection, provisional partition/overlapping needs,
  missing-evidence priority, response-sensitive rationale, required supports,
  approved objective/resources, 35-minute schedule including exit ticket and
  authored answer key, claim references and bounded failures/conflicts.
  Mutations include affected membership/rationale, unchanged-primary rationale,
  later attempts, contradictory attempts, support changes, missing/expired/
  ambiguous roster, conflicting schedule/curriculum, incomplete resource skills,
  future evidence, required/optional outage and later informal guidance.
  Work guidance is surfaced for review rather than automatically applied;
  public enrichment composition and semantic rechecks of teacher edits remain
  pending. Native fact/excerpt entailment and approval authenticity must be
  established by future adapters, not claimed by this pure policy.

Actual validation from repository root:

```powershell
python data\instruct\generate.py --write
$env:PYTHONPATH='services\api'; $env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest services\api\tests\test_instruct_contracts.py services\api\tests\test_instruct_data.py services\api\tests\test_instruct_policy.py services\api\tests\test_isv_contracts.py -q
# 69 passed in 5.74s (includes existing commercial contract regressions).
python -c "from app.instruct_contracts import validate_examples; print(validate_examples(r'docs\contracts\examples'))"
# All nine validated.
```

An intermediate mutation test exposed nondeterministic evidence-array ordering;
the policy now sorts both facts and evidence, and the rerun above passed.
No dependency installs, agents, cloud operations, UI/infrastructure edits,
commits, pushes or workspace rename. Existing untracked work was preserved.
The full suite was not run.

**Next bounded task:** B3 authorization/transport and generated-reference
resolution tests, using the frozen normalized snapshot and deadline decisions;
do not let the existing global authentication test override mask denial cases.
A3/B4 live capability/approval-completeness mapping remains unresolved.

## Live ingestion checkpoint — October 15, 2026, 13:30 Eastern

Implemented explicit synthetic publisher and verified the new Lakehouse's four
Delta tables (24 membership, 3 items, 68 responses, 70 snapshot rows). Created
and refreshed semantic model `da016571-4589-5d47-8fca-5f408490e85a`.
Actual native Execute Queries + adapter normalization returned 70 facts/evidence
records; actual policy returned **partial** with Foundry unavailable, not a
fabricated complete result. This is a versioned import projection, not Direct
Lake synchronization. No runtime seed reads.

Search ARM is running/public but its documented endpoint is **NXDOMAIN** through
three resolvers. No Search ingestion/retrieval or data-plane roles were claimed
or applied. Repeatable guarded Search publisher is implemented, not live
verified. Resume that branch only after DNS resolves, inspect actual objects
before writes, then run native retrieval and normalization. Managed API Fabric
identity and application auth/release remain pending. Models off, capacity
unchanged F4; no old demo, tenant settings, consent, commits, pushes or agents.
See `docs\infrastructure\instruct-iq-deployment.md` for commands, exact live
results, import semantics and blockers. Validation: 23 Fabric/publisher tests
and 33 adapter tests passed.

## 8. Native B3 checkpoint — October 15, 2026

Actual local implementation, with no agents, cloud operations, activation,
consent, commits, pushes, workspace rename, UI or infrastructure changes:

- Added `services\api\app\instruct_auth.py`, `instruct_routes.py`,
  `instruct_runtime.py`, and `instruct_sources.py`; narrowly integrated routes
  and instructional-only error handlers in `main.py`, dedicated settings in
  `config.py`, and corrected the stale contracts module description.
- Installed `/api/instruct/v1/classes`, `/plan`, `/plan/stream` and
  `/classes/{classId}/plans/{planId}/evidence/{refId}`. Instructional bearer
  validation cannot inherit anonymous commercial mock access or the suite's
  global commercial auth override. Validated tenant/subject resolves against
  explicit, time-bounded, revisioned operator class grants; class/assessment
  authorization precedes source work and SSE headers/progress.
- Runtime takes one normalized snapshot, invokes only requested capabilities,
  bounds concurrent work by 30-second overall/20-second provider deadlines,
  cancels/awaits pending tasks and suppresses raw provider exceptions.
  Required outages produce policy-derived blocked/partial output; no runtime
  seed reads. JSON-mode request validation preserves strict offset datetimes
  (initial HTTP tests exposed FastAPI's incompatible strict Python-mode parsing;
  fixed and rerun). REST/SSE finals share the same composition path.
- Evidence index is principal/class/plan/ref-scoped, capped at 128 plans with
  absolute 15-minute expiry; stores original evidence/native revision, checks
  membership revision and current assessment access on resolve. No draft
  storage or browser-edit indexing. Current implementation is process-local;
  native source revision rereads and shared-worker resolution remain pending.
- Added `services\api\tests\test_instruct_runtime.py` (16 tests): actual signed
  JWT denials despite global override, cross-class/assessment denial before
  provider work/stream disclosure, REST/SSE semantic parity on a frozen
  normalized snapshot, mutated assessment/curriculum consumption, claim-ref
  evidence resolution, principal scope, revocation/revision/expiry/eviction,
  required outage, cancellation, timeout, sanitization, optional privacy context,
  invalid requests/config, terminal error and interrupted-transcript rejection.
  Existing contract and policy tests remain unchanged.
- **B4 not complete:** inspected existing Fabric MCP and Search retrieval
  helpers. Fabric uses first-tool/first-argument inference; Search returns
  generated narrative/reference dictionaries, not verified instructional raw
  records/approval metadata. Reusing these outputs as normalized facts would
  fabricate provenance/entailment. Dedicated explicit coordinates are defined;
  missing coordinates return unavailable, and populated coordinates still
  return an explicit unverified-mapping capability gap. No external retrieval
  is attempted yet. Frozen normalized batches are injected only by tests.
  Work/Web integration, native class authority, approval completeness,
  native revision verification and live connected proof are unresolved.
- Updated `docs\contracts\instruct-v1.md` with installed behavior,
  operator-managed grant shape/settings, reference limitations and precise
  connected capability gaps. No deployment readiness claim.

Actual validation from repository root:

```powershell
$env:PYTHONPATH='services\api'; $env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest services\api\tests -q
# 152 passed in 12.99s, including all prior instructional and shared API tests.
python -c "from app.instruct_contracts import validate_examples; print(validate_examples(r'docs\contracts\examples'))"
# All nine validated.
```

Final instructional-only rerun after documentation/module-description updates:

```powershell
python -m pytest services\api\tests\test_instruct_runtime.py services\api\tests\test_instruct_contracts.py services\api\tests\test_instruct_data.py services\api\tests\test_instruct_policy.py -q
# 81 passed in 4.55s.
```

**Next bounded task:** B4/A3 select and verify native Fabric tool/input/result
and Foundry record/approval/provenance retrieval capabilities against explicit
new-resource coordinates, then implement and boundary-test those mappings.
Until that is possible the installed default correctly reports blocked, not
connected success. B3 is locally runnable/tested; live authorization and native
evidence resolver validation are not claimed complete.

## 9. Native B5/B6 frontend checkpoint — October 15, 2026

**Delivered locally:** teacher workspace and constrained browser draft/edit/export
increment. B5 UI is wired to the installed routes; B6 structural editing is
implemented, but semantic policy rechecks remain pending. This does not complete
B4 or establish connected deployment readiness.

Files changed in this increment:

- `apps\web\src\App.tsx`: replaces the commercial entry with the instructional
  workspace; existing commercial components remain untouched and unmounted.
- `apps\web\src\instruct\types.ts`, `client.ts`: actual v1 request/result,
  classes, source, draft and evidence shapes; authenticated POST SSE with
  contiguous request/sequence checks, source lifecycle/final agreement,
  cancellation, terminal error and interrupted-EOF handling. Explicit retry
  only, with no automatic REST fallback or production example/seed loading.
- `apps\web\src\instruct\Workspace.tsx`, `workspace.css`: authorized class and
  assessment selectors, fixed request/scenario explanation (v1 has no question
  field), optional Work/Web requests distinguished from availability, source
  reasons, blocked/partial output, provisional groups/rationale/scaffolds,
  baseline overlaps, lesson segments, exit ticket/answer key, requirements,
  schedule history and resources. Protected evidence always uses the scoped
  route with current authorization; failures/expiry do not fall back to cached
  excerpts. Text rendering, keyboard-visible focus, labeled controls, live
  status/errors and responsive layouts are included.
- `apps\web\src\instruct\draft.ts`: explicit synthetic-data opt-in for local
  storage; principal/class/plan/schema tuple keys, immutable normalized
  baseline and Python-compatible canonical SHA-256, ordered constrained edits,
  exact before/after and claim invalidation, atomic membership+rationale
  changes, roster partition and 35-minute checks. Reload rejects mismatched
  scope/schema/hash/review; edits reset review. Changed claims suppress their
  generated citation support; untouched references are labeled baseline-only
  in edited plans. Review means teacher review only, never publication.
  Markdown and lossless `instruct.export.v1` JSON downloads are available.
- `apps\web\src\authentication.ts`, `auth.tsx`: preserve bearer-token
  acquisition and add sign-out plus identity-change workspace remounts.
  Sign-out/class/assessment changes discard active content and cancel pending
  work; persisted drafts remain separately scoped until explicitly deleted.
  Current class access is rechecked before generation, reload, evidence and
  export. Browser storage is not treated as authorization or encryption.
- `apps\web\index.html`, `src\index.css`: instructional title, mandatory
  Clawpilot detection script before application JavaScript, exact theme tokens,
  Segoe UI/Aptos and component colors exclusively using `var(--cp-*)`.
- `apps\web\src\instruct\instruct.test.tsx`: 25 tests covering complete/partial/
  blocked streams, optional/source states, chunk boundaries, errors,
  cancellation, malformed sequences/scope/transitions, interrupted streams
  without retries, protected evidence scope, canonical Python fixture hash,
  edit/reload/export, invalid draft rejection, storage scope isolation and
  accessible initial workspace markup. Contract fixtures are test-only inputs.

Actual validation from `apps\web`:

```powershell
npm test -- src\instruct\instruct.test.tsx
# 25 passed.
npm run lint
# Passed (oxlint).
npm run build
# Passed (tsc -b and Vite production build).
npm test
# 37 passed across 6 files, including existing frontend regressions.
```

Initial validation found missing local frontend tools; `npm ci --no-audit
--no-fund` restored the existing lockfile dependencies without manifest changes.
An initial canonical fixture test exposed omitted Python default
`effectiveTo=null`; normalization now matches the actual model hash. A build
also caught test-only Node typings and a narrowed MSAL event comparison; both
were corrected before the successful final checks. A bounded production
preview returned HTTP 200 with the instructional title; built HTML inspection
confirmed theme detection precedes the application module. Preview was stopped.

## 10. Connected-adapter and resource-group checkpoint — October 15, 2026

B4 transport and normalization code is implemented in
`services\api\app\instruct_adapters.py`, wired through `instruct_sources.py` and
`config.py`, with `tests\test_instruct_adapters.py`. Raw semantic-model records
and Foundry extractive records drive the policy. Invalid scope, approvals,
provenance, truncation, and narrative-only responses fail closed. These are
implemented boundaries, not proof of populated live resources.

Actual validation reported by the implementation agent:

```powershell
$env:PYTHONPATH='services\api'
python -m pytest services\api\tests\test_instruct_adapters.py -q
# 33 passed.
python -m pytest services\api\tests -q
# 185 passed.
```

Provider requirements are documented in `services\api\README.md`. The Fabric
path uses an explicitly named semantic model and an `InstructSnapshots` ingestion
table; the Foundry path requires an explicitly configured knowledge base/source
and extractive record metadata. Live ingestion, native revisions, identities and
permissions remain unverified. Membership still uses explicit operator grants.
Work/Web remain unavailable rather than pretending to be connected.

The parent session verified the active approved demo tenant subscription, confirmed the target
group did not exist, then executed the previously authorized creation of
`rg-instruct-iq` in Central US using an explicit subscription target.
Azure returned provisioning state `Succeeded`. Only the empty resource group
was created: no paid resources, new Fabric items, capacity activation, tenant
consent changes, deployment, or seed writes occurred.

Root and API READMEs now describe the actual instructional experience and pending
live readiness. Isolated infrastructure-template preparation remains in progress.
Next: validate those templates and ingestion alignment, resolve any consequential
capacity/cost/identity blockers, then provision and verify connected resources.
No commits or pushes.

**Still pending / not claimed:** live provider/authorization proof, real-browser
interaction/accessibility testing (current component coverage is server-rendered
markup; transport and draft behavior are unit-tested), server semantic rechecks
of edited curriculum/support adherence, native revision rereads and shared-worker
evidence resolution. Baseline status/issues/overlaps are explicitly not recomputed
after edits. No free-text question control is invented for the fixed v1 request.
No publishing, cloud changes, agents, API/infra edits, commits or pushes.

**Next bounded task:** B4/A3 native capability mapping and connected evidence
proof remain the prerequisite for usable live generated output. The frontend
correctly renders the current unavailable-provider blocked result meanwhile.

## Live foundation provisioning checkpoint — October 15, 2026

User authorized paid new foundation resources in the exact parent-created
`rg-instruct-iq`; no further generic budget/uptime approval is required.
The shared approved capacity was verified **Active/F4** in both ARM and
Fabric REST and was **not modified**. Its earlier F16/paused discovery state
is historical. Existing demos and tenant settings remain untouched.

Actual execution:

- Populated ignored `.local\instruct-iq-deployment` inputs/manifest with explicit
  selected subscription/tenant, capacity IDs, persistent ownership marker and
  exact new IDs; verified empty parent RG and merged only its ownership tag.
- Reused prepared Bicep and wrapper. Final initial what-if isolated 12 creates,
  unchanged RG and one deferred new-registry `AcrPull` assignment. ARM validation
  succeeded; deployed `instruct-iq-foundation-20261015`.
- New Foundry S0 account/project, Basic ACR, SWA Free shell, user-assigned API
  identity and monitoring were created in Central US. Search Standard 1×1 was
  still provisioning at the ten-minute checkpoint; no query-readiness claim.
- Central US ACA environment failed with provider
  `ManagedEnvironmentCapacityHeavyUsageError` / `AKSCapacityHeavyUsage`.
  Added an environment-only region parameter to the prepared module and chose
  verified East US 2 support. Inspected recovery what-if: a new East US 2
  environment, server-default drift only on this batch's new ACR/SWA, no old
  demo changes. Started `instruct-hosting-eastus2` using the same apps module.
- Created and reread the new marker-owned Fabric workspace `instruct-iq` and
  Lakehouse `instruct_iq` on unchanged F4. IDs pinned locally. No seed writes or
  semantic model creation; no capacity resize needed for these creations.
- Fixed actual Windows `az.cmd` resolution and CLI subscription/tenant argument
  incompatibility in the utility; tenant is independently verified before
  subscription-scoped token acquisition. Bicep compilation, **14 Fabric unit
  tests** and **3 wrapper checks** passed.

See `docs\infrastructure\instruct-iq-deployment.md` and the ignored manifest
for terminal state updates. **Final update at 13:03 Eastern:** Search reached
`succeeded/running`, the East US 2 hosting recovery deployment/environment
succeeded, all four new resource-scoped template roles were verified and the
SWA shell returned HTTP 200. The backing foundation is verified created.
The initial subscription deployment remains Failed only because of its
superseded Central US ACA capacity error; the failed new Central US object is
retained in the manifest and is not the selected environment. Final shared
capacity reread remained F4/Active. Exact resource and principal IDs are saved
locally; no foundation permission blocker remains.

Foundation is distinct from connected acceptance:
models off, no API image, no UI publication; new semantic-model ingestion,
Search KB/index/source, scoped operator data-plane roles, dedicated app auth,
backend query permissions and live acceptance remain subsequent work.
No commits, pushes, rename, tenant consent or broad permissions were performed.
