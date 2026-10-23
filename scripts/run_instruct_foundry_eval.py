"""Submit and retrieve tool-decision evaluations in the existing Foundry project."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from openai.types.evals.run_create_params import (
    DataSourceCreateEvalResponsesRunDataSource,
    DataSourceCreateEvalResponsesRunDataSourceSourceFileContentContent,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evals.instruct.tool_decisions import digest, read_rows, write_rows  # noqa: E402


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def prepare(cases) -> list[DataSourceCreateEvalResponsesRunDataSourceSourceFileContentContent]:
    rows: list[DataSourceCreateEvalResponsesRunDataSourceSourceFileContentContent] = []
    for case in cases:
        if not case["synthetic"] or digest(case["request"]) != case["requestSha256"]:
            raise ValueError(f"{case['id']}: invalid synthetic frozen request")
        request = case["request"]
        rows.append({"item": {
            "case_id": case["id"], "category": case["category"],
            "query": [{"role": "system", "content": request["instructions"]}] + request["input"],
            "tool_definitions": request["tools"],
            "expected_behavior": case["expected_behavior"],
        }})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("submit", "retry", "status"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--deployment", default="instruct-chat-luna")
    parser.add_argument("--cases", type=Path, default=ROOT / ".local" / "instruct-tool-evals" / "cases.jsonl")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    with (
        AzureCliCredential(tenant_id=args.tenant_id) as credential,
        AIProjectClient(endpoint=args.endpoint, credential=credential) as project,
        project.get_openai_client(max_retries=0, timeout=120) as client,
    ):
        if args.action == "submit":
            if args.state.exists():
                raise FileExistsError(args.state)
            cases = read_rows(args.cases)
            if args.smoke:
                selected = {}
                for case in cases:
                    selected.setdefault(case["category"], case)
                cases = list(selected.values())
            frozen_path = args.state.with_suffix(".cases.jsonl")
            write_rows(frozen_path, cases)
            rows = prepare(cases)
            catalog = project.beta.evaluators.get_version(name="builtin.tool_call_accuracy", version="1")
            save(args.state.with_suffix(".evaluator.json"), catalog.as_dict())
            state = {
                "endpoint": args.endpoint, "deployment": args.deployment,
                "casesPath": str(frozen_path), "suiteSha256": digest(cases),
                "caseCount": len(cases), "toolsExecuted": 0,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "framework": "Microsoft Foundry hosted Evals API",
                "samplingDifferences": {
                    "tool_choice": "Not exposed by the hosted sampler; app uses required.",
                    "parallel_tool_calls": "Not exposed by the hosted sampler; app disables parallel calls.",
                    "store": "Foundry persists evaluation inputs, outputs and scores.",
                    "defaults": "Hosted sampler reports seed=42, temperature=1, top_p=1.",
                },
            }
            evaluation = client.evals.create(
                name="Instruct IQ - Layer 1 tool decisions",
                data_source_config={
                    "type": "custom", "include_sample_schema": True,
                    "item_schema": {
                        "type": "object",
                        "properties": {
                            "case_id": {"type": "string"}, "category": {"type": "string"},
                            "query": {"type": "array", "items": {"type": "object"}},
                            "tool_definitions": {"type": "array", "items": {"type": "object"}},
                            "expected_behavior": {"type": "string"},
                        },
                        "required": ["case_id", "query", "tool_definitions"],
                    },
                },
                testing_criteria=[{
                    "type": "azure_ai_evaluator", "name": "tool_call_accuracy",
                    "evaluator_name": catalog.name, "evaluator_version": catalog.version,
                    "initialization_parameters": {"deployment_name": args.deployment, "threshold": 5},
                    "data_mapping": {
                        "query": "{{item.query}}",
                        "tool_definitions": "{{item.tool_definitions}}",
                        "response": "{{sample.output_items}}",
                    },
                }],
                metadata={"scenario": "instruct-iq-layer1", "suite_sha256": state["suiteSha256"]},
            )
            state["evalId"] = evaluation.id
            save(args.state, state)
            request: DataSourceCreateEvalResponsesRunDataSource = {
                "type": "responses",
                "model": args.deployment,
                "source": {"type": "file_content", "content": rows},
                "input_messages": {"type": "item_reference", "item_reference": "item.query"},
                "sampling_params": {
                    "tools": cases[0]["request"]["tools"],
                    "max_completion_tokens": 1400, "reasoning_effort": "low",
                },
            }
            save(args.state.with_suffix(".request.json"), request)
            run = client.evals.runs.create(
                eval_id=evaluation.id,
                name="layer1-smoke" if args.smoke else "layer1-full-240",
                data_source=request,
            )
            state["runId"] = run.id
            state["run"] = run.model_dump(mode="json")
            save(args.state, state)
            print(json.dumps({key: value for key, value in state.items() if key != "run"}), flush=True)
            return 0
        state = json.loads(args.state.read_text(encoding="utf-8"))
        if state["endpoint"] != args.endpoint:
            raise ValueError("Project endpoint differs from the saved run")
        if args.action == "retry":
            previous_outputs = args.state.with_suffix(".outputs.json")
            if previous_outputs.exists():
                save(args.state.with_name(args.state.stem + "." + state["runId"] + ".outputs.json"),
                     json.loads(previous_outputs.read_text(encoding="utf-8")))
            state.setdefault("previousRuns", []).append(state["run"])
            retry_request = json.loads(args.state.with_suffix(".request.json").read_text(encoding="utf-8"))
            # These aren't exposed by Foundry's hosted sampling schema.
            retry_request["sampling_params"].pop("tool_choice", None)
            retry_request["sampling_params"].pop("parallel_tool_calls", None)
            save(args.state.with_suffix(".request.json"), retry_request)
            run = client.evals.runs.create(
                eval_id=state["evalId"], name="layer1-smoke-retry", data_source=retry_request,
            )
            state["runId"] = run.id
            state["run"] = run.model_dump(mode="json")
            state["samplingDifferences"] = {
                "tool_choice": "Not exposed by the hosted sampler; app uses required.",
                "parallel_tool_calls": "Not exposed by the hosted sampler; app disables parallel calls.",
                "store": "Foundry persists evaluation inputs, outputs and scores.",
                "defaults": "Hosted sampler reports seed=42, temperature=1, top_p=1.",
            }
            save(args.state, state)
            print(json.dumps({"evalId": state["evalId"], "runId": run.id, "status": run.status}), flush=True)
            return 0
        run = client.evals.runs.retrieve(eval_id=state["evalId"], run_id=state["runId"])
        state["run"] = run.model_dump(mode="json")
        state["lastPolledAt"] = datetime.now(timezone.utc).isoformat()
        save(args.state, state)
        if run.status in ("completed", "failed", "canceled", "cancelled"):
            items = [item.model_dump(mode="json") for item in client.evals.runs.output_items.list(
                eval_id=state["evalId"], run_id=state["runId"],
            )]
            save(args.state.with_suffix(".outputs.json"), items)
            save(args.state.with_name(args.state.stem + "." + run.id + ".outputs.json"), items)
            print(json.dumps({"status": run.status, "outputItems": len(items),
                              "reportUrl": run.report_url, "resultCounts": run.result_counts.model_dump()
                              if run.result_counts else None}), flush=True)
            return 0 if (run.status == "completed" and run.result_counts
                         and not run.result_counts.errored and not run.result_counts.failed) else 1
        else:
            print(json.dumps({"status": run.status, "runId": run.id}), flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
