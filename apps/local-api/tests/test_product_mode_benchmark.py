"""Black-box checks for the product text-mode benchmark CLI."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "evals" / "scripts" / "benchmark_cleanup_modes.py"


class ProductModeBenchmarkTests(unittest.TestCase):
    def test_basic_mode_measures_product_api_without_calling_it_raw_asr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({
                "id": "case-1",
                "input_text": "明天下午三点开会",
                "protected_terms": ["明天下午三点"],
                "forbidden_phrases": ["今天"],
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            output = root / "report.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--manifest", str(manifest),
                 "--output", str(output)],
                cwd=ROOT, text=True, capture_output=True,
                env={**os.environ, "LIKETYPELESS_OLLAMA_BASE_URL": "http://127.0.0.1:1"},
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["sample_count"], 1)
            self.assertEqual(report["timing_scope"], "in_process_product_api_request")
            self.assertEqual(report["runtime"]["model_start_state"], "not_measured")
            self.assertEqual(report["runtime"]["warmup_policy"], "none")
            self.assertTrue(report["runtime"]["python_version"])
            self.assertEqual(report["samples"][0]["raw_text"], "明天下午三点开会")
            self.assertEqual(report["samples"][0]["basic"]["text"], "明天下午三点开会。")
            self.assertEqual(report["modes"]["basic"]["provider_counts"], {"local-conservative-rules": 1})
            self.assertEqual(report["modes"]["basic"]["protected_term_recall"], 1.0)
            self.assertEqual(report["modes"]["basic"]["automatic_violation_rate"], 0.0)
            self.assertGreaterEqual(report["samples"][0]["basic"]["elapsed_ms"], 0)

    def test_enhanced_mode_records_offline_fallback_as_fallback_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({
                "id": "case-1", "input_text": "明天开会",
                "protected_terms": ["明天"], "forbidden_phrases": ["今天"],
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            output = root / "report.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--manifest", str(manifest),
                 "--output", str(output), "--enhanced"],
                cwd=ROOT, text=True, capture_output=True,
                env={**os.environ, "LIKETYPELESS_OLLAMA_BASE_URL": "http://127.0.0.1:1"},
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["runtime"]["model_start_state"], "ollama_unavailable")
            self.assertEqual(report["runtime"]["ollama_model"], "qwen3:8b")
            self.assertEqual(report["modes"]["enhanced"]["fallback_count"], 1)
            self.assertEqual(report["modes"]["enhanced"]["model_used_count"], 0)
            self.assertEqual(report["samples"][0]["enhanced"]["provider"], "local-conservative-rules")
            self.assertEqual(report["samples"][0]["enhanced"]["text"], report["samples"][0]["basic"]["text"])
            self.assertTrue(report["samples"][0]["enhanced"]["degraded"])
            self.assertTrue(report["samples"][0]["enhanced"]["degradation_reason"])
            self.assertEqual(sum(report["modes"]["enhanced"]["fallback_reasons"].values()), 1)

    def test_explicit_prewarm_is_separated_from_measured_requests(self):
        class OllamaFixture(BaseHTTPRequestHandler):
            def do_POST(self):
                body = (b'{"model":"qwen3:8b","done":true}' if self.path == "/api/generate"
                        else '{"message":{"content":"明天开会。"}}'.encode("utf-8"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaFixture)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = root / "manifest.jsonl"
                manifest.write_text(json.dumps({"id": "case-1", "input_text": "明天开会"}, ensure_ascii=False) + "\n", encoding="utf-8")
                output = root / "report.json"
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--output", str(output),
                     "--enhanced", "--prewarm-enhanced"], cwd=ROOT, text=True, capture_output=True,
                    env={**os.environ, "LIKETYPELESS_OLLAMA_BASE_URL": f"http://127.0.0.1:{server.server_port}"},
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(report["runtime"]["warmup_policy"], "explicit_optional_prepare")
                self.assertEqual(report["modes"]["enhanced"]["model_used_count"], 1)
                self.assertFalse(report["samples"][0]["enhanced"]["degraded"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
