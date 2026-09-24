"""Merge two independent human reviews and any adjudication into prediction JSONL."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path

from evaluate import read_jsonl

BOOLEAN_FIELDS = ("meaning_preserved", "deleted_meaningful_content", "added_information", "protected_terms_preserved", "punctuation_appropriate")
SCORE_FIELDS = ("asr_faithfulness_1_to_5", "translation_faithfulness_1_to_5", "translation_naturalness_1_to_5")


def parse_boolean(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("yes", "y", "true", "1", "是"):
        return True
    if normalized in ("no", "n", "false", "0", "否"):
        return False
    raise ValueError(f"Expected yes/no, got {value!r}")


def merge(predictions: dict[str, dict], reviews: list[dict[str, str]]) -> dict[str, dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in reviews:
        identifier = row["id"]
        if identifier not in predictions:
            raise ValueError(f"Review ID not in predictions: {identifier}")
        if not row.get("reviewer", "").strip():
            raise ValueError(f"{identifier}: reviewer required")
        grouped[identifier].append(row)
    for identifier, rows in grouped.items():
        regular = [row for row in rows if row["reviewer"].strip().lower() != "adjudicator"]
        adjudicators = [row for row in rows if row["reviewer"].strip().lower() == "adjudicator"]
        if len(regular) != 2 or len({row["reviewer"] for row in regular}) != 2:
            raise ValueError(f"{identifier}: exactly two distinct reviewers required")
        decisions: dict[str, bool] = {}
        for field in BOOLEAN_FIELDS if "structured_text" in predictions[identifier] else ():
            values = [parse_boolean(row[field]) for row in regular]
            if values[0] != values[1]:
                if len(adjudicators) != 1:
                    raise ValueError(f"{identifier}: disagreement on {field}; add one adjudicator row")
                decisions[field] = parse_boolean(adjudicators[0][field])
            else:
                decisions[field] = values[0]
        scores = {}
        for field in SCORE_FIELDS:
            values = [int(row[field]) for row in regular if row.get(field, "").strip()]
            if values and (len(values) != 2 or any(value < 1 or value > 5 for value in values)):
                raise ValueError(f"{identifier}: both reviewers must score {field} from 1 to 5")
            if values:
                scores[field] = round(sum(values) / 2, 2)
        predictions[identifier]["human_review"] = {
            **decisions, **scores,
            "reviewers": [row["reviewer"] for row in regular],
            "adjudicated": bool(adjudicators),
        }
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    predictions = read_jsonl(args.predictions)
    with args.reviews.open(encoding="utf-8-sig", newline="") as handle:
        reviews = [row for row in csv.DictReader(handle) if row.get("reviewer", "").strip()]
    merged = merge(predictions, reviews)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in merged.values()), encoding="utf-8")


if __name__ == "__main__":
    main()
