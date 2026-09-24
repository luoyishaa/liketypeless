"""Export worst ASR errors for targeted review; output stays local because it quotes corpus text."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from evaluate import normalize, read_jsonl


def alignment_counts(reference: str, hypothesis: str) -> dict[str, int]:
    """Minimum edit alignment; ties prefer substitution, then deletion, then insertion."""
    previous = [(j, 0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, char in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        for j, other in enumerate(hypothesis, 1):
            cost, substitutions, deletions, insertions = previous[j - 1]
            diagonal = (cost + (char != other), substitutions + (char != other), deletions, insertions)
            cost, substitutions, deletions, insertions = previous[j]
            deletion = (cost + 1, substitutions, deletions + 1, insertions)
            cost, substitutions, deletions, insertions = current[-1]
            insertion = (cost + 1, substitutions, deletions, insertions + 1)
            current.append(min((diagonal, deletion, insertion), key=lambda item: item[0]))
        previous = current
    errors, substitutions, deletions, insertions = previous[-1]
    return dict(character_errors=errors, substitutions=substitutions, deletions=deletions, insertions=insertions)


def analyze(samples: dict, predictions: dict) -> tuple[list[dict], dict]:
    if not samples or samples.keys() != predictions.keys():
        raise ValueError("Nonempty manifest and predictions must have the same IDs")
    rows = []
    totals = defaultdict(Counter)
    for identifier, sample in samples.items():
        if "reference" not in sample:
            continue
        if not isinstance(predictions[identifier].get("asr_text"), str) or predictions[identifier].get("error"):
            raise ValueError(f"{identifier}: invalid prediction")
        reference = normalize(sample["reference"])
        hypothesis = normalize(predictions[identifier]["asr_text"])
        if not reference:
            raise ValueError(f"{identifier}: empty reference")
        counts = alignment_counts(reference, hypothesis)
        flags = []
        if len(reference) < 5:
            flags.append("short_reference")
        if not hypothesis:
            flags.append("empty_hypothesis")
        if counts["deletions"] >= len(reference) / 2:
            flags.append("major_deletion")
        if re.search(r"[0-9零〇幺一二两三四五六七八九十百千万亿]", sample["reference"]):
            flags.append("number_review")
        if re.search(r"[0-9]", hypothesis) and not re.search(r"[0-9]", reference):
            flags.append("number_format_candidate")
        if re.search(r"[a-z]", hypothesis) and not re.search(r"[a-z]", reference):
            flags.append("unexpected_latin")
        if any(word in reference for word in ("不", "没", "别", "未", "无")):
            flags.append("negation_review")
        source = sample.get("source", "unknown")
        totals[source].update(counts)
        totals[source].update(samples=1, reference_characters=len(reference), exact_matches=int(reference == hypothesis))
        totals[source].update(flags)
        rows.append({"id": identifier, "source": source, "duration_seconds": sample.get("duration_seconds", ""),
                     **counts, "reference_characters": len(reference), "sample_cer": round(counts["character_errors"] / len(reference), 4),
                     "flags": " | ".join(flags), "reference": sample["reference"], "asr_text": predictions[identifier]["asr_text"]})
    rows.sort(key=lambda row: (-row["sample_cer"], -row["character_errors"], row["id"]))
    return rows, {"by_source": {source: {**counts, "cer": round(counts["character_errors"] / counts["reference_characters"], 6)}
                               for source, counts in sorted(totals.items())},
                  "limitations": ["Flags identify review candidates, not verified causes. Number formatting is not automatically forgiven.",
                                  "S/D/I counts use one deterministic minimum-edit alignment; equal-cost alignments may differ."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--summary", type=Path, help="Portable aggregate diagnosis without corpus text")
    args = parser.parse_args()
    samples = read_jsonl(args.manifest)
    predictions = read_jsonl(args.predictions)
    rows, summary = analyze(samples, predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["id"])
        writer.writeheader()
        writer.writerows(rows[:args.limit])
    print(f"Wrote {min(args.limit, len(rows))} error cases")
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
