# Instruct v1 — normalized contract

Active execution authority: `docs\instruct-iq-implementation-plan.md`. Earlier
conversion records remain historical, not execution/signoff dependencies.
Strict contracts, persistent regression tests, canonical synthetic ingestion
assets and a deterministic normalized-fact policy are implemented locally.
Instructional routes, operator-configured class authorization and a bounded
generated-reference index are installed locally. Live fact adapters and the UI
remain pending; the connected-only default returns explicit unavailable/blocked
results rather than using seed assets or commercial providers.
No model validation establishes provider readiness or semantic entailment.

## Existing mechanisms and integration boundary

`services/api/app/instruct_contracts.py` uses installed Pydantic 2 and reuses
`app.schemas.Source` (`fabric`, `foundry`, `work`, `web`). It intentionally does
not reuse the commercial `SourceState`: its six distinct states are necessary
to avoid misrepresenting availability. Existing `auth.py` provides bearer
validation, tenant, subject and scopes; existing `main.py` and
`isv_orchestrator.py` use FastAPI, `EventSourceResponse` and `(event, JSON)`
stream tuples. The browser already uses authenticated POST/fetch streams
(`apps/web/src/api/client.ts`), not native EventSource. Retain these mechanisms,
but do not inherit commercial anonymous-mock access, blanket four-source
fan-out, unsafe error details, implicit EOF success, or public evidence access.
No auth/client/transport replacement is proposed.

`fabric_client.py`, `isv_sources.py` and `workiq.py` contain existing client
mechanisms. `RetrievalContextV1` and `ProviderBatchV1` below are **planned
normalized internal interfaces**, NOT supported Fabric/Foundry/M365 vendor API
schemas or an asserted endpoint, tool name, identity flow, or citation capability.
Live discovery must establish those capabilities. Adapters must map verified
provider results into these types, or report a precise capability gap. In
particular, the commercial Fabric client's first-tool inference is not evidence
that the proposed instructional facts can be retrieved.

## Wire conventions and strictness

- All objects forbid unknown fields and use strict Pydantic validation.
  CamelCase names are literal, not aliases. Validate network JSON with
  `model_validate_json`, not Python dictionaries containing date/enum strings;
  strict Python construction requires native types. No string/number/bool
  coercion, untyped `facts` bags, arbitrary paths, or request-supplied principal.
- IDs are opaque, case-sensitive, at most 128 characters and match
  `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`. There are no meaningful ID prefixes at
  runtime. References must resolve within the same authorized result; ref IDs,
  fact IDs, claim IDs, issue IDs, group IDs and segment IDs are unique in their
  respective namespaces. The examples consistently use `class-science-7a`,
  `assessment-20261016`, `student-01` through `student-24`, `skill-graph`,
  `skill-evidence`, and `plan-demo-001`.
  The authenticated principal's `subject` is the existing token's opaque `sub`
  (1–255 characters), not a provider entity ID; preserve it without imposing
  the entity-ID character pattern.
- Dates are ISO dates; instants require a UTC offset. Scenario timezone is
  `America/New_York`, assessment `2026-10-16`, lesson `2026-10-19`,
  cutoff **2026-10-19T07:00:00-04:00** (11:00Z), 35 minutes, 24 students.
  These scenario constants are deliberately not arbitrary scheduling inputs in
  this first contract. Provider facts effective after cutoff cannot be used.
- Schema literals distinguish request (`instruct.request.v1`), result
  (`instruct.plan.v1`), REST/final envelope (`instruct.final.v1`), error
  (`instruct.error.v1`), classes, evidence, retrieval, provider, event, draft,
  and export. Schema evolution is explicit; do not silently load newer drafts.
  JSON Schema is generated from the executable models (2020-12 semantics).
- REST success is **always** `FinalEnvelopeV1`, not a bare plan. The same exact
  envelope is the SSE final event's `payload`. `requestId` is server assigned
  and matches at all nesting levels. Blocked/partial domain results are not
  transport errors. All user-facing messages are safe, not raw provider errors.

## Installed routes and authorization ordering (B3, local validation)

| Method/path | Input | Success |
|---|---|---|
| GET `/api/instruct/v1/classes` | authenticated identity | `ClassesEnvelopeV1` containing only granted classes |
| POST `/api/instruct/v1/plan` | `PlanRequestV1` | `FinalEnvelopeV1` |
| POST `/api/instruct/v1/plan/stream` | identical request | SSE event JSON described below |
| GET `/api/instruct/v1/classes/{classId}/plans/{planId}/evidence/{refId}` | opaque IDs + authenticated identity | `EvidenceEnvelopeV1` |

Evidence path uses `refId`, not a local file path, native provider ID, or
arbitrary URL. `documentId` is an opaque display/document locator and never a
file-system capability. Only Web evidence may have a `publicUrl`; private
documents are accessed through the class-authorized evidence route.

Order: validate bearer identity and API scope; resolve tenant/subject to active
class membership; check assessment belongs to that class; authorize every plan
and evidence reference; then retrieve, emit progress, or disclose content.
`ClassGrantV1` is server-created internal context with checked membership
revision; it is not an authorization token, a browser grant, or proof merely
because it validates. No identity/grant field is accepted in `PlanRequestV1`.
Every adapter consumes a verified grant. A dedicated application/provider identity
does not grant the browser access to all classes. Recheck membership for
evidence access and every new generation; do not treat browser-local drafts as
server authority. A later server plan-ref resolver or signed authorized reference
mechanism is specified below for B3 implementation; no server draft store is authorized.

HTTP failures use `ErrorEnvelopeV1`: 401 `unauthenticated` (+ bearer challenge);
403 `forbidden` for insufficient API scope; 404 `not_found` for a nonexistent or
unauthorized class/assessment/plan/evidence (same generic message); 422
`invalid_request`; 503 `auth_unavailable`; 500 `internal_error`. No student IDs,
counts, evidence, provider diagnostics or source progress accompany denial.
The installed path-scoped exception handlers provide these uniform envelopes;
the existing commercial `detail` error convention remains unchanged.

### Local runtime configuration and capability limits

`INSTRUCT_CLASS_GRANTS_JSON` defaults to `[]`. It is an explicit, operator-managed
authorization authority, not a runtime import of `data\instruct` membership.
Each entry contains `principal` (`tenantId`, opaque `subject`), `classroom`
(`classId`, `title`, `assessmentIds`, `studentCount: 24`), `revision`, `validFrom`
and `validTo` (offset-bearing instants). Malformed/duplicate entries fail with
503; absent/expired grants and unknown assessments fail with generic 404.
Change `revision` whenever access changes. Rechecking uses the current settings
object; environment changes require a process restart. Native membership
integration and multi-worker/shared reference resolution are not implemented.
Instructional authentication always requires bearer validation, even in local
commercial mock mode; it does not inherit the commercial test auth override.

Dedicated coordinates (all empty by default):
`INSTRUCT_FABRIC_WORKSPACE_ID`, `INSTRUCT_FABRIC_DATA_AGENT_ID`,
`INSTRUCT_FABRIC_TOOL_NAME`, `INSTRUCT_FABRIC_QUESTION_ARGUMENT`,
`INSTRUCT_SEARCH_ENDPOINT`, `INSTRUCT_FOUNDRY_KB_NAME`,
`INSTRUCT_SEARCH_API_VERSION`. No commercial coordinate is reused. These
settings do **not** enable retrieval yet: inspection found that the existing
Fabric helper selects the first tool/argument, and the Search helper returns
generated text/reference dictionaries without a verified native record,
approval, revision or excerpt-entailment mapping. The instructional boundary
therefore returns unavailable even when coordinates are populated. No imagined
vendor JSON schema, approval authenticity or live success is asserted.
Work/Web likewise return unavailable when requested and are never invoked when
omitted. External-boundary adapter tests await an actual selected live mapping.

`instruct_runtime.py` consumes only validated normalized source batches. Tests
inject frozen batches and mutate assessment/curriculum facts to verify generated
output changes; this injection is not a production fixture configuration.
It rejects scope/lifecycle mismatches, nonconnected evidence and excerpt hash
mismatches. Policy enforces claim-to-fact-to-reference bindings; native semantic
entailment/authenticity remains an adapter responsibility, not a hash guarantee.

## Conditional retrieval and truthful lifecycle

Fabric assessment and Foundry approved curriculum/requirements are required.
Work is selected only when `includeWork=true`; Web only when `includeWeb=true`.
Selection is not availability. Independent selected retrievals may run in
parallel after authorization. The final has exactly one source batch per enum
value, including omitted sources, and no running states.

| State | Requested | Meaning |
|---|---|---|
| `not_requested` | false | omitted optional capability; no invocation |
| `disabled` | true | administratively/configuration disabled; no invocation |
| `unavailable` | true | selected but unavailable (access/readiness/API/dependency); safe reason |
| `failed` | true | attempted retrieval failed/timed out/invalid normalization; safe reason |
| `running` | true | active retrieval, progress only |
| `succeeded` | true | validated completed retrieval, including an empty search result |

Initial progress is `not_requested`, `disabled`, `unavailable` or `running`.
`running -> succeeded|failed|unavailable`; all other states are terminal for
this request. No retries/reset events within one transcript; a retry is a new
request. Non-success batches expose no evidence or facts; a succeeded empty
batch is **not** proof that required facts exist. Missing required facts become
issues, not fabricated evidence. Source reason is a safe explanation, never
credentials, raw requests, student content, or stack traces.

`ProviderBatchV1` binds class, assessment, source, requested flag, state,
duration, evidence and discriminated typed facts. Normalized capability mapping:
Fabric/assessment, Foundry/curriculum, Work/team_context, Web/public_enrichment.
Every evidence has a stable `refId`, authorized class, source-native ID/revision,
retrieval instant, content SHA-256, title, exact locator, supporting excerpt and
adapter identifier. `adapter` is a truthful implementation/version name, not
an assertion that a vendor API has a particular shape. Private citation lookup
is authorization-preserving. Render excerpts as text, not trusted HTML.

Fact union:

| Kind | Owning source | Authority | Required content |
|---|---|---|---|
| roster | Fabric | assessment_record | 24 distinct synthetic learner IDs |
| assessment | Fabric | assessment_record | assessment ID, graph/evidence skill roles, expected item-to-skill map, attempt-selection rule |
| observation | Fabric | assessment_record | assessment/student/skill/item/attempt + outcome |
| curriculum | Foundry | approved_curriculum | approval, objective, skill IDs |
| support | Foundry | mandatory_support | approval, affected students, requirement |
| schedule | Foundry | approved_schedule | approval, lesson date, minutes, superseded fact IDs |
| resource | Foundry | approved_resource | approval, skills, usage |
| team_decision | Work | team_decision | decision |
| enrichment | Web | public_reference | recommendation |

All facts have effective intervals and evidence refs. Adapters must verify
approval metadata before assigning approved/mandatory authority. Approval is
not inferred from source brand, title, recency or a model assertion. Required
support and schedule truth must be available through the required Foundry
interface, even if Work contains the discussion explaining the amendment.
Different live backing arrangements remain unverified, not fabricated.

`outcome` is `correct`, `incorrect`, or `missing_submission`.
Missing submission requires `attemptId=null`; observed correct/incorrect
requires a real normalized attempt ID. Do not encode missing work as zero,
incorrect, low mastery or a failed skill. No observations for an expected
learner/skill also means **insufficient evidence**, not a fabricated submission.
`AssessmentFactV1` defines expected coverage independently of received attempts.
Both distinct skill roles must occur in its item map. Every expected item must
have a selected nonmissing observation before a learner can enter extension.
Select per student/item by maximum `(effectiveFrom, attemptId or "")` within the
cutoff, using case-sensitive lexical attempt ID as the deterministic tie-break.
Contradictory outcomes with the same selection key block grouping. Unknown
items or mismatched skill mappings block grouping, not silently count as success.
A correct item cannot fill a different missing item, even within the same skill.
All selected items must be correct for extension; any observed incorrect item
records that skill's need, including when missing evidence has primary priority.
The rule is a conservative instructional policy, not an automated grade.
Exactly one roster and coverage manifest are required by the policy. Legacy
development examples intentionally omit the new manifest and remain structural
examples only; they are not semantic policy acceptance fixtures.

Public queries must be constructed solely from approved subject/grade/skill
content. Never include a learner ID/name, response, score, class identifier,
support requirement or disability information, even under a pseudonym.
`publicQuery` exists only for Web. Its presence validator is not a privacy
filter; B4 must enforce an allowlisted projection before calling an existing
provider client. Do not send the whole internal context to public Web.

## Normative policy and claim grounding

`instruct_policy.build_plan` implements deterministic grouping and a constrained
35-minute package from normalized facts without I/O or seed imports. Pydantic
checks structural and reference integrity, not semantic entailment. Adapters
must verify approval metadata and fact/excerpt fidelity; live acceptance remains
pending. Ambiguous curricula/schedules block the lesson but preserve usable
groups. Supports are additive and retained verbatim in applicable scaffolds and
delivery instructions. Team decisions are conservatively surfaced with their
references for teacher review, never automatically applied over requirements;
automatic safe extraction of practical Work delivery changes is still pending.
Public enrichment does not alter the core package in this increment.

1. **Authority before recency.** Mandatory authorized supports are non-negotiable
   access requirements; approved curriculum governs objective/content; the
   effective approved schedule governs timing. These are domain-specific
   authorities, not competing interchangeable ranks. Approved instructional
   resources come next; team decisions may choose delivery within those bounds;
   public enrichment never overrides them. Later chat cannot override any
   mandatory support, curriculum or schedule. A newer same-authority fact wins
   only with verified approval, matching scope, valid effective interval and
   an explicit supersession chain. Ambiguous/equally authoritative incompatible
   requirements are visible conflicts: block only affected claims/sections.
2. **Schedule baseline.** The approved 35-minute amendment supersedes the old
   60-minute lab. Preserve historical schedule evidence when useful, but do not
   apply expired facts. A lesson's segments total 35 including the exit ticket.
   A changed effective authorized schedule must change timing/delivery; a new
   scenario/schema decision is needed if the fixed 35-minute scenario itself
   is changed. Optional Work must never be the sole scheduling authority.
3. **Provisional grouping.** Preserve mandatory supports across every group;
   they are not low-mastery labels. Evaluate the approved graph and
   evidence-selection skills using the deterministically selected assessment
   observations. Priority for one primary group per learner:
   (a) missing/insufficient required-skill evidence;
   (b) graph interpretation gap;
   (c) evidence-selection gap;
   (d) extension when both required skills have sufficient successful evidence.
   Retain secondary observed needs in `overlappingNeeds`. Graph-before-evidence
   is a pedagogical provisional choice: graph interpretation is prerequisite
   to using graph evidence. A correct answer in one skill cannot fill missing
   evidence in another. Omit empty groups. Primary groups partition all 24
   roster members once; none is a final ability label or an automated grade.
4. **Fact sensitivity.** Rationale names the actual observed/absent evidence
   and priority used, with supporting fact IDs. Mutating a selected relevant
   response, missing submission, support, or effective constraint must recompute
   affected membership/scaffold/lesson **and rationale**. If membership remains
   under the same priority, rationale still changes to explain changed facts.
   An unrelated fact mutation need not reorder unaffected groups. No
   hard-coded derived counts or synthetic-seed decisions with live citations.
5. **Claim-level support.** Every generated factual claim has
   `basis=supported_fact`, fact IDs and resolving evidence refs. A claim's
   references exactly match the union from its supporting facts; a ref's excerpt,
   revision and locator must actually entail the assertion. Claims of absence
   require authorized roster/coverage evidence, not a failed query. IDs/quotas
   alone do not prove support. `instructional_proposal` labels a recommendation
   or author-created prompt/answer key, never a disguised student fact or a
   claim of approved-resource authority. Proposals may cite constraints but
   must remain visibly proposals. Cite generated factual objective, rationale
   and requirements at their claims, not only in an appendix.
6. **Conflicts and unsupported claims.** Retain contradictory fact/evidence
   refs in an `authority_conflict` issue; explain which authority controls.
   Resolve same-authority supersession explicitly. A claim without required
   evidence is omitted/blocked with `unsupported_claim` or
   `missing_required_fact`, affected output, safe explanation, and actionable
   resolution. A question in `unresolvedQuestions` never substitutes for a
   blocking issue. Optional failure cannot erase a grounded core lesson.

### Complete, partial, blocked

- `complete`: all requested output is available; both required sources succeeded,
  curriculum/schedule/supports are resolved, grounded groups and full approved
  package exist, no blocking issues. Nonblocking insufficient learner evidence
  or visibly resolved informal conflicts may still be present.
- `partial`: usable output remains and issues explicitly bound what is missing.
  For example Fabric groups may survive Foundry failure, but `package=null`;
  no approved lesson is fabricated. Alternatively requested optional Web failure
  retains the full grounded core package, with a nonblocking enrichment issue.
- `blocked`: no usable groups or lesson, `groups=[]`, `package=null`, at least one
  blocking issue. For example required Fabric unavailable prevents
  assessment-grounded planning; no generic synthetic lesson fallback.
- Required source failures use blocking `required_source_missing` issues.
  Optional failures use nonblocking `optional_source_missing` issues.
  A present source can still be insufficient: use `missing_required_fact`.
  `affected` names groups, lesson, enrichment or student_evidence. No absent
  optional source is marked verified; no invented answer substitutes for a
  failed provider.

## REST/SSE parity and termination

SSE is authenticated POST, `Accept: text/event-stream`, same body as REST.
Perform all auth/class/assessment checks **before** opening the stream.
Before headers, transport/auth failures are ordinary HTTP errors in the same
error envelope. After headers, sanitized unrecoverable transport/composition
errors emit exactly one `error` event then close. Provider failures normally
produce partial/blocked domain results in `final`, not transport errors.
Post-header error codes are restricted to `internal_error` or `cancelled`;
authentication, authorization and request denials belong before stream headers.

Each frame has `event: <type>`, `id: <requestId>:<sequence>`, and `data:` with
one `StreamEventV1` JSON object. JSON `type` matches the SSE event name.
Contiguous sequence starts at zero. Events:

1. `started`: request correlation only, sequence 0.
2. `source`: truthful transitions; announce all four final source states, even
   omitted optional sources. No student evidence or public/raw query progress.
3. Exactly one terminal `final` **or** `error`, then close. `final.payload` is
   the identical `FinalEnvelopeV1` REST would return for the same authorized
   normalized fact snapshot, scenario and requested capabilities.

No `done` frame, final followed by error, duplicate final, source events after
terminal, or successful EOF without terminal. Heartbeats are SSE comments,
not events or sequence increments. Disconnect cancels downstream work; if the
connection is gone there may be no deliverable terminal frame. Client treats
EOF without terminal as interrupted, never as success. Do not automatically
rerun REST after any progress: that would retrieve a different snapshot and
hide failure. Explicit retry creates a new request. Replay/resume is unsupported;
do not claim Last-Event-ID recovery. Parity compares normalized results,
excluding only freshly assigned request/plan IDs and generated/retrieval timings
when requests were actually run separately; use a frozen snapshot for exact
equality. Group/fact/evidence ordering must be deterministic (source enum
order `foundry,fabric,work,web`; remaining stable IDs).

`StreamTranscriptV1` validates contiguous correlation, one terminal and matching
source lifecycle/final states for development. It is not a wire wrapper.
`stream.json` and `blocked.json` demonstrate exact final equality.

## Browser drafts, edits, review and export

Only synthetic browser-local drafts are authorized. Storage key is the
collision-safe JSON tuple:
`["instruct.draft.v1",tenantId,subject,classId,planId]`.
Do not concatenate ambiguous unescaped values. Read only after principal
resolution; require exact principal/class/plan/schema match and current class
access in the UI. On sign-out/principal or class switch, discard active in-memory
draft/evidence; never display another principal's stored draft. Unsupported schema,
invalid hash or revoked access means no automatic render; offer a safe reset,
not a silent merge. Browser storage is not encryption or a server permission.

`DraftV1` keeps immutable `baseline: PlanResultV1`, its SHA-256, ordered teacher
edit revisions, scope, state, and optional review. Canonical hash bytes are
Python-compatible JSON of the validated baseline with keys sorted recursively,
no whitespace separators (`(",",":")`), UTF-8, `ensure_ascii=False`, no trailing
newline; this contract uses integer numeric values only. Frontend must match
this canonicalization, not ordinary unsorted `JSON.stringify`.
The hash detects accidental baseline changes, not malicious tampering or
authorization.

Materialize current content by applying edits in revision order to a copy of
the baseline. Only claim `/text`, group `/studentIds`, and segment `/minutes`
are editable in v1. Paths are simple JSON Pointer paths into `groups` or
`package`, not arbitrary patch operations; no field addition/removal or metadata
mutation. Each change records exact before/after, timestamp, scoped editor and
`teacher_edit_unverified`. A revision lists exactly the invalidated generated
claim IDs. Membership edits must also change the affected rationale text in
that revision and preserve the roster partition; duration edits preserve the
35-minute total. Teacher edits cannot relabel authority or change source facts,
baseline IDs, citations, provenance, issues, or approval metadata.

`generated`: no edits/review. `edited`: one or more revisions, review absent.
`reviewed`: a scoped teacher review binds exactly the current edit revision
(zero is allowed for a reviewed unchanged baseline); it means
`teacher_review_only_not_published`. Any subsequent edit resets state to
`edited` and removes prior review. Keep audit history outside the current
review only if a future schema explicitly defines it. Generation is a new
plan baseline; no silent rebasing. Review is neither publishing nor verified
provider grounding, grading, sharing, or student delivery.

Edited assertions retain their old generated claims only in the baseline.
The materialized UI/export must suppress the old generated citations as support
for every invalidated claim, including edited group rationale; show the
teacher-edit/unverified badge. The JSON retains original provenance for audit,
not endorsement. Teacher review does not restore generated grounding.
Before review/export, B6 must re-evaluate mandatory supports, curriculum and
schedule constraints against the edited content; unsafe/conflicting edits remain
visibly unresolved and cannot be represented as an approved lesson. Structural path/hash
validation is not that semantic policy check.

`ExportV1` contains the complete draft for lossless JSON; Markdown additionally
has rendered current content. Both retain schema/scope, baseline, edits,
invalidations, review, execution mode and evidence provenance. Markdown header
must show synthetic/development status where applicable, partial/blocked status,
review meaning and unverified edits; include citations for unchanged supported
claims and an original-evidence appendix distinct from support for edits.
Markdown is a readable export, not a lossless import format. JSON export is
round-trip validated before accepting an import; importing never grants access.
No external upload/export service is authorized.

## Development-only examples and executable validation

Every example is synthetic and explicitly `development_example`. They are
contract-development payloads, **never runtime fallback, live acceptance proof,
or seed files to read during generation**. The only example-loading helper is
an explicit offline validation function; no route imports or calls it.

| File | Model | Purpose |
|---|---|---|
| request.json | PlanRequestV1 | strict fixed-clock core request |
| provider.json | ProviderBatchV1 | Fabric roster + normalized selected observations |
| complete.json | FinalEnvelopeV1 | 24 learners, four provisional needs, supported 35-minute package |
| partial.json | FinalEnvelopeV1 | Fabric-only usable groups; Foundry unavailable, lesson absent |
| blocked.json | FinalEnvelopeV1 | required providers unavailable/disabled, no usable output |
| stream.json | StreamTranscriptV1 | exact blocked final parity and terminal behavior |
| error.json | ErrorEnvelopeV1 | safe generic denied resource, no evidence disclosure |
| draft.json | DraftV1 | edited partial draft, immutable baseline, unverified changed scaffold |
| export.json | ExportV1 | lossless edited-draft JSON export |

Example complete roster: student-01 has overlapping graph/evidence gaps (graph
primary); student-02 has correct graph/incorrect evidence; student-03 is
successful in both; student-04 has a missing submission; student-05..24 lack
required-skill evidence. Thus primary counts are 1/1/1/21, not a claim of 21
incorrect submissions. Each rationale cites the relevant normalized facts and
roster/absence context. The partial example intentionally has only a roster
and one missing-submission observation: all 24 have insufficient evidence.

From repository root in PowerShell (no dependencies installed or cloud calls):

```powershell
$env:PYTHONPATH='services\api'; $env:PYTHONDONTWRITEBYTECODE='1'; python -c "from app.instruct_contracts import validate_examples; print(validate_examples(r'docs\contracts\examples'))"
```

Schemas are generated with `.model_json_schema()` on each model and
`TypeAdapter(StreamEventV1).json_schema()`. Persistent tests live in
`services\api\tests\test_instruct_contracts.py`, `test_instruct_data.py`, and
`test_instruct_policy.py`. Historical handoffs are not current execution gates.

## Technical integration decisions and remaining capability gaps

### Frozen snapshot, deadlines and cancellation (local B3 implemented)

After authorization, one request uses one immutable normalized snapshot for
REST/SSE composition. Use a 30-second overall monotonic deadline, and at most
20 seconds per selected provider, bounded by remaining overall time. Timeout
normalizes to `failed` with a safe reason; cancel and await outstanding work.
Disconnect propagates cancellation to clients; it is not a successful empty
query. No retry within a stream. Exact provider cancellation support is unverified;
even when remote cancellation is unavailable, stop local work and discard late
results. No provider call starts after the request's cancellation/deadline.
The defaults are configurable downward with `INSTRUCT_REQUEST_TIMEOUT_SECONDS`
and `INSTRUCT_PROVIDER_TIMEOUT_SECONDS` (maximum 30 and 20 respectively).
Async cancellation is awaited, provider exception text is suppressed, and
independent evidence survives a required-source timeout. SSE announces selected
sources as running, then their terminal states and exactly one final/error.
The server cannot deliver a terminal frame after a disconnected transport;
it cancels work and never manufactures a successful final. Interrupted EOF
remains invalid per `StreamTranscriptV1`.

### Stable citations and authorized plan-reference resolver (B3 pending)

Adapters derive opaque stable IDs from source, native object ID, native revision
and locator using domain-separated SHA-256 (prefix plus digest fits `Id`). A new
native revision creates a new reference, never silently rebinds old support.
Content SHA-256 covers the exact UTF-8 excerpt, without an appended newline;
the native revision identifies the full source version. Adapters must verify that
the excerpt entails the normalized fact, not merely attach a citation.

Use a short-lived, bounded in-memory **generated-reference index**, not draft
storage: key `(tenantId, subject, classId, planId, refId)`, value validated evidence,
membership revision and expiry (15 minutes, absolute; no sliding extension).
Never index browser edits. Resolve only after authenticating and rechecking
current membership and assessment access; compare all scope keys and native
revision. Expired/unknown/revoked references return the same generic 404.
The local implementation retains at most 128 plans, prunes expired entries,
copies original evidence (including its native revision) and rechecks current
grant revision and assessment access. It serves the immutable retrieved snapshot,
not a fresh read of the native record. Live native-revision revalidation remains
pending with B4; process restart/worker changes intentionally produce 404 rather
than reconstructing evidence from local assets.
Restart/eviction makes references unavailable; never recover by reading seed
files or accepting browser-provided evidence. Multiple backend replicas require
an explicitly selected authorization-preserving shared index or signed reference
design before deployment; in-memory storage does not claim distributed readiness.

### Required fact and frontend mapping

| Requirement / consumer field | Normalized authority / rule |
| --- | --- |
| Class picker / `classes` | authenticated membership authority, `ClassSummaryV1`; live backing unverified |
| Roster / primary group partition | one Fabric `RosterFactV1`, 24 unique IDs |
| Expected skills/items / absence rationale | one Fabric `AssessmentFactV1`; deterministic selected `ObservationFactV1` per item |
| Objective / `package.objective` | unique effective Foundry approved curriculum; assessment skill roles must match |
| Supports / scaffolds and `implementedSupportFactIds` | every effective Foundry mandatory support, applied to affected students in all groups |
| Timing / segments and `appliedScheduleFactId` | unique effective approved schedule after explicit supersession; fixed 35-minute total including exit |
| Resources / `resourceFactIds` | approved Foundry resources covering both skill roles |
| Needs / `groups`, `overlappingNeeds` | policy-selected provisional primary priority; observed secondary gaps retained |
| Exit ticket / prompt, key, skills | authored instructional proposals, with required skill coverage, not fabricated approved-source claims |
| Evidence panel / claim references | exact fact-reference union with native revision/locator/excerpt; authorized resolver above |
| Source panel / `sources` | four truthful lifecycle states; required failure bounds output, optional failure preserves core |
| Limitations / `issues`, `unresolvedQuestions`, status | blocking versus nonblocking scope; questions never replace blocking issues |
| Identity / principal, class, plan, request IDs | server-owned authenticated scope; browser cannot manufacture grants |
| Draft / scope, baseline hash, edits, review | strict model and ordered edit validation; actual browser persistence and semantic edit rechecks pending |
| Export / `ExportV1` | lossless JSON structure tested; Markdown rendering and edited-claim citation suppression pending |

Live APIs, approval metadata completeness (including explicit verification that
all required supports were returned), class grants, native citation mapping,
identity permissions and retrieval cancellation must be verified at adapter
boundaries. No resource or endpoint is deemed ready by these local decisions.
The policy assumes authorized normalized facts, not raw provider responses;
it cannot prove authorization, approval authenticity or excerpt entailment.
Connected mutations, optional Work delivery extraction, enrichment composition,
semantic checks on teacher edits and deployed REST/SSE parity remain pending.
# Conversational increment (October 15, 2026)

The existing `/api/instruct/v1/plan` and `/plan/stream` contracts remain
unchanged. `POST /api/instruct/v1/conversation` adds an authenticated, **bounded
command interface**, not arbitrary natural-language intelligence. There is no
narration/chat model or external public inference call.

Request (`instruct.conversation.request.v1`):

```json
{
  "schemaVersion": "instruct.conversation.request.v1",
  "context": { "...": "the existing instruct.request.v1 object" },
  "message": "Explain grouping",
  "artifact": {
    "planId": "server-generated-plan-id",
    "baselineSha256": "64 lowercase hexadecimal characters",
    "edits": []
  }
}
```

`artifact` may be null for planning or command clarification. Clients send no
baseline, facts, evidence excerpts, asserted source references or conversation
history. Authorization checks the current principal/class/assessment before
retrieval or index access. Explain/revise resolves the authorized server
baseline from the existing 15-minute, process-local reference index. The
canonical baseline hash must match that snapshot; existing draft edit rules
validate the edits before replay. Changed grants, expired references, server
restarts, other principals/classes/assessments and unknown references fail closed
with sanitized errors. They never retrieve automatically or fall back to cached
client excerpts.

Limits: message 1–500 characters, body 1 MB, at most 50 artifact edit revisions
and 100 changes per revision; edited text at most 12,000 characters.
The UI keeps at most 40 messages in memory and clears history/proposals on
class/assessment/access changes, sign-out and local draft reload. No server
conversation datastore is introduced.

Supported commands (case/whitespace insensitive; terminal periods/exclamation
marks accepted):

| Intent | Accepted commands | Behavior |
| --- | --- | --- |
| Plan | Plan my next lesson; Build instructional plan; Regenerate plan | Fresh live Fabric/Foundry retrieval and existing policy. Optional Work/Web only as explicitly requested and actually available. |
| Reteach | What needs reteaching; What needs reteaching? | Baseline provisional groups with actual item outcomes and resolvable evidence references; no fresh retrieval. |
| Differentiate | Help me differentiate | Existing group scaffolds and authorized-support references; no new assessment inference. |
| Explain | Explain grouping; Why these groups; Why these groups? | Selected actual item samples and baseline grouping context; full rationale stays on canvas. |
| Shorter introduction | Make the intro shorter; Shorten the intro; Revise intro shorter | Proposal moves up to two launch minutes to practice, retaining at least two launch minutes and a 35-minute total. |
| Graph scaffolds | Add more graph scaffolding; More graph scaffolding | Proposal appends an axes/values/trend worked-example scaffold to the current modelling text. |

Other requests return an honest supported-command clarification. Class names
are not parsed or guessed: select a class/assessment from the authorized catalog.
All commands operate only within the fixed October 16 → October 19 scenario.

Response (`instruct.conversation.v1`) contains `requestId`, `principal`,
`classId`, `assessmentId`, `mode: "bounded_commands"`, `intent`, `message`,
`evidenceRefs`, `followups`, nullable `plan` (existing final envelope), and
nullable `proposal` (`planId`, `baselineSha256`, `editRevision`, `changes`).
These models live in `services\api\app\instruct_conversation.py`; existing
plan/draft schemas do not change.

Revision proposals never auto-apply. The UI shows before/after values and
**Apply proposal / Keep current**, binds application to the exact captured
draft (including edits/review), and rejects stale proposals. Changes use the
existing teacher-edit machinery: review resets, affected baseline citations
are invalidated, and open evidence closes. Undo adds inverse changes as a new
unverified revision, never restores a previous review stamp. Existing teacher
text is retained; objective, support records and resource references are not
modified by supported revisions. This is not server semantic approval.
Regeneration into an existing canvas also requires an explicit replacement
choice and never discards teacher edits on request failure.
# General classroom chat v2

The primary UI is now a single conversation, not a lesson builder. No class or
assessment selector is required. The model receives only the caller's authorized
catalog and asks for clarification when scope is ambiguous. Existing v1 plan,
SSE, evidence and legacy conversation endpoints remain backwards-compatible;
the new UI does not use the legacy bounded-command router.

`POST /api/instruct/v1/chat` accepts only
`{schemaVersion:"instruct.chat.request.v2",message,sessionId:null|string}`.
Browser-asserted history, tools, instructions and evidence are rejected.
Messages are limited to 2,000 characters. The server owns an expiring,
principal/grant-revision-scoped process cache (128 conversations, 15-minute idle
expiry, 20 user turns). Restarting the API expires conversations.

The Azure Responses v1 REST boundary uses the API managed identity, `store:false`,
the explicitly configured **gpt-5.6-luna** deployment, six sequential tool calls
maximum, a 90-second overall deadline and existing bounded source deadlines.
Settings: `INSTRUCT_CHAT_ENDPOINT` (resource root, without `/openai/v1`),
`INSTRUCT_CHAT_DEPLOYMENT`, `INSTRUCT_CHAT_MODEL`, `INSTRUCT_CHAT_SCOPE`,
`INSTRUCT_CHAT_TIMEOUT_SECONDS`. No other model or simulated answer is a fallback.
See Microsoft's [Responses documentation](https://learn.microsoft.com/azure/foundry/openai/how-to/responses).

Tools retrieve normalized Fabric assessment or Foundry curriculum/resource facts
without generating a lesson. Work uses the existing source availability boundary;
without an explicitly connected caller-delegated adapter it is unavailable, not
fabricated collaboration context. Web is not exposed as a chat tool. A model can
only select observed facts and citations already retrieved for the current
authorized class/assessment. The server renders selected facts verbatim.
Model prose is separately labelled interpretation, suggestion or clarification,
never a student record or evidence. Missing submissions are not incorrect work.
All source text and prior conversation are untrusted data. No arbitrary tool URLs.

Class/assessment changes discard prior server grounding and conversational turns;
account changes/signout/new conversation clear browser context. Membership is
checked before tools and again before publication. Responses are buffered until
reference validation; the UI shows actual request activity, not fake token streaming.
No student text, token bodies or upstream error payloads are logged by this code.
Production deployment is gated on the separately verified model handoff; unit
tests mock the model boundary and are not proof of live model inference.
