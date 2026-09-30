"""Summarize completed, audio-grounded review of 30 natural utterances.

Never substitute model self-judgement for the human correction and fact-change
columns. Incomplete forms intentionally produce null quality metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from evaluate import edit_distance, normalize, ratio

EXPECTED_IDS = {f"NR{index:02d}" for index in range(1, 31)}
REQUIRED = ("machine_id", "app_version", "asr_model", "warm_state", "reference_text",
            "enhanced_provider", "basic_usable", "enhanced_usable",
            "basic_correction_edits", "enhanced_correction_edits", "basic_fact_changed",
            "enhanced_fact_changed", "reviewer")


def summarize(rows: list[dict[str, str]]) -> dict:
    ids = [row.get("case_id", "") for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_IDS:
        raise ValueError("Review form must contain exactly NR01–NR30 once each")
    completed = [row for row in rows if all(str(row.get(field, "")).strip() for field in REQUIRED)
                 and all(field in row for field in ("raw_transcript", "basic_text", "enhanced_text"))]
    if len(completed) != len(rows):
        return {"schema_version": 1, "sample_count": len(rows), "completed_count": len(completed),
                "complete": False, "raw_asr_cer": None, "basic_structure_usable_rate": None,
                "enhanced_structure_usable_rate": None, "basic_correction_edits": None,
                "enhanced_correction_edits": None, "paired_correction_edits_saved": None,
                "basic_critical_fact_changes": None, "enhanced_critical_fact_changes": None,
                "enhanced_model_used_count": None, "enhanced_fallback_count": None}
    for row in rows:
        if row["warm_state"] not in {"cold", "warm"}:
            raise ValueError(f"{row['case_id']}: warm_state must be cold or warm")
        for name in ("basic_usable", "enhanced_usable", "basic_fact_changed", "enhanced_fact_changed"):
            if row[name] not in {"0", "1"}:
                raise ValueError(f"{row['case_id']}: {name} must be 0 or 1")
        for name in ("basic_correction_edits", "enhanced_correction_edits"):
            if not row[name].isdigit():
                raise ValueError(f"{row['case_id']}: {name} must be a nonnegative integer")
        if not normalize(row["reference_text"]):
            raise ValueError(f"{row['case_id']}: reference must contain spoken words")

    chars = sum(len(normalize(row["reference_text"])) for row in rows)
    errors = sum(edit_distance(normalize(row["reference_text"]), normalize(row["raw_transcript"])) for row in rows)
    basic_edits = sum(int(row["basic_correction_edits"]) for row in rows)
    enhanced_edits = sum(int(row["enhanced_correction_edits"]) for row in rows)
    model_used = sum(row["enhanced_provider"].startswith("hybrid-conservative-llm:") for row in rows)
    return {"schema_version": 1, "sample_count": len(rows), "completed_count": len(rows), "complete": True,
            "raw_asr_cer": ratio(errors, chars), "character_errors": errors, "reference_characters": chars,
            "basic_structure_usable_rate": ratio(sum(int(row["basic_usable"]) for row in rows), len(rows)),
            "enhanced_structure_usable_rate": ratio(sum(int(row["enhanced_usable"]) for row in rows), len(rows)),
            "basic_correction_edits": basic_edits, "enhanced_correction_edits": enhanced_edits,
            "paired_correction_edits_saved": basic_edits - enhanced_edits,
            "basic_critical_fact_changes": sum(int(row["basic_fact_changed"]) for row in rows),
            "enhanced_critical_fact_changes": sum(int(row["enhanced_fact_changed"]) for row in rows),
            "enhanced_model_used_count": model_used, "enhanced_fallback_count": len(rows) - model_used,
            "machine_ids": sorted({row["machine_id"] for row in rows}),
            "app_versions": sorted({row["app_version"] for row in rows}),
            "asr_models": sorted({row["asr_model"] for row in rows})}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.review.open(encoding="utf-8-sig", newline="") as source:
        report = summarize(list(csv.DictReader(source)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['completed_count']}/{report['sample_count']} reviews complete; {args.output}")


if __name__ == "__main__":
    main()
