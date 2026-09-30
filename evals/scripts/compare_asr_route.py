"""Pair Whisper and SenseVoice predictions on identical prepared audio.

The route threshold must be chosen on development data before evaluating a
locked holdout. This script reports evidence; it never promotes the candidate.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random

from evaluate import edit_distance, normalize, percentile, ratio, read_jsonl


def compare(samples: list[dict], whisper: dict, sensevoice: dict,
            *, threshold_seconds: float, bootstrap_draws: int = 5000,
            candidate_is_routed: bool = False) -> dict:
    if threshold_seconds <= 0 or bootstrap_draws < 1 or not samples:
        raise ValueError("Positive threshold, bootstrap draws, and samples required")
    ids = [sample["id"] for sample in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate sample IDs")

    def index(report: dict) -> dict:
        rows = report["samples"]
        indexed = {row["id"]: row for row in rows}
        if len(indexed) != len(rows) or not set(ids).issubset(indexed):
            raise ValueError("Prediction IDs must contain every selected manifest ID without duplicates")
        return indexed

    old = index(whisper)
    new = index(sensevoice)
    rows = []
    for sample in samples:
        identifier = sample["id"]
        old_row, new_row = old[identifier], new[identifier]
        if old_row["audio_sha256"] != new_row["audio_sha256"]:
            raise ValueError(f"{identifier}: audio hashes differ")
        if sample.get("prepared_audio_sha256") and old_row["audio_sha256"] != sample["prepared_audio_sha256"]:
            raise ValueError(f"{identifier}: prediction audio differs from manifest")
        reference = normalize(sample["reference"])
        if not reference:
            raise ValueError(f"{identifier}: empty reference")
        eligible = float(sample["duration_seconds"]) <= threshold_seconds
        if candidate_is_routed:
            provider = new_row.get("provider")
            if provider not in {"local-sensevoice-gguf", "local-faster-whisper"}:
                raise ValueError(f"{identifier}: unexpected routed provider {provider}")
            if not eligible and provider != "local-faster-whisper":
                raise ValueError(f"{identifier}: long audio incorrectly routed to SenseVoice")
            if eligible and provider == "local-faster-whisper" and not new_row.get("stt_fallback_reason"):
                raise ValueError(f"{identifier}: short candidate fallback lacks a reason")
            use_new = True
            actual_provider = "sensevoice" if provider == "local-sensevoice-gguf" else "whisper"
        else:
            use_new = eligible
            actual_provider = "sensevoice" if use_new else "whisper"
        old_errors = edit_distance(reference, normalize(old_row["asr_text"]))
        new_errors = edit_distance(reference, normalize(new_row["asr_text"]))
        rows.append({"id": identifier, "speaker": sample.get("speaker", identifier),
                     "reference_characters": len(reference), "whisper_errors": old_errors,
                     "sensevoice_errors": new_errors, "route_errors": new_errors if use_new else old_errors,
                     "route_provider": actual_provider})

    characters = sum(row["reference_characters"] for row in rows)
    old_errors = sum(row["whisper_errors"] for row in rows)
    new_errors = sum(row["sensevoice_errors"] for row in rows)
    route_errors = sum(row["route_errors"] for row in rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row["speaker"]].append(row)
    speaker_keys = sorted(groups)
    rng = random.Random(20260930)
    gains = []
    for _ in range(bootstrap_draws):
        draw = [row for _ in speaker_keys for row in groups[rng.choice(speaker_keys)]]
        draw_chars = sum(row["reference_characters"] for row in draw)
        gains.append((sum(row["whisper_errors"] - row["route_errors"] for row in draw) / draw_chars)
                     if draw_chars else 0.0)
    gains.sort()
    lower = gains[int(0.025 * (len(gains) - 1))]
    upper = gains[int(0.975 * (len(gains) - 1))]
    return {
        "schema_version": 1,
        "threshold_seconds": threshold_seconds,
        "sample_count": len(rows), "speaker_count": len(groups),
        "whisper": {"character_errors": old_errors, "raw_asr_cer": ratio(old_errors, characters)},
        "candidate_all" if candidate_is_routed else "sensevoice_all": {
            "character_errors": new_errors, "raw_asr_cer": ratio(new_errors, characters)},
        "route": {"character_errors": route_errors, "reference_characters": characters,
                  "raw_asr_cer": ratio(route_errors, characters),
                  "sensevoice_samples": sum(row["route_provider"] == "sensevoice" for row in rows)},
        "paired_gain": {"cer_points": round((old_errors - route_errors) / characters, 6),
                        "relative_error_reduction": ratio(old_errors - route_errors, old_errors),
                        "speaker_bootstrap_95_cer_points": [round(lower, 6), round(upper, 6)],
                        "bootstrap_draws": bootstrap_draws, "seed": 20260930},
        "samples": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--whisper", type=Path, required=True)
    parser.add_argument("--sensevoice", type=Path, required=True)
    parser.add_argument("--source", help="Select one source from a development manifest")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--threshold-seconds", type=float, required=True)
    parser.add_argument("--candidate-is-routed", action="store_true", help="Score actual product provider choices and require fallback reasons")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples = list(read_jsonl(args.manifest).values())
    if args.source:
        samples = [sample for sample in samples if sample.get("source") == args.source]
    if args.limit is not None:
        samples = samples[:args.limit]
    whisper = json.loads(args.whisper.read_text(encoding="utf-8"))
    sensevoice = json.loads(args.sensevoice.read_text(encoding="utf-8"))
    report = compare(samples, whisper, sensevoice, threshold_seconds=args.threshold_seconds,
                     candidate_is_routed=args.candidate_is_routed)
    report["manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"n={report['sample_count']} route CER={report['route']['raw_asr_cer']} "
          f"Whisper CER={report['whisper']['raw_asr_cer']} "
          f"gain CI={report['paired_gain']['speaker_bootstrap_95_cer_points']}")


if __name__ == "__main__":
    main()
