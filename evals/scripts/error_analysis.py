"""Export worst ASR errors for targeted review; output stays local because it quotes corpus text."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from evaluate import edit_distance, normalize, read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    samples = read_jsonl(args.manifest)
    predictions = read_jsonl(args.predictions)
    if samples.keys() != predictions.keys():
        raise ValueError("Manifest and predictions must have the same IDs")
    rows = []
    for identifier, sample in samples.items():
        if "reference" not in sample:
            continue
        reference = normalize(sample["reference"])
        hypothesis = normalize(predictions[identifier]["asr_text"])
        if not reference:
            continue
        edits = edit_distance(reference, hypothesis)
        rows.append({"id": identifier, "source": sample.get("source", ""), "duration_seconds": sample.get("duration_seconds", ""),
                     "character_errors": edits, "reference_characters": len(reference), "sample_cer": round(edits / len(reference), 4),
                     "reference": sample["reference"], "asr_text": predictions[identifier]["asr_text"]})
    rows.sort(key=lambda row: (-row["sample_cer"], -row["character_errors"], row["id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["id"])
        writer.writeheader()
        writer.writerows(rows[:args.limit])
    print(f"Wrote {min(args.limit, len(rows))} error cases")


if __name__ == "__main__":
    main()
