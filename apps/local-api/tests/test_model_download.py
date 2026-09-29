"""Exercise interrupted and resumed model downloads without a 486 MB test fixture."""
import hashlib
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import model_manager


class Response(io.BytesIO):
    def __init__(self, data: bytes, status: int, interrupt: bool = False, content_range: str = ""):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Range": content_range}
        self.interrupt = interrupt
        self.reads = 0

    def read(self, size=-1):
        if self.interrupt and self.reads:
            raise ConnectionResetError("download interrupted")
        self.reads += 1
        return super().read(300 if self.interrupt else size)


def terminal(manager):
    for _ in range(200):
        state = manager.status()
        if state["state"] in ("ready", "error"):
            return state
        time.sleep(0.01)
    raise AssertionError("Model preparation did not finish")


class ModelDownloadTests(unittest.TestCase):
    def test_interrupted_official_download_resumes_and_verifies(self):
        data = b"pinned-model-data" * 200
        spec = {"model.bin": (len(data), "sha256", hashlib.sha256(data).hexdigest())}
        calls = []
        online = False

        def open_response(request, timeout):
            self.assertEqual(timeout, 30)
            self.assertTrue(request.full_url.startswith("https://huggingface.co/"))
            offset = int(request.headers.get("Range", "bytes=0-")[6:-1])
            calls.append(offset)
            if len(calls) > 1 and not online:
                raise ConnectionResetError("offline")
            return Response(data[offset:], 206 if offset else 200, interrupt=len(calls) == 1,
                            content_range=f"bytes {offset}-{len(data)-1}/{len(data)}" if offset else "")

        with tempfile.TemporaryDirectory() as directory, patch.dict(model_manager.FILES, spec, clear=True), patch.object(model_manager.urllib.request, "urlopen", side_effect=open_response):
            manager = model_manager.ModelManager(Path(directory))
            manager.prepare()
            self.assertEqual(terminal(manager)["state"], "error")
            self.assertEqual((Path(directory) / "model.bin.part").stat().st_size, 300)
            online = True
            manager.prepare()
            self.assertEqual(terminal(manager)["state"], "ready")
            self.assertEqual(calls[0], 0)
            self.assertEqual(calls[-1], 300)
            self.assertEqual((Path(directory) / "model.bin").read_bytes(), data)

    def test_short_success_response_resumes_automatically(self):
        data = b"complete-model" * 200
        spec = {"model.bin": (len(data), "sha256", hashlib.sha256(data).hexdigest())}
        calls = []

        def open_response(request, timeout):
            offset = int(request.headers.get("Range", "bytes=0-")[6:-1])
            calls.append(offset)
            return Response(data[:300] if offset == 0 else data[offset:], 206 if offset else 200,
                            content_range=f"bytes {offset}-{len(data)-1}/{len(data)}" if offset else "")

        with tempfile.TemporaryDirectory() as directory, patch.dict(model_manager.FILES, spec, clear=True), patch.object(model_manager.urllib.request, "urlopen", side_effect=open_response):
            manager = model_manager.ModelManager(Path(directory))
            manager.prepare()
            self.assertEqual(terminal(manager)["state"], "ready")
            self.assertEqual(calls, [0, 300])
            self.assertEqual((Path(directory) / "model.bin").read_bytes(), data)
            self.assertFalse((Path(directory) / "model.bin.part").exists())

    def test_ignored_range_restarts_without_duplicate_bytes(self):
        data = b"valid" * 500
        spec = {"model.bin": (len(data), "sha256", hashlib.sha256(data).hexdigest())}
        with tempfile.TemporaryDirectory() as directory, patch.dict(model_manager.FILES, spec, clear=True):
            (Path(directory) / "model.bin.part").write_bytes(data[:300])
            with patch.object(model_manager.urllib.request, "urlopen", return_value=Response(data, 200)):
                manager = model_manager.ModelManager(Path(directory))
                manager.prepare()
                self.assertEqual(terminal(manager)["state"], "ready")
            self.assertEqual((Path(directory) / "model.bin").read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
