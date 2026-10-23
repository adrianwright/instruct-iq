# Layer 1: Instruct IQ tool decisions

These evaluations stop at the model's first response. They never execute
`retrieve`, `answer`, a provider, or the application orchestrator. No Foundry
agent, working tool endpoint, cloud provisioning, or model redeployment is needed.

## Contract and coverage

The application and exporter import the same **unchanged** instructions and JSON
tool schemas from `services\api\app\instruct_model_contract.py`. Exported requests
also reproduce the app's developer-message catalog/snapshot envelope, required
tool choice, disabled parallel calls, token budget, and low reasoning.

`queries.json` contains **60 authored synthetic query templates**, expanded into
**240 cases** across four fictional catalog/ID variants. The variants test ID
binding, not 240 independent intents. These are representative authored cases,
not harvested user traffic or live student records.

| Decision | Cases |
| --- | ---: |
| Assessment evidence: `retrieve(source="fabric")` | 40 |
| Approved curriculum/supports/resources/schedule: `retrieve(source="foundry")` | 40 |
| Teaching-team context: `retrieve(source="work")` | 32 |
| Ambiguous class | 16 |
| Ambiguous assessment | 16 |
| No authorized catalog | 8 |
| Greetings, generic suggestions, unsupported actions | 32 |
| Unauthorized class/assessment requests | 16 |
| Prompt extraction, invented tools, forged references | 16 |
| Already-saved curriculum fact selection | 16 |
| Instruction injection in catalog titles | 8 |

**Important:** this application's final response is itself the `answer` function.
A clarification or a query needing no retrieval must therefore call `answer`
with empty `factIds` and `evidenceRefs`, not return free text. Required tool choice
already constrains tool presence; this suite measures behavior under the actual
app settings, not a model's unconstrained willingness to use tools. Mixed-source
questions with multiple equally valid first retrievals are deliberately excluded
from the exact-match suite.

## Freeze the inputs

From the repository root, with the existing backend/tooling lockfile dependencies
installed:

```powershell
$env:PYTHONPATH = "services\api"
python evals\instruct\tool_decisions.py export
```

The default output is ignored
`.local\instruct-tool-evals\cases.jsonl`. Each row contains `id`, `category`,
`expected`, `expected_behavior`, the **complete model request**, and its SHA-256.
The exporter refuses to overwrite an existing file; use `--output` for another
version. Preserve this file when comparing deployments, models, or prompts.

## Run in the Foundry evaluation framework

The hosted adapter uses `AIProjectClient.get_openai_client().evals` against the
existing project. Foundry generates model responses and runs its built-in
`tool_call_accuracy` evaluator (version 1, strict threshold 5). It does not create
an agent or execute a returned function. Both target and judge use the explicitly
selected deployment.

The caller requires **Foundry User at the parent account scope** for model
inference; project-only access is insufficient.

```powershell
$env:PYTHONPATH = "services\api"
python scripts\run_instruct_foundry_eval.py submit `
  --endpoint https://instruct-example-ai.services.ai.azure.com/api/projects/instruct-iq `
  --tenant-id d9eb725c-64c7-5769-8557-418fda0f460f `
  --state .local\instruct-tool-evals\foundry-full.json
```

Use `--smoke` for one case per category. Use `status` in place of `submit` with
the same `--state`, endpoint and tenant to retrieve progress and download all
terminal per-item results. `retry` creates another run in the same evaluation
group after an operational failure; prior downloaded results are archived.
Evaluation/run IDs, the selected case-file hash, raw run configuration, catalog
definition, report URL, outputs and scores remain persisted. Results are also
visible in the project's Foundry Evaluation page.

**Hosted sampler differences:** the prompt is supplied as a system message.
Foundry retains the real tool schemas and requested low reasoning/1,400-token
budget, but its sampling schema does not expose the application's required
`tool_choice` or disabled `parallel_tool_calls` flags. It reports seed 42,
temperature 1 and top-p 1 defaults. Foundry persists evaluation data regardless
of the application's `store:false` policy. These differences are recorded in
run state; hosted results must not be described as exact application-runtime
parity. Built-in Tool Call Accuracy is an LLM-judge score, not the deterministic
exact-match score described below.

## Portable request/response format

For each row, send **only `row["request"]` plus the target `model` deployment**
to the Responses API. Save the returned object immediately. Do not dispatch the
function call, submit a tool result, or ask the model for another turn.

Save UTF-8 JSONL predictions with this envelope:

```json
{"id":"fabric-01-cedar","response":{"status":"completed","output":[{"type":"function_call","name":"retrieve","arguments":"{\"classId\":\"class-cedar-7a\",\"assessmentId\":\"assessment-cedar-friday\",\"source\":\"fabric\"}"}]}}
```

Use the same frozen cases for each model. Other provider adapters must translate
the real schemas/messages into their native formats and normalize their returned
tool calls into the envelope above; native Claude/Llama clients are not included.
Preserve call count, arguments, text, and completion status during normalization.
Unsupported request settings must be reported explicitly, not silently dropped.
Record deployment/model version, provider adapter, generation settings, case-file
hash, and any deliberate setting differences alongside each run.

For a small smoke run, select one case from each category, saving the selected
rows into a separate cases JSONL. Grade that subset, rather than a partial output
against the full suite. No model calls are made by the exporter or grader.

## Grade saved responses

```powershell
$env:PYTHONPATH = "services\api"
python evals\instruct\tool_decisions.py grade `
  --responses .local\instruct-tool-evals\luna-responses.jsonl `
  --output .local\instruct-tool-evals\luna-grades.json
```

Use `--cases` to select a frozen suite other than the default. Output is created
exclusively, never overwritten. A nonzero exit code means a decision failed, a
response is missing, or an input is invalid.

The deterministic grader checks completed status, exactly one call, expected
tool name, the **frozen request's JSON parameter schema**, exact source/class/
assessment arguments, exact fact/reference selections, and absence of free-text
answers. It rejects extra/missing parameters, bad types/enums, malformed or
duplicate-key JSON, whitespace-only answer messages, unknown tools, and extra
calls. Missing responses remain in the denominator; unknown/duplicate IDs are
errors. Reports include per-category counts and separate failed-check counts.

**Scope of the score:** `passed` means structural and argument accuracy only.
It does not establish that `answer.message` asks a useful clarifying question,
refuses safely, avoids leakage, or stays grounded. Every answer case is marked
`message_review_required` and has an `expected_behavior` rubric for human or
subsequent judge review. A syntactically valid answer with bad prose can pass
the deterministic checks. Do not present this score as full behavioral accuracy.

These adversarial routing cases are not a red-team scan. This suite also does
not measure retrieval quality, authorization enforcement, tool execution,
multi-turn continuation, final instructional quality, or app end-to-end safety.

## Local harness checks

```powershell
$env:PYTHONPATH = "services\api"
python -m pytest evals\instruct services\api\tests\test_instruct_chat.py -q
```

Offline oracle outputs validate the harness, not the deployed model. No live
evaluation, red-team job, or resource change is performed by these checks.
