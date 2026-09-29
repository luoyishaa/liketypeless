"""Create a traceable release snapshot from all supplied repeated ASR trials."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics


def summarize(baseline: dict, candidates: list[dict]) -> dict:
    if not candidates:
        raise ValueError("At least one candidate experiment is required")
    trials = [trial for experiment in candidates for trial in experiment["trials"]]
    if any(t["manifest_sha256"] != baseline["manifest_sha256"] for t in trials):
        raise ValueError("Release comparison requires identical manifests")
    values = [t["overall"]["asr"]["cer"] for t in trials]
    median = statistics.median(values)
    before = statistics.median(t["overall"]["asr"]["cer"] for t in baseline["trials"])
    return {
        "manifest_sha256": baseline["manifest_sha256"],
        "sample_count": trials[0]["sample_count"],
        "baseline_median_cer": before,
        "candidate_median_cer": median,
        "delta_percentage_points": round((median - before) * 100, 6),
        "within_one_percentage_point": median - before <= 0.01 + 1e-9,
        "repeat_count": len(trials),
        "trial_cer": values,
        "trial_prediction_sha256": [t["prediction_sha256"] for t in trials],
        "median_trial_asr_p95_ms": statistics.median(t["overall"]["latency_ms"]["p95"] for t in trials),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True, help="suite=experiment.json; repeat for multiple experiments")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    groups: dict[str, list] = {}
    for value in args.candidate:
        suite, path = value.split("=", 1)
        if suite not in ("read", "short", "longform"):
            raise ValueError("Unknown release suite")
        groups.setdefault(suite, []).append(read(Path(path)))
    if set(groups) != {"read", "short", "longform"}:
        raise ValueError("All three release suites are required")
    result = {
        "status": "candidate-not-human-accepted",
        "requirements_lock_sha256": hashlib.sha256(Path("apps/local-api/requirements-release.lock").read_bytes()).hexdigest(),
        "suites": {suite: summarize(read(args.baseline_root / suite / "experiment.json"), experiments) for suite, experiments in groups.items()},
        "limitations": [
            "Repeated trials reuse the same utterances; they are not additional independent samples.",
            "Timing measures ASR only, not stop-recording-to-usable-text or desktop paste.",
            "Build and test activity overlapped some timings; not a controlled performance acceptance.",
            "Short utterances exhibit temperature-fallback sampling variability; all 13 trials of the selected pinned configuration are included.",
            "No human natural-dictation or clean-machine acceptance has been completed.",
        ],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(s["within_one_percentage_point"] for s in result["suites"].values()):
        raise SystemExit(1)
