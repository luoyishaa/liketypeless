"""Summarize observed desktop input trials without treating a sent paste key as delivery."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from evaluate import edit_distance, normalize, percentile, ratio


FIELDS = (
    "trial_id", "target_app", "mode", "reference_text", "raw_transcript",
    "final_text", "outcome", "result_recoverable", "stop_to_usable_ms",
    "correction_edits", "critical_fact_changed",
)
TARGET_APPS = ("notepad", "browser", "word")
OUTCOMES = ("direct", "manual_copy", "lost", "wrong_target")


def _read_trials(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        trials = []
        seen = set()
        for line, row in enumerate(reader, 2):
            trial_id = row["trial_id"].strip()
            if not trial_id or trial_id in seen:
                raise ValueError(f"Line {line}: missing or duplicate trial_id")
            seen.add(trial_id)
            for field in ("target_app", "mode", "outcome", "result_recoverable", "critical_fact_changed"):
                row[field] = row[field].strip().lower()
            if row["target_app"] not in TARGET_APPS or row["mode"] not in ("basic", "enhanced"):
                raise ValueError(f"Line {line}: invalid target_app or mode")
            if row["outcome"] not in OUTCOMES:
                raise ValueError(f"Line {line}: invalid outcome")
            if row["result_recoverable"] not in ("yes", "no") or row["critical_fact_changed"] not in ("yes", "no"):
                raise ValueError(f"Line {line}: use yes or no for the boolean fields")
            if row["outcome"] == "lost" and row["result_recoverable"] != "no":
                raise ValueError(f"Line {line}: lost result cannot be marked recoverable")
            if not row["reference_text"].strip():
                raise ValueError(f"Line {line}: reference_text is required")
            if row["outcome"] in ("direct", "manual_copy") and not row["final_text"].strip():
                raise ValueError(f"Line {line}: delivered or copied result needs final_text")
            try:
                row["correction_edits"] = int(row["correction_edits"])
                row["stop_to_usable_ms"] = float(row["stop_to_usable_ms"]) if row["stop_to_usable_ms"].strip() else None
            except ValueError as error:
                raise ValueError(f"Line {line}: invalid number") from error
            if row["correction_edits"] < 0 or row["stop_to_usable_ms"] is not None and row["stop_to_usable_ms"] < 0:
                raise ValueError(f"Line {line}: negative counts or latency are invalid")
            if row["outcome"] in ("direct", "manual_copy") and row["stop_to_usable_ms"] is None:
                raise ValueError(f"Line {line}: usable result needs stop_to_usable_ms")
            trials.append(row)
        return trials


def _latency(values: list[float]) -> dict:
    return {"samples": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95)}


def summarize(trials: list[dict]) -> dict:
    count = len(trials)
    char_count = sum(len(normalize(row["reference_text"])) for row in trials)
    char_errors = sum(edit_distance(normalize(row["reference_text"]), normalize(row["raw_transcript"])) for row in trials)
    by_app = {app: sum(row["target_app"] == app for row in trials) for app in TARGET_APPS}
    by_mode = {mode: sum(row["mode"] == mode for row in trials) for mode in ("basic", "enhanced")}
    direct = sum(row["outcome"] == "direct" for row in trials)
    wrong = sum(row["outcome"] == "wrong_target" for row in trials)
    lost = sum(row["result_recoverable"] == "no" for row in trials)
    evaluable = all(by_app[app] >= 20 for app in TARGET_APPS)
    return {
        "schema_version": 1,
        "measurement_scope": "observed_desktop_trials; human-observed outcome, not automated paste confirmation",
        "trial_count": count,
        "by_target_app": by_app,
        "by_mode": by_mode,
        "overall": {
            "direct_input_count": direct,
            "direct_input_rate": ratio(direct, count),
            "manual_copy_count": sum(row["outcome"] == "manual_copy" for row in trials),
            "wrong_target_count": wrong,
            "unrecoverable_count": lost,
            "raw_asr_cer": ratio(char_errors, char_count),
            "raw_asr_character_errors": char_errors,
            "raw_asr_reference_characters": char_count,
            "critical_fact_changed_count": sum(row["critical_fact_changed"] == "yes" for row in trials),
            "correction_edits": sum(row["correction_edits"] for row in trials),
            "direct_stop_to_usable_ms": _latency([row["stop_to_usable_ms"] for row in trials if row["outcome"] == "direct"]),
            "manual_copy_stop_to_usable_ms": _latency([row["stop_to_usable_ms"] for row in trials if row["outcome"] == "manual_copy"]),
        },
        "release_gate": {
            "criteria": "at least 20 trials per target app; direct rate >= 59/60; zero wrong-target and unrecoverable outcomes",
            "evaluable": evaluable,
            "passed": direct / count >= 59 / 60 and wrong == 0 and lost == 0 if evaluable else None,
        },
        "limitations": [
            "CSV observations are not automatically verified; this report cannot certify clean-machine behavior.",
            "CER is calculated from the raw ASR text, not polished output.",
            "Latency is stop-of-recording to observed usable text; direct and manual-copy outcomes are kept separate.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = summarize(_read_trials(args.trials))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Summarized {report['trial_count']} observed trials: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
