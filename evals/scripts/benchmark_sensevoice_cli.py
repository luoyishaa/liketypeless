"""Measure the official portable SenseVoice CLI as an experimental CPU candidate.

This is not a product-route or installed-package benchmark. Each sample starts a
fresh process, so the timings include model startup and should not be described
as steady-state ASR latency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from time import perf_counter

from build_holdout import portable_hash
from evaluate import edit_distance, normalize, percentile, ratio, read_jsonl


def measure(manifest_path: Path, executable: Path, model: Path, *, source: str | None = None,
            limit: int | None = None) -> dict:
    if not executable.is_file() or not model.is_file():
        raise ValueError("Existing runtime executable and GGUF model required")
    samples = list(read_jsonl(manifest_path).values())
    if source:
        samples = [sample for sample in samples if sample.get("source") == source]
    if limit is not None:
        samples = samples[:limit]
    if not samples:
        raise ValueError("No matching samples")

    rows = []
    for sample in samples:
        audio = Path(sample["audio_path"])
        if not audio.is_file() or not normalize(sample.get("reference", "")):
            raise ValueError(f"{sample['id']}: audio and reference required")
        if audio.suffix.lower() != ".wav":
            raise ValueError(f"{sample['id']}: prepared WAV required; refusing source audio {audio.suffix}")
        started = perf_counter()
        result = subprocess.run([str(executable), "-m", str(model), "-a", str(audio), "--backend", "cpu"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                                check=False)
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        if result.returncode != 0:
            raise RuntimeError(f"{sample['id']}: SenseVoice CLI failed ({result.returncode}): {result.stderr[-500:]}")
        text = result.stdout.strip()
        rows.append({"id": sample["id"], "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                     "asr_text": text, "process_ms": elapsed_ms,
                     "character_errors": edit_distance(normalize(sample["reference"]), normalize(text)),
                     "reference_characters": len(normalize(sample["reference"])),
                     "speaker": sample.get("speaker")})

    timings = [row["process_ms"] for row in rows]
    errors = sum(row["character_errors"] for row in rows)
    characters = sum(row["reference_characters"] for row in rows)
    return {
        "schema_version": 1,
        "timing_scope": "fresh_process_per_sample_official_sensevoice_cli_cpu_candidate",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "portable_manifest_sha256": portable_hash(samples),
        "runtime": {"platform": platform.platform(), "backend": "cpu", "executable": str(executable.resolve()),
                    "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                    "model": str(model.resolve()), "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                    "warmup_policy": "none; new process and model load per sample"},
        "sample_count": len(rows),
        "summary": {"raw_asr_cer": ratio(errors, characters), "character_errors": errors,
                    "reference_characters": characters,
                    "process_latency_ms": {"first": timings[0], "p50": percentile(timings, 0.5),
                                           "p95": percentile(timings, 0.95), "max": max(timings)}},
        "samples": rows,
        "limitations": ["Candidate CLI only; not integrated into or measured through the installed product.",
                        "Each request starts a fresh process and includes model loading.",
                        "Prepared files exclude microphone capture, cleanup, focus recovery and paste."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    report = measure(args.manifest, args.executable, args.model, source=args.source, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {report['sample_count']} prepared audio files; CER={report['summary']['raw_asr_cer']}")


if __name__ == "__main__":
    main()
