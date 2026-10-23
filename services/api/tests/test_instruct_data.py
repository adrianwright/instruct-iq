import hashlib
import importlib.util
import json
from pathlib import Path

from app.instruct_contracts import ProviderBatchV1

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("instruct_generator", ROOT / "data" / "instruct" / "generate.py")
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_canonical_assets_are_reproducible_and_persisted():
    assert generator.generate() == generator.generate()
    for name, content in generator.artifacts().items():
        assert (ROOT / "data" / "instruct" / name).read_text(encoding="utf-8") == content


def test_registry_coverage_missingness_and_provenance():
    registry = generator.generate()
    students = registry["membership"]["studentIds"]
    assert len(students) == len(set(students)) == 24
    assert registry["membership"]["teacherSubject"] == registry["teacher"]["subject"]
    for source in registry["sources"]:
        batch = ProviderBatchV1.model_validate_json(json.dumps(source))
        for evidence in batch.evidence:
            assert evidence.provenance.contentSha256 == hashlib.sha256(evidence.excerpt.encode()).hexdigest()
    observations = registry["sources"][1]["facts"][2:]
    assert {o["studentId"] for o in observations} == set(students)
    assert {o["itemId"] for o in observations} == set(registry["items"])
    assert any(o["outcome"] == "missing_submission" and o["attemptId"] is None for o in observations)
    assert not any(o["studentId"] == "student-05" and o["itemId"] == "item-evidence" for o in observations)
    for response in registry["responses"]:
        match = next(o for o in observations if (o["studentId"], o["itemId"]) == (
            response["studentId"], response["itemId"]))
        assert (match["outcome"], match["attemptId"]) == (response["outcome"], response["attemptId"])
    foundry = registry["sources"][0]["facts"]
    assert all(f["approvalId"] for f in foundry)
    amended = next(f for f in foundry if f["factId"] == "schedule-amended")
    assert amended["minutes"] == 35 and amended["supersedesFactIds"] == ["schedule-original"]
