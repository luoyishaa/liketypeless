"""Score prepared audio through the PyInstaller backend process over loopback HTTP.

This validates the packaged backend and its native dependencies, but it still
does not measure microphone capture, Electron focus restoration, or paste.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import secrets
import subprocess
import tempfile
from threading import Thread
from time import perf_counter, sleep
import urllib.request

from build_holdout import portable_hash
from evaluate import edit_distance, normalize, percentile, ratio, read_jsonl


def request_json(url: str, token: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"},
                                     data=json.dumps(payload).encode("utf-8") if payload is not None else None,
                                     method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


@contextmanager
def launch_backend(executable: Path, model_dir: Path, bundle_dir: Path | None):
    if not executable.is_file() or not model_dir.is_dir() or (bundle_dir is not None and not bundle_dir.is_dir()):
        raise ValueError("Packaged backend, Whisper model, and optional short-model bundle must exist")
    with tempfile.TemporaryDirectory(prefix="liketypeless-packaged-asr-") as data_dir:
        token = secrets.token_hex(32)
        environment = {**os.environ, "LIKETYPELESS_DATA_DIR": data_dir,
                       "LIKETYPELESS_SESSION_TOKEN": token,
                       "LIKETYPELESS_PARENT_PID": str(os.getpid()),
                       "LIKETYPELESS_STT_PROVIDER": "local-routed",
                       "LIKETYPELESS_STT_MODEL_PATH": str(model_dir.resolve())}
        if bundle_dir is not None:
            environment["LIKETYPELESS_SENSEVOICE_BUNDLE_DIR"] = str(bundle_dir.resolve())
        process = subprocess.Popen([str(executable.resolve())], cwd=executable.parent,
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=0x08000000 if os.name == "nt" else 0)
        lines: queue.Queue[str] = queue.Queue()
        diagnostics: list[str] = []
        def stdout_reader():
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)
        def stderr_reader():
            assert process.stderr is not None
            for line in process.stderr:
                diagnostics.append(line)
                if len(diagnostics) > 40:
                    diagnostics.pop(0)
        Thread(target=stdout_reader, daemon=True).start()
        Thread(target=stderr_reader, daemon=True).start()
        base_url = None
        try:
            deadline = perf_counter() + 60
            while perf_counter() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Packaged backend exited: " + "".join(diagnostics)[-1500:])
                try:
                    line = lines.get(timeout=0.5)
                except queue.Empty:
                    continue
                match = re.search(r"LIKETYPELESS_READY:(\d+)", line)
                if match:
                    base_url = f"http://127.0.0.1:{match.group(1)}"
                    break
            if not base_url:
                raise RuntimeError("Packaged backend startup timed out: " + "".join(diagnostics)[-1500:])
            while perf_counter() < deadline:
                try:
                    if request_json(f"{base_url}/health", token).get("modelReady"):
                        break
                except Exception:
                    pass
                sleep(0.1)
            else:
                raise RuntimeError("Packaged backend model verification did not become ready")
            yield base_url, token
        finally:
            if base_url and process.poll() is None:
                try:
                    request_json(f"{base_url}/system/shutdown", token, {})
                except Exception:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def measure(manifest_path: Path, executable: Path, model_dir: Path, bundle_dir: Path | None,
            *, provider: str = "local-routed") -> dict:
    samples = list(read_jsonl(manifest_path).values())
    if not samples:
        raise ValueError("Manifest is empty")
    rows = []
    with launch_backend(executable, model_dir, bundle_dir) as (base_url, token):
        health = request_json(f"{base_url}/health", token)
        if not health.get("modelReady"):
            raise RuntimeError("Packaged Whisper model is not ready")
        for sample in samples:
            audio = Path(sample["audio_path"])
            if not audio.is_file() or not normalize(sample.get("reference", "")):
                raise ValueError(f"{sample['id']}: prepared audio and reference required")
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            if sample.get("prepared_audio_sha256") and digest != sample["prepared_audio_sha256"]:
                raise ValueError(f"{sample['id']}: prepared audio hash mismatch")
            started = perf_counter()
            response = request_json(f"{base_url}/stt/transcribe", token,
                                    {"filePath": str(audio.resolve()), "language": "zh", "provider": provider})
            rows.append({"id": sample["id"], "audio_sha256": digest, "asr_text": response["text"],
                         "provider": response["provider"], "model": response["model"],
                         "stt_ms": response["sttElapsedMs"],
                         "stt_fallback_reason": response.get("sttFallbackReason"),
                         "request_ms": round((perf_counter() - started) * 1000, 3)})

    characters = sum(len(normalize(sample["reference"])) for sample in samples)
    errors = sum(edit_distance(normalize(sample["reference"]), normalize(row["asr_text"]))
                 for sample, row in zip(samples, rows, strict=True))
    timings = [row["request_ms"] for row in rows]
    return {"schema_version": 1, "timing_scope": "packaged_backend_http_stt_route",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "portable_manifest_sha256": portable_hash(samples),
            "runtime": {"platform": platform.platform(), "backend_executable": str(executable.resolve()),
                        "backend_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                        "short_bundle_dir": str(bundle_dir.resolve()) if bundle_dir else None,
                        "requested_provider": provider, "health": health, "warmup_policy": "none"},
            "sample_count": len(rows),
            "summary": {"raw_asr_cer": ratio(errors, characters), "character_errors": errors,
                        "reference_characters": characters,
                        "request_latency_ms": {"first": timings[0], "p50": percentile(timings, 0.5),
                                               "p95": percentile(timings, 0.95), "max": max(timings)}},
            "samples": rows,
            "limitations": ["Packaged backend process over loopback HTTP, not the Electron installer process.",
                            "Prepared files exclude microphone capture, focus recovery, and paste."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--short-bundle-dir", type=Path)
    parser.add_argument("--provider", choices=("local-faster-whisper", "local-routed"), default="local-routed")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.provider == "local-routed" and not args.short_bundle_dir:
        parser.error("--short-bundle-dir is required for routed candidate measurement")
    report = measure(args.manifest, args.backend, args.model_path, args.short_bundle_dir,
                     provider=args.provider)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {report['sample_count']} audio files through packaged backend: {args.output}")


if __name__ == "__main__":
    main()
