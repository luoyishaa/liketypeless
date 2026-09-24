"""Sequential ASR experiments: keep inference workloads from competing for resources."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from evaluate import evaluate, read_jsonl

PROFILES = {
    "whisper-small-beam1": ("local-faster-whisper", 1),
    "whisper-small-beam5": ("local-faster-whisper", 5),
    "sensevoice-small-cpu": ("local-sensevoice", 1),
}


def validate_runtime(configuration: dict) -> None:
    packages = {name: importlib.metadata.version(name) for name in ("faster-whisper", "ctranslate2")}
    overrides = {key: os.environ[key] for key in ("LIKETYPELESS_STT_DEVICE", "LIKETYPELESS_STT_COMPUTE_TYPE", "LIKETYPELESS_STT_MODEL_PATH") if key in os.environ}
    if (configuration.get("python") != platform.python_version()
            or configuration.get("packages") != packages
            or configuration.get("env_overrides", {}) != overrides):
        raise ValueError("Resume runtime differs: use a new experiment directory for changed Python, packages, or environment overrides")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", required=True, help="name=prepared-manifest.jsonl")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--profiles", nargs="+", choices=tuple(PROFILES), default=list(PROFILES))
    parser.add_argument("--resume-completed", action="store_true", help="Validate and reuse fully completed trials; partial directories still fail")
    parser.add_argument("--retain-completed-on-native-exit", action="store_true", help="Retain fully written diagnostics after Windows 0xC0000409; record failure and return nonzero after the matrix")
    args = parser.parse_args()
    suites = dict(item.split("=", 1) for item in args.suite)
    for name, manifest in suites.items():
        if Path(name).name != name or name in (".", "..") or not Path(manifest).is_file():
            raise ValueError(f"Invalid suite: {name}")
    failures = []
    for profile in args.profiles:
        provider, beam = PROFILES[profile]
        for suite, manifest in suites.items():
            directory = args.output_dir / profile / suite
            if args.resume_completed and (directory / "experiment.json").is_file():
                experiment = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
                configuration = experiment["configuration"]
                validate_runtime(configuration)
                root = Path(__file__).resolve().parents[2]
                fingerprint = hashlib.sha256(b"".join((root / name).read_bytes() for name in (
                    "apps/local-api/app/stt_service.py", "apps/local-api/app/config.py", "apps/local-api/scripts/sensevoice_runner.py"))).hexdigest()
                if configuration["product_code_sha256"] != fingerprint:
                    raise ValueError(f"Product code changed since completed experiment: {directory}")
                if (configuration["provider"] != provider or configuration["repeats"] != args.repeats
                        or len(experiment["trials"]) != args.repeats
                        or (provider == "local-faster-whisper" and configuration["whisper_beam_size"] != beam)):
                    raise ValueError(f"Resume configuration mismatch: {directory}")
                for trial, report in enumerate(experiment["trials"], 1):
                    actual = evaluate(read_jsonl(Path(manifest)), read_jsonl(directory / f"predictions-{trial}.jsonl"))
                    if any(actual[key] != report[key] for key in ("manifest_sha256", "prediction_sha256")):
                        raise ValueError(f"Resume evidence mismatch: {directory}")
                print(f"Reusing verified completed experiment: {directory}; inspect its process status separately", flush=True)
                status = directory / "process-status.json"
                if status.is_file() and json.loads(status.read_text(encoding="utf-8"))["exit_code"]:
                    failures.append(str(directory))
                continue
            print(f"Starting {profile}: {suite}", flush=True)
            # Each experiment must be new; completed directories are never silently reused.
            process = subprocess.run([sys.executable, str(Path(__file__).with_name("benchmark_asr.py")),
                            "--manifest", manifest, "--output-dir", str(directory), "--provider", provider,
                            "--beam-size", str(beam), "--repeats", str(args.repeats)])
            if directory.is_dir():
                (directory / "process-status.json").write_text(json.dumps({"exit_code": process.returncode,
                    "completed_report_exists": (directory / "experiment.json").is_file()}, indent=2) + "\n", encoding="utf-8")
            if process.returncode:
                if (args.retain_completed_on_native_exit and process.returncode == 3221226505
                        and (directory / "experiment.json").is_file()):
                    experiment = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
                    if len(experiment["trials"]) != args.repeats:
                        raise SystemExit("Native exit with incomplete experiment")
                    for trial, report in enumerate(experiment["trials"], 1):
                        actual = evaluate(read_jsonl(Path(manifest)), read_jsonl(directory / f"predictions-{trial}.jsonl"))
                        if actual["prediction_sha256"] != report["prediction_sha256"]:
                            raise SystemExit("Native exit with invalid experiment evidence")
                    failures.append(str(directory))
                    print(f"WARNING: retaining completed diagnostics, not a stability pass: {directory}", flush=True)
                    continue
                raise SystemExit(f"Experiment process failed ({process.returncode}); inspect {directory}, including any completed reports.")
    if failures:
        raise SystemExit("Measurements completed with process-exit failures: " + ", ".join(failures))
    print("All experiments completed with clean process exits", flush=True)
