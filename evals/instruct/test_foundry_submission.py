import copy
import importlib.util
import json
from pathlib import Path

import pytest

from tool_decisions import build_cases

PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_instruct_foundry_eval.py"
SPEC = importlib.util.spec_from_file_location("foundry_submission", PATH)
assert SPEC is not None and SPEC.loader is not None
submission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(submission)


def test_hosted_inputs_preserve_real_prompt_tools_and_user_message_without_oracle_leakage():
    cases = list(build_cases())
    rows = submission.prepare(cases)
    assert len(rows) == 240
    for case, row in zip(cases, rows, strict=True):
        item = row["item"]
        assert item["query"][0] == {"role": "system", "content": case["request"]["instructions"]}
        assert item["query"][1:] == case["request"]["input"]
        assert item["tool_definitions"] == case["request"]["tools"]
        assert item["case_id"] == case["id"]
        assert "expected" not in json.dumps(item["query"])


def test_hosted_inputs_reject_tampering_or_non_synthetic_data():
    case = copy.deepcopy(next(build_cases()))
    case["synthetic"] = False
    with pytest.raises(ValueError):
        submission.prepare([case])
    case["synthetic"] = True
    case["request"]["instructions"] = "Tampered"
    with pytest.raises(ValueError):
        submission.prepare([case])
