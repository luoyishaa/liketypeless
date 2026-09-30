import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("benchmark_packaged_asr", SCRIPTS / "benchmark_packaged_asr.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class PackagedAsrBenchmarkTests(unittest.TestCase):
    def test_fixed_audio_uses_real_backend_contract_and_records_actual_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "one.wav"
            audio.write_bytes(b"audio")
            (root / "backend.exe").write_bytes(b"backend")
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"id": "one", "audio_path": str(audio), "reference": "你好",
                                            "prepared_audio_sha256": benchmark.hashlib.sha256(b"audio").hexdigest()},
                                           ensure_ascii=False), encoding="utf-8")
            with patch.object(benchmark, "launch_backend") as launch, patch.object(benchmark, "request_json") as request:
                launch.return_value.__enter__.return_value = ("http://127.0.0.1:12345", "token")
                request.side_effect = [
                    {"status": "ok", "modelReady": True, "runtime": {"device": "cuda"}},
                    {"provider": "local-sensevoice-gguf", "model": "q8", "text": "你好。",
                     "sttElapsedMs": 900, "sttFallbackReason": None},
                ]
                report = benchmark.measure(manifest, root / "backend.exe", root / "small", root / "bundle")
            self.assertEqual(report["summary"]["raw_asr_cer"], 0)
            self.assertEqual(report["samples"][0]["provider"], "local-sensevoice-gguf")
            self.assertEqual(request.call_args.args[2]["provider"], "local-routed")
            self.assertEqual(report["timing_scope"], "packaged_backend_http_stt_route")

    def test_packaged_whisper_baseline_uses_same_http_route_without_short_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend.exe").write_bytes(b"backend")
            audio = root / "one.wav"
            audio.write_bytes(b"audio")
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"id": "one", "audio_path": str(audio), "reference": "你好"},
                                           ensure_ascii=False), encoding="utf-8")
            with patch.object(benchmark, "launch_backend") as launch, patch.object(benchmark, "request_json") as request:
                launch.return_value.__enter__.return_value = ("http://127.0.0.1:12345", "token")
                request.side_effect = [{"modelReady": True, "runtime": {}},
                                       {"provider": "local-faster-whisper", "model": "small", "text": "你好",
                                        "sttElapsedMs": 100, "sttFallbackReason": None}]
                report = benchmark.measure(manifest, root / "backend.exe", root / "small", None,
                                           provider="local-faster-whisper")
            self.assertEqual(request.call_args.args[2]["provider"], "local-faster-whisper")
            self.assertEqual(report["runtime"]["requested_provider"], "local-faster-whisper")


if __name__ == "__main__":
    unittest.main()
