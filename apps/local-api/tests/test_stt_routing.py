from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.stt_service import RoutedSpeechProvider, TranscriptionResult


class FakeWhisper:
    def __init__(self):
        self.calls = 0

    def transcribe(self, path, language=None):
        self.calls += 1
        return TranscriptionResult(provider="local-faster-whisper", model="small", text="原文", language="zh",
                                   duration_seconds=0, elapsed_ms=12, segments=[])


class FakeBundle:
    def __init__(self, ready=True, directory=None):
        self.ready = ready
        self.directory = directory or Path(".")

    def status(self):
        return {"state": "ready" if self.ready else "missing"}

    def paths(self):
        return self.directory / "model.gguf", self.directory / "cli.exe"


class RoutedSpeechTests(unittest.TestCase):
    @staticmethod
    def audio(root: Path, seconds: int) -> Path:
        path = root / "sample.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\0\0" * (16000 * seconds))
        return path

    def test_short_audio_uses_portable_candidate_and_reports_actual_provider(self):
        with tempfile.TemporaryDirectory(prefix="中文 路径 ") as directory:
            whisper = FakeWhisper()
            model_dir = Path(directory) / "模型 目录"
            model_dir.mkdir()
            provider = RoutedSpeechProvider(whisper, FakeBundle(directory=model_dir))
            with patch("app.stt_service.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "你好。\n"
                result = provider.transcribe(self.audio(Path(directory), 2))
            self.assertEqual(result.provider, "local-sensevoice-gguf")
            self.assertEqual(result.text, "你好。")
            self.assertIsNone(result.fallback_reason)
            self.assertEqual(whisper.calls, 0)
            self.assertIn("--backend", run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["cwd"], str(model_dir))
            self.assertEqual(run.call_args.args[0][2], "model.gguf")
            staged_name = run.call_args.args[0][4]
            self.assertTrue(staged_name.endswith(".wav"))
            self.assertTrue(staged_name.isascii())
            self.assertFalse((model_dir / staged_name).exists())

    def test_missing_candidate_and_cli_failure_both_fall_back_to_whisper(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = self.audio(Path(directory), 2)
            whisper = FakeWhisper()
            missing = RoutedSpeechProvider(whisper, FakeBundle(False)).transcribe(audio)
            self.assertEqual(missing.provider, "local-faster-whisper")
            self.assertIn("未准备", missing.fallback_reason)
            with patch("app.stt_service.subprocess.run") as run:
                run.return_value.returncode = 1
                run.return_value.stderr = "failed"
                failed = RoutedSpeechProvider(whisper, FakeBundle()).transcribe(audio)
            self.assertEqual(failed.provider, "local-faster-whisper")
            self.assertIn("失败", failed.fallback_reason)

    def test_long_audio_keeps_whisper_without_starting_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            whisper = FakeWhisper()
            with patch("app.stt_service.subprocess.run") as run:
                result = RoutedSpeechProvider(whisper, FakeBundle()).transcribe(self.audio(Path(directory), 5))
            self.assertEqual(result.provider, "local-faster-whisper")
            self.assertIsNone(result.fallback_reason)
            run.assert_not_called()

    def test_non_16khz_microphone_wav_is_normalized_for_candidate(self):
        with tempfile.TemporaryDirectory(prefix="麦克风 路径 ") as directory:
            root = Path(directory)
            model_dir = root / "模型 目录"
            model_dir.mkdir()
            audio = root / "other-rate.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(b"\0\0" * 44100)
            with patch("app.stt_service.subprocess.run") as run:
                def inspect(command, **kwargs):
                    info = sf.info(str(Path(kwargs["cwd"]) / command[4]))
                    self.assertEqual(info.samplerate, 16000)
                    self.assertEqual(info.channels, 1)
                    self.assertEqual(info.subtype, "PCM_16")
                    return type("Result", (), {"returncode": 0, "stdout": "你好。"})()
                run.side_effect = inspect
                result = RoutedSpeechProvider(FakeWhisper(), FakeBundle(directory=model_dir)).transcribe(audio)
            self.assertEqual(result.provider, "local-sensevoice-gguf")
            self.assertIsNone(result.fallback_reason)


if __name__ == "__main__":
    unittest.main()
