import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from time import perf_counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_data = tempfile.TemporaryDirectory()
os.environ["LIKETYPELESS_DATA_DIR"] = _data.name
os.environ["LIKETYPELESS_SESSION_TOKEN"] = "test-session-token"
os.environ["LIKETYPELESS_OLLAMA_BASE_URL"] = "http://127.0.0.1:1"

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.stt_service import sensevoice_bundle


class ProductApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, headers={"Authorization": "Bearer test-session-token"})

    def test_basic_cleanup_works_without_ollama(self):
        started = perf_counter()
        response = self.client.post("/llm/structure", json={"text": "明天开会", "cleanupMode": "basic"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["structuredText"], "明天开会。")
        self.assertEqual(response.json()["model"], "local-conservative-rules")
        self.assertFalse(response.json()["degraded"])
        self.assertIsNone(response.json()["degradationReason"])
        self.assertLess(perf_counter() - started, 0.5)

    def test_enhanced_cold_model_returns_saved_basic_text_without_waiting_for_load(self):
        class SlowOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(1.2)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"message":{"content":"loaded"}}')

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowOllama)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.object(settings, "ollama_base_url", f"http://127.0.0.1:{server.server_port}"):
                started = perf_counter()
                response = self.client.post("/llm/structure", json={"text": "明天开会", "cleanupMode": "enhanced"})
                elapsed = perf_counter() - started
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["structuredText"], "明天开会。")
            self.assertTrue(response.json()["degraded"])
            self.assertIn("准备", response.json()["degradationReason"])
            self.assertLess(elapsed, 0.5)
        finally:
            server.shutdown()
            server.server_close()

    def test_explicit_prepare_makes_optional_cleanup_available(self):
        class ReadyOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                body = b'{"model":"qwen3:8b","done":true}' if self.path == "/api/generate" else (
                    '{"message":{"content":"明天开会。"}}'.encode("utf-8"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ReadyOllama)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.object(settings, "ollama_base_url", f"http://127.0.0.1:{server.server_port}"):
                self.assertEqual(self.client.post("/llm/prepare").status_code, 200)
                for _ in range(100):
                    status = self.client.get("/llm/status").json()
                    if status["state"] == "ready":
                        break
                    time.sleep(0.01)
                self.assertEqual(status["state"], "ready")
                response = self.client.post("/llm/structure", json={"text": "明天开会", "cleanupMode": "enhanced"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["model"].startswith("hybrid-conservative-llm:"))
            self.assertFalse(response.json()["degraded"])
        finally:
            server.shutdown()
            server.server_close()

    def test_ready_model_that_stalls_falls_back_with_bounded_wait(self):
        class StallingOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path == "/api/chat":
                    time.sleep(3)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    self.wfile.write(b'{"model":"qwen3:8b","done":true}')
                except (BrokenPipeError, ConnectionAbortedError):
                    pass

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), StallingOllama)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.object(settings, "ollama_base_url", f"http://127.0.0.1:{server.server_port}"):
                self.client.post("/llm/prepare")
                for _ in range(100):
                    if self.client.get("/llm/status").json()["state"] == "ready":
                        break
                    time.sleep(0.01)
                started = perf_counter()
                response = self.client.post("/llm/structure", json={"text": "明天开会", "cleanupMode": "enhanced"})
                elapsed = perf_counter() - started
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["model"], "local-conservative-rules")
            self.assertIn("超时", response.json()["degradationReason"])
            self.assertLess(elapsed, 2.7)
        finally:
            server.shutdown()
            server.server_close()

    def test_enhanced_formatting_cannot_change_date_or_name(self):
        class UnsafeOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                body = (b'{"model":"qwen3:8b","done":true}' if self.path == "/api/generate"
                        else json.dumps({"message": {"content": "今天下午三点给王老师发邮件。"}},
                                        ensure_ascii=False).encode("utf-8"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), UnsafeOllama)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.object(settings, "ollama_base_url", f"http://127.0.0.1:{server.server_port}"):
                self.client.post("/llm/prepare")
                for _ in range(100):
                    if self.client.get("/llm/status").json()["state"] == "ready":
                        break
                    time.sleep(0.01)
                response = self.client.post("/llm/structure", json={"text": "明天下午三点给李老师发邮件", "cleanupMode": "enhanced"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["model"], "local-conservative-rules")
            self.assertEqual(response.json()["structuredText"], "明天下午三点给李老师发邮件。")
            self.assertIn("改变了原文", response.json()["degradationReason"])
        finally:
            server.shutdown()
            server.server_close()

    def test_api_rejects_missing_session_credential(self):
        self.assertEqual(TestClient(app).get("/audio/recording/status").status_code, 401)

    def test_health_distinguishes_missing_model_from_service_failure(self):
        result = self.client.get("/health").json()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["modelReady"])
        self.assertIn(result["enhancedModelState"], {"unavailable", "loading", "ready"})

    def test_optional_short_model_has_separate_status_and_prepare_route(self):
        with patch.object(sensevoice_bundle, "prepare") as prepare:
            response = self.client.post("/models/short/prepare", json={})
        self.assertEqual(response.status_code, 200)
        prepare.assert_called_once_with(None)
        self.assertIn(self.client.get("/models/short/status").json()["state"],
                      {"missing", "downloading", "verifying", "ready", "error"})

    def test_invalid_model_import_never_reports_ready(self):
        response = self.client.post("/models/prepare", json={"sourcePath": _data.name})
        self.assertEqual(response.status_code, 200)
        for _ in range(100):
            status = self.client.get("/models/status").json()
            if status["state"] == "error": break
            time.sleep(0.01)
        self.assertEqual(status["state"], "error")
        self.assertFalse(self.client.get("/health").json()["modelReady"])

    def test_unprepared_model_cannot_start_recording(self):
        self.assertEqual(self.client.post("/audio/recording/start", json={}).status_code, 409)

    def test_disabled_translation_mode_is_not_accepted_by_voice_input(self):
        self.assertEqual(self.client.post("/voice/recording/finish", json={"outputMode": "zh-to-en"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
