import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_data = tempfile.TemporaryDirectory()
os.environ["LIKETYPELESS_DATA_DIR"] = _data.name
os.environ["LIKETYPELESS_SESSION_TOKEN"] = "test-session-token"
os.environ["LIKETYPELESS_OLLAMA_BASE_URL"] = "http://127.0.0.1:1"

from fastapi.testclient import TestClient
from app.main import app


class ProductApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, headers={"Authorization": "Bearer test-session-token"})

    def test_basic_cleanup_works_without_ollama(self):
        started = perf_counter()
        response = self.client.post("/llm/structure", json={"text": "明天开会", "cleanupMode": "basic"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["structuredText"], "明天开会。")
        self.assertEqual(response.json()["model"], "local-conservative-rules")
        self.assertLess(perf_counter() - started, 0.5)

    def test_api_rejects_missing_session_credential(self):
        self.assertEqual(TestClient(app).get("/audio/recording/status").status_code, 401)

    def test_health_distinguishes_missing_model_from_service_failure(self):
        result = self.client.get("/health").json()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["modelReady"])

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
