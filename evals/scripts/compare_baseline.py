"""Compare reports from the same manifest; fail on an automatic safety regression."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

METRICS = (
    ("overall.asr.cer", "lower"),
    ("overall.latency_ms.p50", "lower"),
    ("overall.latency_ms.p95", "lower"),
    ("overall.asr_real_time_factor", "lower"),
    ("overall.asr.human_faithfulness_mean_1_to_5", "higher"),
    ("safety.protected_term_recall", "higher"),
    ("safety.automatic_violation_rate", "lower"),
    ("safety.human_faithful_rate", "higher"),
    ("translation.chrf_plus_plus", "higher"),
    ("translation.human_faithfulness_mean_1_to_5", "higher"),
    ("translation.human_naturalness_mean_1_to_5", "higher"),
)


def value_at(report: dict, path: str):
    value = report
    for part in path.split("."):
        value = value[part]
    return value


def compare(baseline: dict, candidate: dict) -> tuple[str, bool]:
    if baseline["schema_version"] != candidate["schema_version"]:
        raise ValueError("Report schema versions differ")
    if baseline["manifest_sha256"] != candidate["manifest_sha256"]:
        raise ValueError("Reports use different manifests; compare identical sample sets")
    if baseline["sample_count"] != candidate["sample_count"] or set(baseline["by_source"]) != set(candidate["by_source"]):
        raise ValueError("Reports must have identical sample and source coverage")
    if (baseline["overall"]["asr"]["samples"] != candidate["overall"]["asr"]["samples"]
            or baseline["overall"]["latency_ms"]["samples"] != candidate["overall"]["latency_ms"]["samples"]):
        raise ValueError("Reports must have identical ASR and latency coverage")
    if baseline["translation"]["samples"] != candidate["translation"]["samples"] or baseline["safety"]["structure_samples"] != candidate["safety"]["structure_samples"]:
        raise ValueError("Reports must have identical translation and safety coverage")
    lines = ["| Metric | Baseline | Candidate | Absolute change | Relative change |", "|---|---:|---:|---:|---:|"]
    metrics = list(METRICS)
    for source in sorted(baseline["by_source"]):
        for suffix, direction in (("asr.cer", "lower"), ("latency_ms.p95", "lower")):
            metrics.append((f"by_source.{source}.{suffix}", direction))
    if set(baseline.get("by_reference_length", {})) != set(candidate.get("by_reference_length", {})):
        raise ValueError("Reports must have identical reference-length coverage")
    for length in sorted(baseline.get("by_reference_length", {})):
        metrics.append((f"by_reference_length.{length}.asr.cer", "lower"))
    for metric, direction in metrics:
        before, after = value_at(baseline, metric), value_at(candidate, metric)
        if before is None and after is None:
            continue
        if before is None or after is None:
            raise ValueError(f"{metric}: metric coverage differs between reports")
        change = after - before
        relative = f"{change / abs(before) * 100:+.2f}%" if before else "n/a (zero baseline)"
        arrow = "↑" if direction == "higher" else "↓"
        lines.append(f"| {metric} {arrow} | {before:.4f} | {after:.4f} | {change:+.4f} | {relative} |")
    before = baseline["safety"]["automatic_violation_rate"]
    after = candidate["safety"]["automatic_violation_rate"]
    regression = before is not None and after is not None and after > before
    lines.append("")
    lines.append("Safety gate: **FAIL**" if regression else "Safety gate: **PASS**")
    return "\n".join(lines), regression


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    summary, regression = compare(baseline, candidate)
    print(summary)
    if regression:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
