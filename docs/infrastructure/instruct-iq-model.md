# Instruct IQ chat model

Deployment identifiers and endpoints in this public guide are synthetic
examples. Supply the approved account explicitly as `foundryAccountName`;
the model template has no environment-specific account default.

## Verified deployment

On 2026-10-15 the explicitly approved exact model `gpt-5.6-luna`, version
`2026-07-09`, was deployed successfully as `instruct-chat-luna` in Central US.
The SKU is GlobalStandard, capacity 5: ARM reports **5,000 TPM and 5 RPM**.
Before provisioning, the live parent catalog supported this version/SKU;
subscription quota and model-capacity endpoints both showed 250 available
GlobalStandard units. No quota increase, reserved throughput, other-account
changes, or Fabric capacity changes were made.

Live inference using the existing API UAMI passed: strict `add_numbers`
function schema with required tool choice and no parallel calls; a stateless
`function_call_output` continuation carrying instructions; conversational
prose ("Adding 2 and 3 gives 5."); and strict JSON output `{"sum":5}`.
The initial successful execution was `instruct-chat-model-probe-oarpfer`.
The app-aligned baseline below then passed in execution
`instruct-chat-model-probe-75xjuh4` (terminal status Succeeded).
The service's response `model` field returned the deployment alias; the exact
model identity/version above were independently verified through ARM.

The superseded, own new `instruct-chat` GPT-4.1-mini deployment was deleted
after verifying its exact identity and that the live app had no model binding.
Its earlier verification execution was stopped. No app settings were changed.
No GPT-4.1 deployment is handed off.

## Scope and repeatability

`infra\instruct\chat-model.bicep` manages only a model deployment on the existing
`instruct-example-ai` parent in `rg-instruct-iq`. It requires an explicit
GPT-5.6 catalog variant and retains the default content filter. It does not
manage the account, application, identities, or other infrastructure. Before
running it, recheck the selected model's live catalog version/SKU, matching
quota usage key, and regional model capacity. Use incremental deployment only.

`infra\instruct\chat-model-probe.py` runs inside an Azure container using the
API UAMI. It checks a strict function schema, tool-result conversational prose,
and strict JSON output against OpenAI v1 Responses. Tokens remain in
memory; logs contain only synthetic inputs and responses. Run it only after
the approved model is deployed. The bounded probe job has no ingress, retry
limit zero, and a 240-second timeout. The one-off probe job was deleted after
persisting evidence; no idle verification resource or public ingress remains.

The existing API UAMI client ID is
`f3a13e63-b9ab-5b9b-8850-98b64917ffcb`; principal ID is
`0e29e0f2-ca26-588f-a314-f5a7905f046f`. It already holds Cognitive Services User
at this parent-account scope; no additional role was granted.

## Safe configuration handoff

- OpenAI v1 base URL:
  `https://instruct-example-ai.openai.azure.com/openai/v1/`
- Resource root: `https://instruct-example-ai.openai.azure.com`.
- Request path: `responses`; model field: `instruct-chat-luna`.
- Entra scope: `https://cognitiveservices.azure.com/.default`.
- No dated API-version query parameter for v1.
- Keep configuration use-case-neutral: no lesson-planning system prompt.
- Verified app baseline: `store:false`, `max_output_tokens:1400`,
  `reasoning:{"effort":"low"}`. An earlier baseline with 1024 output tokens and
  reasoning omitted also passed. Do not use GPT-4.1's `max_tokens` parameter. An initial Chat
  Completions probe with the old parameter assumptions failed HTTP 400;
  Responses is the verified protocol, not Chat Completions.
- Safe exact values and non-secret inference evidence are in ignored
  `.local\instruct-iq-deployment\chat-model.json` and
  `.local\instruct-iq-deployment\chat-model-inference.json`.
- Keep total input/output allocation within the low demo token rate. A 5–7K
  token app request exceeds this allocation; compact/chunk evidence rather
  than assuming all retrieved facts fit. Two-round tool turns also consume
  shared TPM/RPM. Honor 429 retry hints with bounded retries and user-visible
  failure; the smoke test is not a concurrency or full-app load test.
- Measured synthetic usage across the three calls: 170, 93, and 64 tokens
  respectively (327 total), with zero reasoning tokens returned. This does not
  establish a full grounding payload's token estimate or sustained latency.
- Token-rate allocation is not a spending cap. GlobalStandard is pay-per-token
  and may process globally; no PTU reservation or regional-only residency is implied.

Reference: [Azure OpenAI v1 API lifecycle](https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle).
