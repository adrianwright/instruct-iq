import copy
import json

import pytest
from jsonschema import Draft202012Validator

import tool_decisions as suite
from app.instruct_model_contract import SYSTEM, TOOLS

CASES = list(suite.build_cases())


def correct_response(case):
    arguments = dict(case["expected"]["arguments"])
    if case["expected"]["name"] == "answer":
        arguments["message"] = "Which authorized class and assessment do you mean?"
    return {
        "status": "completed",
        "output": [{
            "type": "function_call", "name": case["expected"]["name"],
            "arguments": json.dumps(arguments), "call_id": "offline-oracle",
        }],
    }


def test_suite_is_deterministic_and_has_documented_coverage():
    assert CASES == list(suite.build_cases())
    assert len(CASES) == 240
    assert len({case["id"] for case in CASES}) == 240
    assert {case["category"] for case in CASES} == set(suite.RUBRICS)
    for tool in TOOLS:
        Draft202012Validator.check_schema(tool["parameters"])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_oracle_is_schema_valid_and_uses_the_real_contract(case):
    assert case["request"]["instructions"] == SYSTEM
    assert case["request"]["tools"] == TOOLS
    assert case["request"]["tool_choice"] == "required"
    assert case["request"]["parallel_tool_calls"] is True
    assert case["request"]["store"] is False
    assert suite.grade_case(case, correct_response(case))["passed"]
    snapshot = json.loads(case["request"]["input"][0]["content"].split(": ", 1)[1])
    expected = case["expected"]
    if expected["name"] == "retrieve":
        args = expected["arguments"]
        assert any(
            row["classId"] == args["classId"] and args["assessmentId"] in row["assessmentIds"]
            for row in snapshot["catalog"]
        )
    else:
        assert set(expected["arguments"]["factIds"]) <= {fact["factId"] for fact in snapshot["facts"]}
        assert set(expected["arguments"]["evidenceRefs"]) <= {
            ref for fact in snapshot["facts"] for ref in fact["evidenceRefs"]
        }


@pytest.mark.parametrize("mutation,failed_check", [
    ("no_call", "one_call"),
    ("two_calls", "one_call"),
    ("wrong_tool", "tool_name"),
    ("unknown_tool", "schema_valid"),
    ("wrong_source", "arguments_match"),
    ("invalid_source", "schema_valid"),
    ("wrong_class", "arguments_match"),
    ("wrong_assessment", "arguments_match"),
    ("extra_argument", "schema_valid"),
    ("missing_argument", "schema_valid"),
    ("wrong_type", "schema_valid"),
    ("invalid_json", "schema_valid"),
    ("duplicate_key", "schema_valid"),
    ("non_json_constant", "schema_valid"),
    ("arguments_object", "schema_valid"),
    ("incomplete", "completed"),
    ("free_text", "no_free_text"),
    ("bad_output", "one_call"),
    ("bad_response", "completed"),
])
def test_rejects_bad_model_decisions(mutation, failed_check):
    case = CASES[0]
    response = correct_response(case)
    call = response["output"][0]
    arguments = json.loads(call["arguments"])
    if mutation == "no_call":
        response["output"] = []
    elif mutation == "two_calls":
        response["output"].append(dict(call))
    elif mutation == "wrong_tool":
        call["name"] = "answer"
    elif mutation == "unknown_tool":
        call["name"] = "get_student_record"
    elif mutation == "wrong_source":
        arguments["source"] = "foundry"
    elif mutation == "invalid_source":
        arguments["source"] = "web"
    elif mutation == "wrong_class":
        arguments["classId"] = "private-class"
    elif mutation == "wrong_assessment":
        arguments["assessmentId"] = "private-assessment"
    elif mutation == "extra_argument":
        arguments["student_id"] = "12345"
    elif mutation == "missing_argument":
        del arguments["assessmentId"]
    elif mutation == "wrong_type":
        arguments["classId"] = 12345
    elif mutation == "incomplete":
        response["status"] = "incomplete"
    elif mutation == "free_text":
        response["output"].append({"type": "message", "content": [{"text": "Everyone failed."}]})
    elif mutation == "bad_output":
        response["output"] = {}
    elif mutation == "bad_response":
        response = None
    call["arguments"] = json.dumps(arguments)
    if mutation == "invalid_json":
        call["arguments"] = "{"
    elif mutation == "duplicate_key":
        call["arguments"] = '{"source":"fabric","source":"foundry"}'
    elif mutation == "non_json_constant":
        call["arguments"] = '{"classId":NaN}'
    elif mutation == "arguments_object":
        call["arguments"] = arguments
    result = suite.grade_case(case, response)
    assert not result["passed"]
    assert not result["checks"][failed_check]


@pytest.mark.parametrize("mutation", [
    "empty_message", "wrong_message_type", "long_message",
    "invented_fact", "invented_reference", "duplicate_selection",
])
def test_answer_content_boundaries(mutation):
    case = next(case for case in CASES if case["category"] == "cached_fact")
    response = correct_response(case)
    call = response["output"][0]
    arguments = json.loads(call["arguments"])
    if mutation == "empty_message":
        arguments["message"] = "  "
    elif mutation == "wrong_message_type":
        arguments["message"] = 23
    elif mutation == "long_message":
        arguments["message"] = "x" * 4001
    elif mutation == "invented_fact":
        arguments["factIds"] = ["invented"]
    elif mutation == "invented_reference":
        arguments["evidenceRefs"] = ["invented"]
    else:
        arguments["factIds"] *= 2
    call["arguments"] = json.dumps(arguments)
    assert not suite.grade_case(case, response)["passed"]


def test_answer_prose_semantics_are_explicitly_not_scored():
    case = next(case for case in CASES if case["category"] == "ambiguous_class")
    response = correct_response(case)
    call = response["output"][0]
    args = json.loads(call["arguments"])
    args["message"] = "This prose is not a clarifying question and must be reviewed separately."
    call["arguments"] = json.dumps(args)
    result = suite.grade_case(case, response)
    assert result["passed"]
    assert result["message_review_required"]
    assert "Ask which authorized class" in result["expected_behavior"]


def test_missing_predictions_are_failures_not_excluded_from_denominator():
    predictions = [{"id": CASES[0]["id"], "response": correct_response(CASES[0])}]
    report = suite.grade_rows(CASES, predictions)
    assert report["total"] == 240
    assert report["passed"] == 1
    assert len(report["missingResponseIds"]) == 239


def test_rejects_unknown_or_duplicate_predictions_and_empty_suites():
    prediction = {"id": CASES[0]["id"], "response": correct_response(CASES[0])}
    for cases, rows in [
        (CASES, [prediction, prediction]),
        (CASES, [{**prediction, "id": "not-in-suite"}]),
        ([], []),
    ]:
        with pytest.raises(ValueError):
            suite.grade_rows(cases, rows)


def test_frozen_requests_are_graded_without_substituting_current_prompt():
    case = copy.deepcopy(CASES[0])
    case["request"]["instructions"] = "A frozen older contract."
    case["requestSha256"] = suite.digest(case["request"])
    assert suite.grade_case(case, correct_response(case))["passed"]
    case["request"]["instructions"] = "Tampered."
    with pytest.raises(ValueError, match="checksum mismatch"):
        suite.grade_case(case, correct_response(case))


def test_jsonl_roundtrip_and_no_overwrite(tmp_path):
    path = tmp_path / "cases.jsonl"
    suite.write_rows(path, CASES)
    assert suite.read_rows(path) == CASES
    with pytest.raises(FileExistsError):
        suite.write_rows(path, CASES)
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nonempty"):
        suite.read_rows(path)


def test_cli_exports_and_grades_offline(tmp_path, monkeypatch, capsys):
    cases_path, responses_path, grades_path = (
        tmp_path / name for name in ("cases.jsonl", "responses.jsonl", "grades.json")
    )
    monkeypatch.setattr("sys.argv", ["tool_decisions", "export", "--output", str(cases_path)])
    assert suite.main() == 0
    assert json.loads(capsys.readouterr().out)["cases"] == 240
    suite.write_rows(responses_path, [
        {"id": case["id"], "response": correct_response(case)} for case in CASES
    ])
    monkeypatch.setattr("sys.argv", [
        "tool_decisions", "grade", "--cases", str(cases_path),
        "--responses", str(responses_path), "--output", str(grades_path),
    ])
    assert suite.main() == 0
    assert json.loads(grades_path.read_text(encoding="utf-8"))["passed"] == 240
