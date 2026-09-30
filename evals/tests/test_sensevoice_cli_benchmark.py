import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("benchmark_sensevoice_cli", SCRIPTS / "benchmark_sensevoice_cli.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class SenseVoiceCliBenchmarkTests(unittest.TestCase):
    def test_scores_exact_audio_and_records_process_latency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "sample.wav"
            model = root / "model.gguf"
            executable = root / "cli.exe"
            audio.write_bytes(b"audio")
            model.write_bytes(b"model")
            executable.write_bytes(b"binary")
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"id": "one", "audio_path": str(audio),
                                            "reference": "你好", "speaker": "speaker-a"}, ensure_ascii=False), encoding="utf-8")
            with patch.object(benchmark.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "你好。"
                run.return_value.stderr = ""
                report = benchmark.measure(manifest, executable, model)
            self.assertEqual(report["summary"]["raw_asr_cer"], 0)
            self.assertEqual(report["samples"][0]["audio_sha256"], benchmark.hashlib.sha256(b"audio").hexdigest())
            self.assertEqual(report["runtime"]["backend"], "cpu")
            self.assertEqual(run.call_args.args[0][-1], "cpu")

    def test_nonzero_exit_is_not_scored_as_empty_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("sample.wav", "model.gguf", "cli.exe"):
                (root / name).write_bytes(b"x")
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"id": "one", "audio_path": str(root / "sample.wav"),
                                            "reference": "你好"}, ensure_ascii=False), encoding="utf-8")
            with patch.object(benchmark.subprocess, "run") as run:
                run.return_value.returncode = 1
                run.return_value.stdout = ""
                run.return_value.stderr = "failed"
                with self.assertRaisesRegex(RuntimeError, "one"):
                    benchmark.measure(manifest, root / "cli.exe", root / "model.gguf")


if __name__ == "__main__":
    unittest.main()
