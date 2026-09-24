"""Select high-impact errors plus a fixed random control for human ASR review."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path

from error_analysis import analyze
from evaluate import read_jsonl
from make_manifest import rank


def select(samples: dict, predictions: dict, worst: int, random_count: int) -> list[dict]:
    rows, _ = analyze(samples, predictions)
    sources = defaultdict(list)
    for row in rows:
        sources[row["source"]].append(row)
    selected = []
    for source, group in sorted(sources.items()):
        errors = sorted((row for row in group if row["character_errors"] > 0), key=lambda row: (-row["character_errors"], -row["sample_cer"], row["id"]))[:worst]
        used = {row["id"] for row in errors}
        control = sorted((row for row in group if row["id"] not in used), key=lambda row: rank(row["id"]))[:random_count]
        for reason, subset in (("high_character_error", errors), ("random_control", control)):
            selected.extend({**samples[row["id"]], "review_selection": reason} for row in subset)
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, nargs="+", required=True)
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--worst-per-source", type=int, default=10)
    parser.add_argument("--random-per-source", type=int, default=5)
    args = parser.parse_args()
    samples, predictions = {}, {}
    for paths, target in ((args.manifest, samples), (args.predictions, predictions)):
        for path in paths:
            rows = read_jsonl(path)
            if set(rows) & set(target):
                raise ValueError("Duplicate IDs between input files")
            target.update(rows)
    chosen = select(samples, predictions, args.worst_per_source, args.random_per_source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("manifest", chosen), ("predictions", [predictions[row["id"]] for row in chosen])):
        (args.output_dir / f"{name}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Selected {len(chosen)} cases. This error-enriched review set does not estimate population error rates.")
