"""Holdout selection must not reuse a baseline speaker or audio recording."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_holdout import select_holdout  # noqa: E402


class HoldoutTests(unittest.TestCase):
    def test_excludes_baseline_speakers_and_duplicate_audio(self):
        baseline = [{"id": "old", "source": "corpus", "speaker": "alice",
                     "source_audio_sha256": "audio-old", "reference": "旧句"}]
        candidates = [
            {"id": "new-a", "source": "corpus", "speaker": "alice",
             "source_audio_sha256": "audio-a", "reference": "新句"},
            {"id": "new-b", "source": "corpus", "speaker": "bob",
             "source_audio_sha256": "audio-old", "reference": "重复"},
            {"id": "new-c", "source": "corpus", "speaker": "chen",
             "source_audio_sha256": "audio-c", "reference": "有效"},
        ]
        self.assertEqual([row["id"] for row in select_holdout(candidates, baseline, 1)], ["new-c"])

    def test_rejects_missing_provenance_instead_of_claiming_independence(self):
        incomplete = {"id": "a", "source": "corpus", "reference": "你好"}
        with self.assertRaisesRegex(ValueError, "speaker"):
            select_holdout([incomplete], [], 1)
        incomplete["speaker"] = "alice"
        with self.assertRaisesRegex(ValueError, "source_audio_sha256"):
            select_holdout([incomplete], [], 1)

    def test_cli_freezes_portable_manifest_and_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.jsonl"
            baseline = root / "baseline.jsonl"
            output = root / "holdout.jsonl"
            lock = root / "holdout.lock.json"
            candidate.write_text(json.dumps({"id": "a", "source": "aishell-1", "split": "train",
                                             "speaker": "S0002", "reference": "你好世界",
                                             "source_audio_sha256": "audio-a", "audio_path": "C:/temporary.wav"},
                                            ensure_ascii=False) + "\n", encoding="utf-8")
            baseline.write_text(json.dumps({"id": "b", "source": "aishell-1", "split": "test",
                                            "speaker": "S0764", "reference": "旧句",
                                            "source_audio_sha256": "audio-b"}, ensure_ascii=False) + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "build_holdout.py"),
                                     "--candidate", str(candidate), "--exclude", str(baseline), "--count", "1",
                                     "--output", str(output), "--lock", str(lock),
                                     "--source-revision", "bbe295d530192a4cd41644b711c9aecd087df653"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads(lock.read_text(encoding="utf-8"))
            self.assertEqual(metadata["sample_count"], 1)
            self.assertEqual(metadata["source_revision"], "bbe295d530192a4cd41644b711c9aecd087df653")
            self.assertEqual(len(metadata["manifest_sha256"]), 64)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["speaker"], "S0002")

    def test_cli_can_exclude_a_smoke_inspected_recording_without_excluding_its_speaker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.jsonl"
            rows = [{"id": identifier, "source": "aishell-1", "split": "train", "speaker": "S0012",
                     "reference": "你好", "source_audio_sha256": identifier, "audio_path": f"C:/{identifier}.wav"}
                    for identifier in ("a", "b")]
            candidate.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            output, lock = root / "holdout.jsonl", root / "holdout.lock.json"
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "build_holdout.py"),
                                     "--candidate", str(candidate), "--exclude-id", "a", "--count", "1",
                                     "--output", str(output), "--lock", str(lock), "--source-revision", "revision"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["id"], "b")
            self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["excluded_ids"], ["a"])


if __name__ == "__main__":
    unittest.main()
