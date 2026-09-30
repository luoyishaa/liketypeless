import hashlib
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from threading import Thread
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.sensevoice_bundle import SenseVoiceBundle


class SenseVoiceBundleTests(unittest.TestCase):
    def test_startup_removes_only_expired_staged_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_clip = root / "clip-old.wav"
            new_clip = root / "clip-new.wav"
            unrelated = root / "recording.wav"
            for path in (old_clip, new_clip, unrelated):
                path.write_bytes(b"audio")
            old_time = time.time() - 25 * 3600
            os.utime(old_clip, (old_time, old_time))
            os.utime(unrelated, (old_time, old_time))
            SenseVoiceBundle(root)
            self.assertFalse(old_clip.exists())
            self.assertTrue(new_clip.exists())
            self.assertTrue(unrelated.exists())

    def test_import_verifies_both_artifacts_and_rejects_wrong_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            model = b"gguf-model"
            executable = b"portable-cli"
            (source / "sensevoice-small-q8.gguf").write_bytes(model)
            (source / "llama-funasr-sensevoice.exe").write_bytes(executable)
            bundle = SenseVoiceBundle(root / "installed", model_spec=(len(model), hashlib.sha256(model).hexdigest()),
                                      exe_sha256=hashlib.sha256(executable).hexdigest())
            bundle.prepare(source=source)
            self._wait(bundle)
            self.assertEqual(bundle.status()["state"], "ready")
            self.assertTrue(bundle.paths()[0].is_file())
            (source / "sensevoice-small-q8.gguf").write_bytes(b"wrong")
            second = SenseVoiceBundle(root / "different", model_spec=(len(model), hashlib.sha256(model).hexdigest()),
                                      exe_sha256=hashlib.sha256(executable).hexdigest())
            second.prepare(source=source)
            self._wait(second)
            self.assertEqual(second.status()["state"], "error")

    def test_zip_extraction_uses_only_pinned_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = b"portable-cli"
            archive = BytesIO()
            with ZipFile(archive, "w") as output:
                output.writestr("llama-funasr-sensevoice.exe", executable)
                output.writestr("../unsafe.txt", b"do not extract")
            bundle = SenseVoiceBundle(root, model_spec=(1, hashlib.sha256(b"x").hexdigest()),
                                      archive_spec=(len(archive.getvalue()), hashlib.sha256(archive.getvalue()).hexdigest()),
                                      exe_sha256=hashlib.sha256(executable).hexdigest())
            (root / "runtime.zip").write_bytes(archive.getvalue())
            bundle._extract_runtime()
            self.assertEqual((root / "llama-funasr-sensevoice.exe").read_bytes(), executable)
            self.assertFalse((root.parent / "unsafe.txt").exists())

    def test_download_resumes_with_checked_byte_range(self):
        payload = b"verified-model"

        class ResumeServer(BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.range_header = self.headers.get("Range")
                self.send_response(206)
                self.send_header("Content-Range", f"bytes 4-{len(payload)-1}/{len(payload)}")
                self.end_headers()
                self.wfile.write(payload[4:])

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ResumeServer)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                partial = root / "model.part"
                partial.write_bytes(payload[:4])
                bundle = SenseVoiceBundle(root)
                bundle._download(f"http://127.0.0.1:{server.server_port}/model", partial,
                                 (len(payload), hashlib.sha256(payload).hexdigest()), 0)
                self.assertEqual(server.range_header, "bytes=4-")
                self.assertEqual(partial.read_bytes(), payload)
        finally:
            server.shutdown()
            server.server_close()

    @staticmethod
    def _wait(bundle):
        for _ in range(100):
            if bundle.status()["state"] not in {"downloading", "verifying"}:
                return
            time.sleep(0.01)
        raise AssertionError("bundle did not finish")


if __name__ == "__main__":
    unittest.main()
