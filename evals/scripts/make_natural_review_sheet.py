"""Create a blank, local-only 30-utterance review sheet from fixed open-ended cues."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from summarize_natural_review import EXPECTED_IDS

FIELDS = (
    "case_id", "category", "cue", "machine_id", "app_version", "asr_model", "warm_state",
    "reference_text", "raw_transcript", "basic_text", "enhanced_text", "enhanced_provider",
    "basic_usable", "enhanced_usable", "basic_correction_edits", "enhanced_correction_edits",
    "basic_fact_changed", "enhanced_fact_changed", "reviewer", "notes",
)


def make_rows(tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    ids = [task.get("case_id", "") for task in tasks]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_IDS:
        repeated = next((case_id for case_id in ids if ids.count(case_id) > 1), None)
        raise ValueError(f"Expected NR01–NR30 exactly once; duplicate={repeated}, missing={sorted(EXPECTED_IDS - set(ids))}")
    if any(not task.get("cue", "").strip() or not task.get("category", "").strip() for task in tasks):
        raise ValueError("Every task needs a category and an open-ended cue")
    return [dict.fromkeys(FIELDS, "") | {key: task[key] for key in ("case_id", "category", "cue")}
            for task in sorted(tasks, key=lambda item: item["case_id"])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path("evals/fixtures/natural-review-tasks.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tasks = [json.loads(line) for line in args.tasks.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = make_rows(tasks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Created {len(rows)} blank review cases: {args.output}")


if __name__ == "__main__":
    main()
