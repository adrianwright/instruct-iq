"""Canonical synthetic ingestion assets. Explicit offline tool, never a runtime source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CLASS = "class-science-7a"
ASSESSMENT = "assessment-20261016"
EFFECTIVE = "2026-10-16T00:00:00-04:00"
RETRIEVED = "2026-10-19T06:59:00-04:00"
SCENARIO = {
    "assessmentDate": "2026-10-16", "lessonDate": "2026-10-19",
    "timezone": "America/New_York", "planningCutoff": "2026-10-19T07:00:00-04:00",
    "lessonMinutes": 35, "studentCount": 24,
}
ITEMS = {
    "item-axis": {"skillId": "skill-graph", "prompt": "Which axis shows elapsed time?", "answer": "horizontal"},
    "item-trend": {"skillId": "skill-graph", "prompt": "Values at minutes 0, 1, 2 are 2, 4, 6. Describe the trend.", "answer": "increases by 2 each minute"},
    "item-evidence": {"skillId": "skill-evidence", "prompt": "Cite two values supporting an increasing trend.", "answer": "2 at minute 0 and 6 at minute 2"},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def generate():
    students = [f"student-{i:02d}" for i in range(1, 25)]
    batches = {
        source: {
            "schemaVersion": "instruct.provider.v1", "classId": CLASS,
            "assessmentId": ASSESSMENT, "source": source,
            "requested": source in {"fabric", "foundry"},
            "state": "succeeded" if source in {"fabric", "foundry"} else "not_requested",
            "reason": "Synthetic ingestion asset; no provider called." if source in {"fabric", "foundry"} else None,
            "durationMs": 0, "evidence": [], "facts": [],
        } for source in ("foundry", "fabric", "work", "web")
    }

    def fact(source, fid, kind, authority, **values):
        ref = f"ref-{fid}"
        record = {
            "factId": fid, "kind": kind, "authority": authority, "evidenceRefs": [ref],
            "effectiveFrom": EFFECTIVE, **values,
        }
        excerpt = canonical(record).strip()
        batches[source]["facts"].append(record)
        batches[source]["evidence"].append({
            "refId": ref, "classId": CLASS, "source": source, "documentId": f"doc-{fid}",
            "title": f"Synthetic {kind} record {fid}", "locator": f"record:{fid}",
            "excerpt": excerpt, "publicUrl": None,
            "provenance": {
                "mode": "test_double", "nativeId": fid, "nativeRevision": "synthetic-v1",
                "retrievedAt": RETRIEVED, "contentSha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                "adapter": "synthetic-ingestion-v1",
            },
        })

    fact("fabric", "roster", "roster", "assessment_record", studentIds=students)
    fact("fabric", "assessment-coverage", "assessment", "assessment_record",
         assessmentId=ASSESSMENT, graphSkillId="skill-graph", evidenceSkillId="skill-evidence",
         itemSkills={item: spec["skillId"] for item, spec in ITEMS.items()},
         attemptSelection="latest_effective_then_attempt_id")
    responses = []
    for i, student in enumerate(students, 1):
        for item, spec in ITEMS.items():
            if i % 6 == 5 and item == "item-evidence":
                continue
            missing = i % 6 == 4 and item == "item-axis"
            incorrect = (i % 6 in {0, 1} and spec["skillId"] == "skill-graph") or (
                i % 6 in {1, 2} and spec["skillId"] == "skill-evidence")
            outcome = "missing_submission" if missing else "incorrect" if incorrect else "correct"
            attempt = None if missing else f"attempt-{i:02d}-{item}"
            fact("fabric", f"observation-{i:02d}-{item}", "observation", "assessment_record",
                 assessmentId=ASSESSMENT, studentId=student, skillId=spec["skillId"],
                 itemId=item, attemptId=attempt, outcome=outcome,
                 effectiveFrom="2026-10-16T13:00:00-04:00")
            responses.append({
                "studentId": student, "itemId": item, "attemptId": attempt,
                "response": None if missing else "unsupported response" if incorrect else spec["answer"],
                "outcome": outcome,
            })
    fact("foundry", "curriculum", "curriculum", "approved_curriculum",
         approvalId="approval-curriculum-v1", skillIds=["skill-graph", "skill-evidence"],
         objective="Interpret graph axes and trends, then select numerical evidence supporting a claim.")
    fact("foundry", "support-access", "support", "mandatory_support",
         approvalId="approval-support-v1", studentIds=["student-01", "student-04", "student-09"],
         requirement="Provide enlarged high-contrast graphs and a read-aloud of directions in every group.")
    fact("foundry", "support-language", "support", "mandatory_support",
         approvalId="approval-language-v1", studentIds=["student-02", "student-07"],
         requirement="Provide a vocabulary preview and evidence sentence frames without reducing the objective.")
    fact("foundry", "schedule-original", "schedule", "approved_schedule",
         approvalId="approval-schedule-v1", lessonDate="2026-10-19", minutes=60,
         supersedesFactIds=[], effectiveFrom="2026-10-01T00:00:00-04:00",
         effectiveTo="2026-10-16T15:00:00-04:00")
    fact("foundry", "schedule-amended", "schedule", "approved_schedule",
         approvalId="approval-schedule-v2", lessonDate="2026-10-19", minutes=35,
         supersedesFactIds=["schedule-original"], effectiveFrom="2026-10-16T15:00:00-04:00")
    fact("foundry", "resource-graphs", "resource", "approved_resource",
         approvalId="approval-resource-v1", skillIds=["skill-graph", "skill-evidence"],
         usage="Use the approved three-point graph: minutes 0, 1, 2; readings 2, 4, 6.")
    return {
        "schemaVersion": "instruct.seed.v1", "synthetic": True,
        "district": {"districtId": "district-synthetic", "title": "Synthetic Learning District"},
        "teacher": {"tenantId": "synthetic-tenant", "subject": "synthetic-teacher"},
        "membership": {"membershipRevision": "membership-v1", "classId": CLASS,
                       "teacherSubject": "synthetic-teacher", "studentIds": students},
        "class": {"classId": CLASS, "grade": 7, "subject": "science", "assessmentId": ASSESSMENT},
        "scenario": SCENARIO, "items": ITEMS, "responses": responses,
        "sources": list(batches.values()),
    }


def artifacts():
    registry = generate()
    documents = {}
    for record in registry["sources"][0]["facts"]:
        content = record.get("objective", record.get("requirement", record.get("usage", "")))
        if record["kind"] == "schedule":
            content = f"Lesson {record['lessonDate']}: {record['minutes']} minutes."
        documents[f"approved-{record['factId']}.md"] = (
            f"# Synthetic approved {record['kind']}\n\n"
            f"Approval: {record['approvalId']}\n\n"
            f"Effective from: {record['effectiveFrom']}\n\n"
            f"Effective to: {record.get('effectiveTo', 'open')}\n\n"
            f"Supersedes: {', '.join(record.get('supersedesFactIds', [])) or 'none'}\n\n"
            f"{content}\n"
        )
    return {"registry.json": canonical(registry), **documents}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Persist canonical ingestion assets locally.")
    args = parser.parse_args()
    if args.write:
        for name, content in artifacts().items():
            Path(__file__).with_name(name).write_text(content, encoding="utf-8", newline="\n")
    else:
        print(canonical(generate()), end="")
