from __future__ import annotations

import argparse
import json
from pathlib import Path


METRICS = ("asr.cer", "latency_ms.p50", "latency_ms.p95", "safety.protected_term_recall", "safety.unsafe_output_rate", "translation.exact_match_rate")


def value_at(report: dict, path: str):
    value = report
    for part in path.split("."):
        value = value[part]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    arguments = parser.parse_args()
    baseline = json.loads(arguments.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    print("| Metric | Baseline | Candidate | Delta |")
    print("|---|---:|---:|---:|")
    for metric in METRICS:
        before, after = value_at(baseline, metric), value_at(candidate, metric)
        print(f"| {metric} | {before:.6f} | {after:.6f} | {after - before:+.6f} |")
    if candidate["safety"]["unsafe_output_rate"] > baseline["safety"]["unsafe_output_rate"]:
        raise SystemExit("Safety regression: unsafe output rate increased.")


if __name__ == "__main__":
    main()
