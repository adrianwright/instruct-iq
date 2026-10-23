# Instruct IQ conversion plan

Status: C1/N0 bounded contract and capability batch authorized; broad implementation not started.

## Outcome and scope

Deliver a teacher-first, evidence-grounded workflow: from Friday's assessment to
Monday's differentiated lesson. Use one synthetic district, teacher, grade-7
science class of 24 students, and one unit on interpreting graphs and selecting
evidence for scientific claims.

The teacher receives provisional groups with rationale, one shared objective,
differentiated scaffolds, a 35-minute lesson, an exit ticket with answer key,
citations, unresolved questions, and an editable, exportable teaching package.

No real student data, publishing, automated grading, or student-facing tutor is in
scope. This planning update does not execute cloud provisioning, deployment,
commits, or pushes.

## Infrastructure baseline

Build new, isolated Instruct IQ infrastructure rather than repurposing existing
demo resources. Reuse of the existing `<approved-fabric-capacity>` Fabric capacity is approved; discover and
verify its capacity ID, region, permissions, available capacity, and compatibility
before assigning a new workspace. Do not assume its identifiers. Leave that capacity
in its existing resource group. All other Instruct IQ resources must use a new,
dedicated Azure resource group. The user authorizes creating `rg-instruct-iq`
alone during this batch only if discovery clearly establishes the intended
subscription, location, and unambiguous name; otherwise record the exact missing
deployment decision. This exception does not authorize paid resources, deployment,
seeding, consent changes, or changes to existing demo resources.

Create a new Fabric workspace on that capacity, with a new Lakehouse,
instructional data, semantic/ontology items, and Data Agent as required by the
selected integration. Plan new Azure resource groups and application resources:
backend/frontend hosting, a Foundry project and required parent resource, model
deployments, Azure AI Search and knowledge bases, secret storage, managed
identities, and monitoring as needed. Inventory dependencies before provisioning
so only required resources are created.

Configure dedicated application authentication and explicit permissions. Identify
the target M365 tenant and isolate synthetic teaching-team artifacts for Work
integration. Do not assume existing application registrations, certificates,
tenant consent, or demo content can be reused. Optional Web integration requires
verified access and configuration.

The Fabric capacity is the only explicitly approved shared infrastructure. Do not
modify or delete existing demo workspaces, data, applications, or deployed
services. Account for shared-capacity contention and cost.

Infrastructure discovery proceeds alongside contract definition. Subscription,
region, capacity, tenant, quota, permission, and API availability checks are early
critical-path work. There is no separate local/offline demo milestone. Test doubles
remain permitted for automated tests and parallel development, not as substitutes
for live acceptance.

## Implementation ownership

The following responsibility and file boundaries govern execution.

| Owner | Responsibility | File boundary |
| --- | --- | --- |
| API/integration | Lead, contracts, policy, authorization, API, integration | `services\api\app\instruct_*` except Data-owned modules; shared entry points and configuration |
| Data | Canonical synthetic seed data, normalized evidence, connected provider adapters | `data\instruct\**`, `instruct_data.py`, `instruct_sources.py`, `instruct_adapters\**` |
| Platform | Azure/Fabric infrastructure, identity, deployment, resource isolation | `infra\**`, `agent\provisioning\instruct\**`, deployment workflows and environment templates |
| UI | Teacher workspace, editing, persistence, export | `apps\web\src\instruct\**` except QA-owned tests; frontend app integration |
| QA | Independent acceptance tests and milestone review | `services\api\tests\test_instruct_*.py`, instructional frontend tests |

Do not replace the five commercial specialists with five educational specialists.

Platform is the dedicated infrastructure specialist.
Platform owns infrastructure and deployment; Data specifies tables, ontology,
seeding inputs, and provider requirements. Platform and API/integration agree
identity and authorization boundaries. QA reviews isolation and live acceptance.

API/integration integrates changes to `main.py`, shared `schemas.py`, configuration,
`pyproject.toml`, `scripts\dev.ps1`, and README. Platform supplies configuration
requirements through handoffs rather than concurrent edits to those files.
Assign individual documentation, workflow, and cleanup files before parallel edits.

## Defaults

- Use a fixed, explicitly recorded scenario clock, timezone, and effective dates.
  Proposed assessment date: October 16, 2026; lesson date: October 19, 2026;
  planning cutoff: 07:00 America/New_York.
- An approved schedule amendment establishes the baseline 35-minute limit.
  The older 60-minute lab is superseded. Work context explains the change and
  contributes team delivery choices; optional Work availability must not be the
  only way to discover a mandatory scheduling constraint.
- Persist synthetic drafts in browser-local storage scoped by principal, class,
  plan, and schema version. No server draft store in the first milestone.
- Export Markdown for readability and JSON for lossless edits and provenance.
- Use versioned routes under `/api/instruct/v1` and an `instruct.plan.v1`
  response contract.

## Architecture rules

Retain FastAPI, authentication, REST/SSE transport, reusable evidence presentation,
and provider client mechanisms after inspection. Replace commercial schemas,
registry-driven renewal synthesis, dashboard, specialists, fixtures, and prompts.

| Source | Purpose | Invocation |
| --- | --- | --- |
| Fabric IQ | Assessment attempts, item-to-skill relationships, class evidence, proposed groups | Required for assessment-grounded planning |
| Foundry IQ | Approved curriculum, instructional resources, mandatory requirements | Required for approved lesson planning |
| Work IQ | Relevant team decisions and practical delivery context | When requested and available |
| Web IQ | Fresh authoritative instructional enrichment | Explicit optional request |

Route by requested capability, not blanket four-source fan-out. Parallelize
independent selected retrievals. Source states must distinguish not requested,
disabled, unavailable, failed, running, and successful retrieval.

Runtime planning uses connected provider facts. Synthetic seed files populate
the live demo resources; they are not a hidden runtime fallback. Automated tests
exercise the same policy engine with normalized test doubles. Recommendations
must change when retrieved facts change; never attach live citations to decisions
secretly derived from seed files. Show accurate provenance per source.

Validate claim-level support rather than arbitrary citation quotas. Resolve
authority before recency. Informal discussion cannot override mandatory
curriculum or authorized supports. Surface unresolved conflicts and block claims
that lack required evidence. Optional enrichment failure must not invalidate a
grounded core lesson.

Authorize class access before planning and evidence retrieval. Public web queries
must contain no student identifiers, responses, scores, or support information.

## Dependencies and milestones

```text
C1 Contracts and acceptance specification || N0 Infrastructure capability discovery
C1 + N0 -> G0 Contract/capability alignment

G0 -> D1 Canonical synthetic seed data and connected Fabric/Foundry adapters
G0 -> A1 Policy, routing, authorization, API
G0 -> U1 Teacher workspace, edit, persist, export
G0 -> Q1 Independent automated tests and live acceptance specification
G0 -> N1 New-resource IaC, identity, deployment and seeding utilities

N1 + confirmed deployment parameters/authorization -> N2 Provision isolated resources
N2 + D1 -> S1 Seed and verify live Fabric/Foundry evidence
S1 + A1 + U1 + Q1 -> G1 Connected core acceptance

G0 -> W1 Work/Web integration preparation (not a core dependency)
G1 + W1 + verified access/consent -> G2 Collaboration/enrichment acceptance
G2 + documentation/cleanup -> G3 Demo release readiness
```

Contract mocks permit parallel implementation but do not satisfy integration
acceptance. Chunk reviews each gate; authors address findings before the gate
closes.

### C1: Contract freeze

Mikey owns schemas, representative payloads, provider facts, rubric and authority
rules, partial/blocked results, and REST/SSE semantics. Data and Mouth confirm
interfaces; Chunk confirms testability and access boundaries.

Proposed routes:

- `GET /api/instruct/v1/classes`
- `POST /api/instruct/v1/plan`
- `POST /api/instruct/v1/plan/stream`
- Class-authorized evidence retrieval.

Define generated, edited, and reviewed states. Preserve the generated baseline
and subsequent teacher edits. Editing invalidates prior review; review never
means published.

### M1: Connected core demo

Data builds canonical synthetic seed data, deterministic exports, and connected
Fabric/Foundry adapters.
Model membership, students, skills, items, attempts, responses, approved resources,
support requirements, constraints, and temporal team decisions. Generate rather
than hand-maintain derived counts and proposed groups.

Mikey implements transparent instructional rules and conditional retrieval.
Distinguish missing evidence from incorrect answers. Define priority for
overlapping needs and explain provisional group assignments.

Mouth replaces the commercial dashboard with:

`Class and assessment -> Learning needs -> Lesson draft -> Exit ticket -> Evidence`

Expose editable lesson content and group proposals, source inspection, truthful
source activity, reload-safe draft storage, and export. Label teacher edits
without implying that generated citations substantiate newly added assertions.

Platform prepares and provisions the new infrastructure after deployment
parameters and authorization are confirmed, reusing only the verified existing
Fabric capacity. Data and Platform seed the new resources and verify ingestion,
query readiness, permissions, and citations.

Chunk gates the deployed journey against the acceptance matrix below. The core
must run with live Fabric and Foundry evidence, not test doubles or seed-file
fallbacks. Verify both browser sign-in and backend provider identity flows.

### M2: Collaboration and optional enrichment

Prepare Work/Web integrations in parallel with the core when contracts permit.
Activate against verified access and consent after connected-core acceptance.
Explicitly authorize M365 synthetic seeding before it writes tenant artifacts.
Work must demonstrate a grounded team decision changing the plan; Web remains
an optional teacher request with authoritative sources and privacy-safe queries.
Unavailable optional integrations must be reported, not presented as verified.

### M3: Release readiness

Update active branding, documentation, CI, configuration, and demo collateral.
Remove obsolete commercial implementation and fixtures only after replacements
pass their gates. Update dependent test discovery and launcher paths together.
Document resource ownership, estimated cost, shared-capacity impact, and targeted
cleanup instructions. Never delete shared capacity or existing demo resources.

## Acceptance matrix

| Condition | Required result |
| --- | --- |
| Mutate student responses or normalized provider facts | Relevant group and rationale change |
| Remove an assessment submission | Insufficient evidence, not low mastery |
| Change an effective approved planning constraint | Lesson timing or delivery changes |
| Supply conflicting informal guidance | Mandatory requirements remain enforced; conflict is visible |
| Disable, omit, or fail a provider | Truthful distinct state and bounded affected output |
| Fail optional Web enrichment | Approved core lesson remains available |
| Inspect generated factual claims | References resolve and support those claims |
| Request an unauthorized class or evidence document | No student evidence is disclosed |
| Compare REST and SSE | Equivalent final semantic result and clear terminal behavior |
| Edit, reload, and export a draft | Edits and provenance survive; review state resets appropriately |
| Run the deployed core journey | Actual Fabric and Foundry evidence drives the result |
| Required provider is unavailable | Explicit blocked/partial result, no synthetic runtime fallback |
| Verify deployment | New resource IDs, healthy app, sign-in, provider permissions, and query-ready seeded data |
| Run automated tests | Deterministic test doubles; no live credentials needed for unit tests |

Use existing targeted backend/frontend tests, lint, type checking, build, and
seed-data consistency tooling. Supplement these with bounded live acceptance
checks against the isolated deployment. Mocks cannot satisfy the live gate.

## Execution constraints

Data, API, UI, infrastructure, and acceptance have distinct deliverables with
typed handoffs. The main execution risks are shared-file
conflicts, an overloaded lead, and cloud dependencies mistaken for parallel work.

Keep the following execution constraints:

- Begin C1 and N0 together; align contracts with verified provider capabilities
  before the team commits to unsupported APIs or identity assumptions.
- Keep infrastructure troubleshooting separate from API development and
  integration so cloud troubleshooting does not serialize them.
- Each work item records its single accountable owner, inputs, exact writable
  files, prerequisite IDs, acceptance command/evidence, and handoff artifact.
- Use contract payloads and test doubles to unblock UI/API/tests, but label those
  results as development-only until the connected integration gate passes.
- Maintain one integration owner for shared files and explicit interface reviews
  at G0. Avoid a broad repository rename while multiple owners are editing.
- Seed writes wait for infrastructure readiness; live acceptance waits for
  ingestion/query readiness and identity. These are real dependencies.
- QA reviews independently; record decisions and resumable handoffs without
  adding a product/runtime subsystem.

Assign accountable owners before implementation. Ownership assignments are not
a claim of deployed or implemented product behavior.

## First implementation batch

1. Assign implementation owners and record the defaults and file ownership.
2. Run C1 contracts and N0 capability discovery in parallel, then close G0.
3. Run D1, A1, U1, Q1, and N1 within their ownership boundaries. Prepare Work/Web
   interfaces without making optional access a dependency of the core.
4. Confirm deployment parameters and authorization, provision new resources, seed
   synthetic instructional evidence, and verify live query readiness.
5. Integrate the deployed app and close G1 with real Fabric/Foundry evidence.
6. Close Work/Web acceptance where access permits, then finish release cleanup.

Keep the GitHub repository private and empty until a push is explicitly
authorized. Do not rename the active local workspace during this conversion.
