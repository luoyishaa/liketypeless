"""Score fixed audio through the product's authenticated /stt/transcribe route."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "local-api"
sys.path.insert(0, str(API_ROOT))
from evaluate import edit_distance, normalize, percentile, ratio, read_jsonl  # noqa: E402
from build_holdout import portable_hash  # noqa: E402


def measure(manifest_path: Path, model_path: Path | None = None) -> dict:
    samples = list(read_jsonl(manifest_path).values())
    if not samples:
        raise ValueError("Manifest is empty")
    for sample in samples:
        if not isinstance(sample.get("reference"), str) or not sample["reference"].strip():
            raise ValueError(f"{sample['id']}: nonempty reference required")
        if not isinstance(sample.get("audio_path"), str) or not Path(sample["audio_path"]).is_file():
            raise ValueError(f"{sample['id']}: existing audio_path required")

    with tempfile.TemporaryDirectory(prefix="liketypeless-asr-api-") as directory, ExitStack() as stack:
        token = secrets.token_hex(24)
        evaluation_env = {"LIKETYPELESS_DATA_DIR": directory, "LIKETYPELESS_SESSION_TOKEN": token}
        if model_path is not None:
            evaluation_env["LIKETYPELESS_STT_MODEL_PATH"] = str(model_path.resolve())
        stack.enter_context(patch.dict(os.environ, evaluation_env))
        from app.main import app  # noqa: E402
        from app.config import settings  # noqa: E402

        # In-process callers may already have imported the application. The
        # benchmark still uses a fresh credential for every invocation.
        stack.enter_context(patch.object(settings, "session_token", token))
        if model_path is not None:
            stack.enter_context(patch.object(settings, "stt_model_path", str(model_path.resolve())))
        runtime = {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "stt_provider": settings.stt_provider,
            "stt_model": settings.stt_model,
            "model_path": settings.stt_model_path,
            "device_setting": settings.stt_device,
            "warmup_policy": "none",
        }
        rows = []
        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
            for sample in samples:
                audio = Path(sample["audio_path"])
                started = perf_counter()
                response = client.post("/stt/transcribe", json={
                    "filePath": str(audio), "language": "zh",
                })
                request_ms = round((perf_counter() - started) * 1000, 3)
                response.raise_for_status()
                result = response.json()
                rows.append({
                    "id": sample["id"], "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                    "asr_text": result["text"], "provider": result["provider"],
                    "model": result["model"], "stt_ms": result["sttElapsedMs"],
                    "request_ms": request_ms,
                })
            runtime["actual_stt_runtime"] = client.get("/health").json()["runtime"]

    reference_chars = sum(len(normalize(sample["reference"])) for sample in samples)
    errors = sum(edit_distance(normalize(sample["reference"]), normalize(row["asr_text"]))
                 for sample, row in zip(samples, rows, strict=True))
    timings = [row["request_ms"] for row in rows]
    return {
        "schema_version": 1,
        "timing_scope": "in_process_product_stt_route",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "portable_manifest_sha256": portable_hash(samples),
        "runtime": runtime,
        "sample_count": len(rows),
        "summary": {
            "raw_asr_cer": ratio(errors, reference_chars),
            "character_errors": errors,
            "reference_characters": reference_chars,
            "request_latency_ms": {
                "first": timings[0], "p50": percentile(timings, 0.5),
                "p95": percentile(timings, 0.95), "max": max(timings),
            },
        },
        "samples": rows,
        "limitations": [
            "Input is a prepared audio file, not a microphone capture.",
            "Request timing excludes recording, text cleanup, desktop focus, and paste.",
            "No warmup is performed; the first request may include model loading.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True, help="Verified local faster-whisper model directory")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not arguments.model_path.is_dir():
        parser.error("--model-path must be an existing directory")
    report = measure(arguments.manifest, arguments.model_path)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {report['sample_count']} audio files through /stt/transcribe: {arguments.output}")


if __name__ == "__main__":
    main()
