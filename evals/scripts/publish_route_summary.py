"""Publish aggregate-only, same-binary paired ASR evidence from local reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform


def summarize_pair(label: str, baseline: dict, routed: dict, paired: dict) -> dict:
    if (baseline["runtime"]["backend_sha256"] != routed["runtime"]["backend_sha256"]):
        raise ValueError(f"{label}: backend binaries differ")
    if baseline["portable_manifest_sha256"] != routed["portable_manifest_sha256"]:
        raise ValueError(f"{label}: manifests differ")
    if not (baseline["sample_count"] == routed["sample_count"] == paired["sample_count"]):
        raise ValueError(f"{label}: sample counts differ")
    if (baseline["runtime"]["requested_provider"] != "local-faster-whisper"
            or routed["runtime"]["requested_provider"] != "local-routed"):
        raise ValueError(f"{label}: unexpected provider comparison")
    if (baseline["summary"]["character_errors"] != paired["whisper"]["character_errors"]
            or routed["summary"]["character_errors"] != paired["route"]["character_errors"]):
        raise ValueError(f"{label}: paired and aggregate results differ")
    return {
        "cohort": label, "sample_count": paired["sample_count"], "speaker_count": paired["speaker_count"],
        "portable_manifest_sha256": baseline["portable_manifest_sha256"],
        "route_threshold_seconds": paired["threshold_seconds"],
        "reference_characters": baseline["summary"]["reference_characters"],
        "whisper": {"character_errors": baseline["summary"]["character_errors"],
                    "raw_asr_cer": baseline["summary"]["raw_asr_cer"],
                    "request_latency_ms": baseline["summary"]["request_latency_ms"]},
        "routed": {"character_errors": routed["summary"]["character_errors"],
                   "raw_asr_cer": routed["summary"]["raw_asr_cer"],
                   "sensevoice_samples": paired["route"]["sensevoice_samples"],
                   "request_latency_ms": routed["summary"]["request_latency_ms"]},
        "paired_gain": {key: paired["paired_gain"][key] for key in
                        ("cer_points", "relative_error_reduction", "speaker_bootstrap_95_cer_points")},
    }


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for cohort in ("short", "read"):
        for kind in ("baseline", "routed", "paired"):
            parser.add_argument(f"--{cohort}-{kind}", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--machine", required=True, help="Public CPU/GPU/OS description of measured host")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cohorts = []
    binaries = set()
    for cohort in ("short", "read"):
        baseline, routed, paired = (load(getattr(args, f"{cohort}_{kind}"))
                                    for kind in ("baseline", "routed", "paired"))
        cohorts.append(summarize_pair(cohort, baseline, routed, paired))
        binaries.add(baseline["runtime"]["backend_sha256"])
    if len(binaries) != 1:
        raise ValueError("All cohorts must use one identical packaged backend binary")
    result = {"schema_version": 1, "version": args.version, "test_layer": "pyinstaller_packaged_backend_http",
              "backend_executable_sha256": binaries.pop(), "machine": args.machine,
              "platform": platform.platform(), "audio_source": "publisher AISHELL-1 train, disjoint speakers",
              "model_versions": {"whisper": "small / beam=1", "sensevoice_gguf_revision":
                                 "90c1c61912018b70ada0fcc024ea24aca62f2e63",
                                 "funasr_runtime_tag": "runtime-llamacpp-v0.2.6"},
              "cold_warm_policy": "No explicit warmup; first request separately reported; later requests warmed.",
              "cohorts": cohorts,
              "limitations": ["Packaged backend, not NSIS-installed desktop or microphone-to-input latency.",
                              "No independent Windows host or cross-application input validation in this report."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Published aggregate-only comparison for {sum(c['sample_count'] for c in cohorts)} clips")


if __name__ == "__main__":
    main()
