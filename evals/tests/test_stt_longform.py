from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "local-api"
sys.path.insert(0, str(API_ROOT))
from app.stt_service import LocalFasterWhisperProvider  # noqa: E402


class FakeModel:
    def __init__(self) -> None:
        self.calls = []

    def transcribe(self, path: str, **kwargs):
        self.calls.append((path, kwargs))
        return [SimpleNamespace(start=0.0, end=1.0, text="你好")], SimpleNamespace(language="zh", duration=1.0)


class LongformTimestampTests(unittest.TestCase):
    def test_short_audio_keeps_fast_no_timestamp_mode(self) -> None:
        provider = LocalFasterWhisperProvider()
        provider._audio_duration_seconds = lambda _: 5.0
        model = FakeModel()
        provider._transcribe_audio(model, Path("short.wav"), "zh")
        self.assertTrue(model.calls[0][1]["without_timestamps"])

    def test_30_to_90_second_audio_uses_timestamps(self) -> None:
        provider = LocalFasterWhisperProvider()
        provider._audio_duration_seconds = lambda _: 45.0
        model = FakeModel()
        provider._transcribe_audio(model, Path("middle.wav"), "zh")
        self.assertFalse(model.calls[0][1]["without_timestamps"])

    def test_chunks_all_use_timestamps(self) -> None:
        provider = LocalFasterWhisperProvider()
        provider._audio_duration_seconds = lambda _: 100.0
        provider._write_wav_chunks = lambda *_: [(0.0, Path("first.wav")), (90.0, Path("second.wav"))]
        model = FakeModel()
        provider._transcribe_audio(model, Path("long.wav"), "zh")
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(all(call[1]["without_timestamps"] is False for call in model.calls))


if __name__ == "__main__":
    unittest.main()
