"""Measure the product's basic text cleanup on a fixed JSONL input set.

This exercises the local API route in process. It does not measure ASR,
microphone capture, desktop delivery, or semantic faithfulness.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import sys
import tempfile
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import urlopen

from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "local-api"
sys.path.insert(0, str(API_ROOT))
from evaluate import normalize_protected, percentile, ratio, read_jsonl  # noqa: E402


def _model_start_state(base_url: str, model: str) -> str:
    try:
        with urlopen(f"{base_url.rstrip('/')}/api/ps", timeout=1) as response:
            active = json.load(response).get("models", [])
    except (OSError, URLError, ValueError, KeyError):
        return "ollama_unavailable"
    return "loaded" if any(item.get("name") == model or item.get("model") == model for item in active) else "not_loaded"


def measure(manifest_path: Path, enhanced: bool = False, prewarm_enhanced: bool = False) -> dict:
    if prewarm_enhanced and not enhanced:
        raise ValueError("Explicit prewarm requires enhanced mode")
    samples = list(read_jsonl(manifest_path).values())
    if not samples:
        raise ValueError("Manifest is empty")
    for sample in samples:
        if not isinstance(sample.get("input_text"), str) or not sample["input_text"].strip():
            raise ValueError(f"{sample['id']}: nonempty input_text required")

    with tempfile.TemporaryDirectory(prefix="liketypeless-eval-") as directory:
        os.environ["LIKETYPELESS_DATA_DIR"] = directory
        token = secrets.token_hex(24)
        os.environ["LIKETYPELESS_SESSION_TOKEN"] = token
        from app.main import app  # noqa: E402 - import after isolated API configuration
        from app.config import settings  # noqa: E402

        runtime = {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "ollama_model": settings.default_model if enhanced else None,
            "model_start_state": _model_start_state(settings.ollama_base_url, settings.default_model) if enhanced else "not_measured",
            "warmup_policy": "none",
        }

        rows = []
        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
            if prewarm_enhanced:
                warmup_started = perf_counter()
                client.post("/llm/prepare").raise_for_status()
                state = "loading"
                while perf_counter() - warmup_started < 60:
                    status = client.get("/llm/status")
                    status.raise_for_status()
                    state = status.json()["state"]
                    if state == "ready":
                        break
                    sleep(0.05)
                if state != "ready":
                    raise RuntimeError(f"Enhanced model did not become ready within 60 seconds: {state}")
                runtime["warmup_policy"] = "explicit_optional_prepare"
                runtime["prewarm_ms"] = round((perf_counter() - warmup_started) * 1000, 3)
            for sample in samples:
                started = perf_counter()
                response = client.post("/llm/structure", json={
                    "text": sample["input_text"], "cleanupMode": "basic",
                })
                elapsed_ms = round((perf_counter() - started) * 1000, 3)
                response.raise_for_status()
                result = response.json()
                rows.append({
                    "id": sample["id"], "raw_text": sample["input_text"],
                    "basic": {
                        "text": result["structuredText"], "provider": result["model"],
                        "elapsed_ms": elapsed_ms,
                    },
                })
                if enhanced:
                    started = perf_counter()
                    response = client.post("/llm/structure", json={
                        "text": sample["input_text"], "cleanupMode": "enhanced",
                    })
                    elapsed_ms = round((perf_counter() - started) * 1000, 3)
                    response.raise_for_status()
                    result = response.json()
                    rows[-1]["enhanced"] = {
                        "text": result["structuredText"], "provider": result["model"],
                        "elapsed_ms": elapsed_ms, "degraded": result["degraded"],
                        "degradation_reason": result["degradationReason"],
                    }

    def summarize_mode(mode: str) -> dict:
        protected_total = protected_kept = 0
        violation_ids = []
        for sample, row in zip(samples, rows, strict=True):
            output = row[mode]["text"]
            normalized = normalize_protected(output)
            protected = sample.get("protected_terms", [])
            verbatim = sample.get("verbatim_terms", [])
            forbidden = sample.get("forbidden_phrases", [])
            protected_total += len(protected) + len(verbatim)
            protected_kept += sum(normalize_protected(term) in normalized for term in protected)
            protected_kept += sum(term in output for term in verbatim)
            if (any(normalize_protected(term) not in normalized for term in protected)
                    or any(term not in output for term in verbatim)
                    or any(normalize_protected(term) in normalized for term in forbidden)):
                violation_ids.append(sample["id"])

        times = [row[mode]["elapsed_ms"] for row in rows]
        providers = Counter(row[mode]["provider"] for row in rows)
        summary = {
            "provider_counts": dict(sorted(providers.items())),
            "changed_samples": sum(row["raw_text"] != row[mode]["text"] for row in rows),
            "latency_ms": {"p50": percentile(times, 0.5), "p95": percentile(times, 0.95)},
            "protected_terms": protected_total,
            "protected_term_recall": ratio(protected_kept, protected_total),
            "automatic_violation_rate": ratio(len(violation_ids), len(rows)),
            "automatic_violation_ids": violation_ids,
        }
        if mode == "enhanced":
            summary["fallback_count"] = providers.get("local-conservative-rules", 0)
            summary["model_used_count"] = len(rows) - summary["fallback_count"]
            summary["fallback_reasons"] = dict(sorted(Counter(
                row["enhanced"]["degradation_reason"] for row in rows
                if row["enhanced"]["degraded"]
            ).items()))
            summary["changed_from_basic_samples"] = sum(
                row["enhanced"]["text"] != row["basic"]["text"] for row in rows
            )
        return summary

    modes = {"basic": summarize_mode("basic")}
    if enhanced:
        modes["enhanced"] = summarize_mode("enhanced")
    return {
        "schema_version": 1,
        "timing_scope": "in_process_product_api_request",
        "runtime": runtime,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "sample_count": len(rows),
        "modes": modes,
        "samples": rows,
        "limitations": [
            "Raw text is the fixture input, not measured ASR output.",
            "Timing covers the in-process product API request, not recording or desktop paste.",
            "Annotated lexical checks do not establish semantic faithfulness.",
            "Enhanced fallback is counted separately and is not a successful LLM result.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enhanced", action="store_true", help="Also measure the optional LLM path and its fallback")
    parser.add_argument("--prewarm-enhanced", action="store_true", help="Prepare the optional model before timing; records warmup separately")
    arguments = parser.parse_args()
    report = measure(arguments.manifest, arguments.enhanced, arguments.prewarm_enhanced)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Measured {report['sample_count']} basic-cleanup inputs; report: {arguments.output}")


if __name__ == "__main__":
    main()
