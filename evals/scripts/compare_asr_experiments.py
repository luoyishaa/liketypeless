"""Compare repeated ASR experiments with paired, speaker-cluster CER intervals."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics

from evaluate import edit_distance, normalize, percentile, read_jsonl


def paired_delta(samples: dict, before: dict, after: dict, draws: int = 2000) -> dict:
    if not samples or samples.keys() != before.keys() or samples.keys() != after.keys():
        raise ValueError("Paired comparison requires identical nonempty sample IDs")
    clusters = defaultdict(lambda: [0, 0, 0])
    changed = wins = losses = 0
    for identifier, sample in samples.items():
        reference = normalize(sample["reference"])
        if not reference:
            raise ValueError("Empty reference")
        first, second = normalize(before[identifier]["asr_text"]), normalize(after[identifier]["asr_text"])
        error_before, error_after = edit_distance(reference, first), edit_distance(reference, second)
        # Shared room/channel acoustics make meeting speakers non-independent.
        if sample.get("source") == "fleurs-cmn-hans-cn":
            # Legacy manifests mislabeled corpus IDs as speaker IDs; never use those for speaker intervals.
            cluster = "unknown-speakers"
        else:
            cluster = identifier.split(":")[1] if sample.get("source") == "aishell-4-meeting" else sample.get("speaker", identifier)
        cluster = f"{sample.get('source', 'unknown')}:{cluster}"
        values = clusters[cluster]
        values[0] += len(reference)
        values[1] += error_before
        values[2] += error_after
        changed += first != second
        wins += error_after < error_before
        losses += error_after > error_before
    groups = list(clusters.values())
    denominator = sum(group[0] for group in groups)
    before_cer, after_cer = (sum(group[index] for group in groups) / denominator for index in (1, 2))
    interval = None
    constructed = any(sample.get("source") == "constructed-longform" for sample in samples.values())
    unknown_speakers = any(sample.get("source") == "fleurs-cmn-hans-cn" or
                           (not sample.get("speaker") and sample.get("source") != "aishell-4-meeting") for sample in samples.values())
    if len(groups) >= 10 and not constructed and not unknown_speakers:
        rng = random.Random(20260924)
        deltas = []
        for _ in range(draws):
            selected = rng.choices(groups, k=len(groups))
            deltas.append(sum(group[2] - group[1] for group in selected) / sum(group[0] for group in selected))
        interval = [round(percentile(deltas, p), 6) for p in (0.025, 0.975)]
    return {"samples": len(samples), "clusters": len(groups), "cer_before": round(before_cer, 6), "cer_after": round(after_cer, 6),
            "absolute_cer_delta": round(after_cer - before_cer, 6),
            "relative_error_change": round(after_cer / before_cer - 1, 6) if before_cer else None,
            "cer_delta_95pct_cluster_bootstrap": interval, "bootstrap_draws": draws if interval else 0,
            "changed_transcripts": changed, "improved_utterances": wins, "worsened_utterances": losses,
            "tied_utterances": len(samples) - wins - losses,
            "interval_note": "Paired cluster bootstrap; first trial only; assumes sampled clusters are representative."
                             if interval else "Too few independent clusters, unavailable speaker IDs, or constructed stress audio; no confidence interval is claimed."}


def trial_stats(experiment: dict) -> dict:
    trials = experiment["trials"]
    def values(path):
        selected = []
        for trial in trials:
            value = trial
            for key in path:
                value = value[key]
            selected.append(value)
        return {"values": selected, "median": statistics.median(selected), "min": min(selected), "max": max(selected)}
    return {"cer": values(("overall", "asr", "cer")), "p50_ms": values(("overall", "latency_ms", "p50")),
            "p95_ms": values(("overall", "latency_ms", "p95")),
            "warmup_ms": experiment["configuration"]["warmup_ms"],
            "provider": experiment["configuration"]["provider"], "device": experiment["configuration"]["device"],
            "coordinator_python": experiment["configuration"].get("python"),
            "product_code_sha256": experiment["configuration"].get("product_code_sha256"),
            "packages": experiment["configuration"].get("worker_packages", experiment["configuration"]["packages"])}


def compare(manifest: Path, baseline: Path, candidate: Path, candidate_manifest: Path | None = None) -> dict:
    first = json.loads((baseline / "experiment.json").read_text(encoding="utf-8"))
    second = json.loads((candidate / "experiment.json").read_text(encoding="utf-8"))
    if first["manifest_sha256"] != second["manifest_sha256"] and candidate_manifest is None:
        raise ValueError("Experiments use different manifests")
    if not first["trials"] or len(first["trials"]) != len(second["trials"]) or first["configuration"]["ordering_seed"] != second["configuration"]["ordering_seed"]:
        raise ValueError("Experiments must have equal trial counts and ordering seeds")
    samples = read_jsonl(manifest)
    candidate_samples = read_jsonl(candidate_manifest) if candidate_manifest else samples
    if samples.keys() != candidate_samples.keys() or any(samples[key]["reference"] != candidate_samples[key]["reference"] for key in samples):
        raise ValueError("Audio preprocessing comparisons require identical IDs and exact reference text")
    before = read_jsonl(baseline / "predictions-1.jsonl")
    after = read_jsonl(candidate / "predictions-1.jsonl")
    from evaluate import evaluate
    for verification_samples, directory, experiment in ((samples, baseline, first), (candidate_samples, candidate, second)):
        for trial, report in enumerate(experiment["trials"], 1):
            verified = evaluate(verification_samples, read_jsonl(directory / f"predictions-{trial}.jsonl"))
            if (verified["manifest_sha256"] != experiment["manifest_sha256"]
                    or verified["prediction_sha256"] != report["prediction_sha256"]
                    or verified["overall"] != report["overall"]):
                raise ValueError("Supplied manifest, predictions, or metrics do not match experiment")
    by_source = {}
    for source in sorted({row["source"] for row in samples.values()}):
        subset = {key: row for key, row in samples.items() if row["source"] == source}
        by_source[source] = paired_delta(subset, {key: before[key] for key in subset}, {key: after[key] for key in subset})
    return {"manifest_sha256": first["manifest_sha256"], "candidate_manifest_sha256": second["manifest_sha256"],
            "comparison_type": "audio_preprocessing" if candidate_manifest else "provider_configuration",
            "baseline": trial_stats(first), "candidate": trial_stats(second),
            "baseline_process": json.loads((baseline / "process-status.json").read_text(encoding="utf-8")) if (baseline / "process-status.json").is_file() else None,
            "candidate_process": json.loads((candidate / "process-status.json").read_text(encoding="utf-8")) if (candidate / "process-status.json").is_file() else None,
            "paired": paired_delta(samples, before, after), "by_source": by_source,
            "limitations": ["Latency compares deployed configurations, not equal hardware: SenseVoice currently uses CPU, Whisper uses CUDA when available.",
                            "Three trials describe local variability, not a latency confidence interval. No recording/UI/paste time is included.",
                            "Known test sets and diagnostic slices must not be treated as a new unseen holdout or official leaderboard score."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, help="Explicit audio-preprocessing diagnostic; IDs and reference text must remain identical")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.manifest, args.baseline, args.candidate, args.candidate_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["paired"], ensure_ascii=False))
