"""Benchmark an existing product provider with repeated, identically ordered trials."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter

from evaluate import evaluate, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "local-api"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(manifest_path: Path, output: Path, provider_name: str, beam_size: int, repeats: int) -> None:
    from app.config import settings
    from app.stt_service import get_stt_provider

    if repeats < 1 or beam_size < 1:
        raise ValueError("repeats and beam_size must be positive")
    samples = read_jsonl(manifest_path)
    if not samples:
        raise ValueError("Empty manifest")
    # Fresh experiment directories prevent accidental mixing of model versions or partial trials.
    output.mkdir(parents=True, exist_ok=False)
    settings.stt_beam_size = beam_size
    provider = get_stt_provider(provider_name)
    configuration = {"provider": provider_name, "whisper_beam_size": beam_size if provider_name == "local-faster-whisper" else None,
                     "repeats": repeats, "ordering_seed": 20260924, "python": platform.python_version(),
                     "platform": platform.platform(), "cpu": platform.processor(),
                     "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                     "product_code_sha256": hashlib.sha256(b"".join((ROOT / name).read_bytes() for name in (
                         "apps/local-api/app/stt_service.py", "apps/local-api/app/config.py", "apps/local-api/scripts/sensevoice_runner.py"))).hexdigest(),
                     "env_overrides": {key: os.environ[key] for key in ("LIKETYPELESS_STT_DEVICE", "LIKETYPELESS_STT_COMPUTE_TYPE", "LIKETYPELESS_STT_MODEL_PATH") if key in os.environ},
                     "packages": {name: importlib.metadata.version(name) for name in ("faster-whisper", "ctranslate2")}}
    write_json(output / "configuration.json", configuration)
    try:
        first = next(iter(samples.values()))
        started = perf_counter()
        warmup = provider.transcribe(Path(first["audio_path"]), language="zh")
        configuration.update(warmup_ms=round((perf_counter() - started) * 1000, 3), model=warmup.model,
                             device=getattr(provider, "_loaded_device", None), compute_type=getattr(provider, "_loaded_compute_type", None))
        if provider_name == "local-sensevoice":
            configuration["device"] = "cpu"  # The current product worker explicitly selects CPU.
            configuration["worker_packages"] = json.loads(subprocess.check_output(
                [settings.sensevoice_python, "-c", "import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in ['funasr','torch','modelscope']}))"], text=True))
        write_json(output / "configuration.json", configuration)
        print(f"Warm-up {configuration['warmup_ms']} ms; scoring {len(samples)} samples x {repeats} trials", flush=True)
        reports = []
        for trial in range(1, repeats + 1):
            order = list(samples)
            random.Random(20260924 + trial).shuffle(order)
            predictions = {}
            with (output / f"predictions-{trial}.jsonl").open("w", encoding="utf-8") as handle:
                for number, identifier in enumerate(order, 1):
                    started = perf_counter()
                    result = provider.transcribe(Path(samples[identifier]["audio_path"]), language="zh")
                    row = {"id": identifier, "asr_text": result.text, "stt_ms": result.elapsed_ms,
                           "end_to_end_ms": round((perf_counter() - started) * 1000, 3),
                           "stt_provider": result.provider, "stt_model": result.model}
                    predictions[identifier] = row
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                    if number % 25 == 0 or number == len(samples):
                        print(f"trial {trial}/{repeats}: {number}/{len(samples)}", flush=True)
            report = evaluate(samples, predictions)
            write_json(output / f"report-{trial}.json", report)
            reports.append(report)
        comparison = {"configuration": configuration, "manifest_sha256": reports[0]["manifest_sha256"], "trials": reports,
                      "median_trial_cer": statistics.median(r["overall"]["asr"]["cer"] for r in reports),
                      "median_trial_p95_ms": statistics.median(r["overall"]["latency_ms"]["p95"] for r in reports),
                      "limitations": ["Trials are repeated measurements on the same utterances, not independent new samples.",
                                      "Warm-up is excluded. Timings cover the ASR provider only, not recording or desktop paste."]}
        write_json(output / "experiment.json", comparison)
    finally:
        if hasattr(provider, "_stop_worker"):
            provider._stop_worker()
        # Release native CUDA resources before Python module teardown on Windows.
        model = getattr(provider, "_model", None)
        if model is not None:
            model.model.unload_model()
            provider._model = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", default="local-faster-whisper", choices=("local-faster-whisper", "local-sensevoice"))
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run(args.manifest, args.output_dir, args.provider, args.beam_size, args.repeats)
