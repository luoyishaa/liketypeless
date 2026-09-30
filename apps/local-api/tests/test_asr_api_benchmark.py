"""The ASR benchmark must exercise the same authenticated route for every audio sample."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals" / "scripts"))
sys.path.insert(0, str(ROOT / "apps" / "local-api"))


class AsrApiBenchmarkTests(unittest.TestCase):
    def test_fixed_audio_is_sent_to_product_route_and_reported_as_raw_asr(self):
        from benchmark_asr_api import measure  # noqa: E402
        from app.stt_service import TranscriptionResult  # noqa: E402

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "one.wav"
            audio.write_bytes(b"fixture")
            manifest = root / "samples.jsonl"
            manifest.write_text(json.dumps({
                "id": "one", "audio_path": str(audio), "reference": "明天开会",
            }, ensure_ascii=False) + "\n", encoding="utf-8")

            class FakeProvider:
                def __init__(self):
                    self.paths = []

                def transcribe(self, file_path, language=None):
                    self.paths.append((file_path, language))
                    return TranscriptionResult(
                        provider="fake", model="fake-model", text="明天开会", language="zh",
                        duration_seconds=1.0, elapsed_ms=11, segments=[],
                    )

            provider = FakeProvider()
            with patch("app.main.get_stt_provider", return_value=provider):
                report = measure(manifest)
            self.assertEqual(provider.paths, [(audio, "zh")])
            self.assertEqual(report["samples"][0]["asr_text"], "明天开会")
            self.assertEqual(report["samples"][0]["provider"], "fake")
            self.assertEqual(report["summary"]["raw_asr_cer"], 0.0)
            self.assertGreaterEqual(report["summary"]["request_latency_ms"]["first"], 0)
            self.assertGreaterEqual(report["summary"]["request_latency_ms"]["max"], 0)
            self.assertEqual(report["timing_scope"], "in_process_product_stt_route")
            self.assertEqual(len(report["portable_manifest_sha256"]), 64)

    def test_candidate_provider_name_is_sent_explicitly_to_product_route(self):
        from benchmark_asr_api import measure
        from app.stt_service import TranscriptionResult
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "one.wav"
            audio.write_bytes(b"fixture")
            manifest = root / "samples.jsonl"
            manifest.write_text(json.dumps({"id": "one", "audio_path": str(audio), "reference": "你好"},
                                           ensure_ascii=False) + "\n", encoding="utf-8")
            with patch("app.main.get_stt_provider") as provider:
                provider.return_value.transcribe.return_value = TranscriptionResult(
                    provider="local-sensevoice-gguf", model="q8", text="你好", language="zh",
                    duration_seconds=2, elapsed_ms=100, segments=[])
                measure(manifest, provider="local-routed")
            self.assertEqual(provider.call_args.args, ("local-routed",))


if __name__ == "__main__":
    unittest.main()
