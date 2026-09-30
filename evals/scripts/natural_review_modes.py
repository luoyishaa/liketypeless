"""Pair basic and optional model cleanup on exactly the same recorded raw text."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from summarize_natural_review import EXPECTED_IDS


def _check_ids(rows: list[dict], field: str) -> None:
    ids = [row.get(field, "") for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_IDS:
        raise ValueError(f"Expected NR01–NR30 exactly once in {field}")


def export_manifest(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    _check_ids(rows, "case_id")
    result = []
    for row in rows:
        raw = row.get("raw_transcript", "").strip()
        if not raw:
            raise ValueError(f"{row['case_id']}: raw_transcript is required before mode comparison")
        result.append({"id": row["case_id"], "source": "natural-review", "input_text": raw})
    return result


def merge_mode_report(rows: list[dict[str, str]], report: dict) -> list[dict[str, str]]:
    _check_ids(rows, "case_id")
    samples = report.get("samples", [])
    _check_ids(samples, "id")
    by_id = {sample["id"]: sample for sample in samples}
    merged = []
    for row in rows:
        case_id = row["case_id"]
        sample = by_id[case_id]
        if sample.get("raw_text") != row.get("raw_transcript", "").strip():
            raise ValueError(f"{case_id}: benchmark input differs from recorded raw transcript")
        values = {"basic_text": sample["basic"]["text"],
                  "enhanced_text": sample["enhanced"]["text"],
                  "enhanced_provider": sample["enhanced"]["provider"]}
        for field, value in values.items():
            if row.get(field, "") and row[field] != value:
                raise ValueError(f"{case_id}: existing {field} differs; use a fresh review sheet")
        merged.append({**row, **values})
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--manifest-output", type=Path)
    action.add_argument("--modes-report", type=Path)
    parser.add_argument("--output", type=Path, help="New reviewed CSV; required with --modes-report")
    args = parser.parse_args()
    with args.review.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames or []
        rows = list(reader)
    if args.manifest_output:
        manifest = export_manifest(rows)
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest_output.open("x", encoding="utf-8") as destination:
            for sample in manifest:
                destination.write(json.dumps(sample, ensure_ascii=False) + "\n")
        print(f"Prepared {len(manifest)} fixed raw-text inputs")
    else:
        if args.output is None:
            parser.error("--output is required with --modes-report")
        report = json.loads(args.modes_report.read_text(encoding="utf-8"))
        merged = merge_mode_report(rows, report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8-sig", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            writer.writerows(merged)
        print(f"Merged {len(merged)} paired outputs; manual judgement fields remain unchanged")


if __name__ == "__main__":
    main()
