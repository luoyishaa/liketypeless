from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compare_baseline import compare  # noqa: E402
from evaluate import edit_distance, evaluate, normalize, normalize_protected, read_jsonl  # noqa: E402
from make_manifest import aishell, common_voice, fleurs, wenetspeech  # noqa: E402
from make_aishell4_manifest import read_textgrid  # noqa: E402
from make_translation_manifest import make_manifest as make_translation_manifest  # noqa: E402
from merge_reviews import merge  # noqa: E402


class EvaluationTests(unittest.TestCase):
    def test_cer_and_safety_redline(self) -> None:
        manifest = {"a": {"id": "a", "source": "test", "reference": "你好世界", "duration_seconds": 2,
                          "input_text": "不要删掉明天", "protected_terms": ["明天"], "forbidden_phrases": ["今天"]}}
        correct = {"a": {"id": "a", "asr_text": "你好，世杰。", "stt_ms": 500, "end_to_end_ms": 600,
                         "structured_text": "不要删掉明天。"}}
        candidate = {"a": {**correct["a"], "structured_text": "删掉今天。"}}
        before = evaluate(manifest, correct)
        after = evaluate(manifest, candidate)
        self.assertEqual(before["overall"]["asr"]["cer"], 0.25)
        self.assertEqual(before["overall"]["asr_real_time_factor"], 0.25)
        self.assertEqual(after["safety"]["automatic_violation_rate"], 1)
        self.assertTrue(compare(before, after)[1])

    def test_missing_prediction_fails_instead_of_improving_score(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            evaluate({"a": {"id": "a", "reference": "你好"}}, {})

    def test_normalization_keeps_digits_and_latin_letters(self) -> None:
        self.assertEqual(normalize("API 20 秒。"), "api20秒")
        self.assertEqual(normalize("甲·乙，丙！"), "甲乙丙")
        self.assertNotEqual(normalize_protected("3.14"), normalize_protected("314"))
        self.assertEqual(edit_distance("abcd", "abxd"), 1)

    def test_invalid_or_missing_latency_fails(self) -> None:
        sample = {"a": {"id": "a", "reference": "你好"}}
        with self.assertRaisesRegex(ValueError, "stt_ms"):
            evaluate(sample, {"a": {"id": "a", "asr_text": "你好", "end_to_end_ms": 1}})
        with self.assertRaisesRegex(ValueError, "end_to_end_ms"):
            evaluate(sample, {"a": {"id": "a", "asr_text": "你好", "stt_ms": 1}})

    def test_manifest_hash_ignores_machine_local_audio_path(self) -> None:
        sample = {"id": "a", "reference": "你好", "audio_path": "D:/one.wav", "source_audio_sha256": "abc"}
        output = {"a": {"id": "a", "asr_text": "你好", "stt_ms": 1, "end_to_end_ms": 2}}
        first = evaluate({"a": sample}, output)
        second = evaluate({"a": {**sample, "audio_path": "/tmp/one.wav"}}, output)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_aishell_import_uses_test_split(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data_aishell"
            (root / "transcript").mkdir(parents=True)
            speaker = root / "wav" / "test" / "S0001"
            speaker.mkdir(parents=True)
            (root / "transcript" / "aishell_transcript_v0.8.txt").write_text("S0001_TEST 你 好\n", encoding="utf-8")
            (speaker / "S0001_TEST.wav").touch()
            rows = aishell(Path(temporary), 1)
            self.assertEqual(rows[0]["reference"], "你好")
            self.assertEqual(rows[0]["split"], "test")

    def test_common_voice_import_uses_test_tsv_and_speaker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "clips").mkdir()
            (root / "clips" / "a.mp3").touch()
            (root / "test.tsv").write_text("client_id\tpath\tsentence\nuser\ta.mp3\t你好\n", encoding="utf-8")
            rows = common_voice(root, 1)
            self.assertEqual(rows[0]["speaker"], "user")
            self.assertEqual(rows[0]["reference"], "你好")

    def test_wenetspeech_import_preserves_segment_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for split in ("net", "meeting"):
                audio = root / "audio" / split / "a.opus"
                audio.parent.mkdir(parents=True)
                audio.touch()
            data = {"audios": [
                {"aid": "net", "path": "audio/net/a.opus", "segments": [{"sid": "n1", "begin_time": 1, "end_time": 3, "text": "网络", "subsets": ["TEST_NET"]}]},
                {"aid": "meeting", "path": "audio/meeting/a.opus", "segments": [{"sid": "m1", "begin_time": 4, "end_time": 6, "text": "会议", "subsets": ["TEST_MEETING"]}]},
            ]}
            (root / "WenetSpeech.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            rows = wenetspeech(root, 1, 1)
            self.assertEqual({row["start_seconds"] for row in rows}, {1.0, 4.0})

    def test_fleurs_imports_headerless_test_tsv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test").mkdir()
            (root / "test" / "a.wav").touch()
            (root / "test.tsv").write_text("speaker\ta.wav\t你好。\t你好\n", encoding="utf-8")
            rows = fleurs(root, 1)
            self.assertEqual(rows[0]["reference"], "你好。")
            self.assertEqual(rows[0]["speaker"], "speaker")

    def test_aishell4_textgrid_ignores_silence_markup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            grid = Path(temporary) / "meeting.TextGrid"
            grid.write_text('name = "speaker-a"\nintervals [1]:\n xmin = 0\n xmax = 3\n text = "呃<sil>你好"\n'
                            'intervals [2]:\n xmin = 3\n xmax = 4\n text = "<%>"\n', encoding="utf-8")
            self.assertEqual(read_textgrid(grid), [("speaker-a", 0.0, 3.0, "呃你好")])

    def test_flores_pairing_and_review_adjudication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "devtest"
            root.mkdir()
            (root / "zho_Hans.devtest").write_text("你好\n", encoding="utf-8")
            (root / "eng_Latn.devtest").write_text("Hello\n", encoding="utf-8")
            sample = make_translation_manifest(root.parent, 1)[0]
            self.assertEqual(sample["translation_reference"], "Hello")
            predictions = {sample["id"]: {"id": sample["id"], "translation": "Hi", "end_to_end_ms": 5}}
            reviews = [
                {"id": sample["id"], "reviewer": "alice", "translation_faithfulness_1_to_5": "4", "translation_naturalness_1_to_5": "5"},
                {"id": sample["id"], "reviewer": "bob", "translation_faithfulness_1_to_5": "2", "translation_naturalness_1_to_5": "3"},
            ]
            merged = merge(predictions, reviews)
            self.assertEqual(merged[sample["id"]]["human_review"]["translation_faithfulness_1_to_5"], 3)
            self.assertEqual(evaluate({sample["id"]: sample}, merged)["translation"]["human_reviewed"], 1)

    def test_structure_review_disagreement_needs_adjudication(self) -> None:
        predictions = {"a": {"id": "a", "structured_text": "你好"}}
        common = {"id": "a", "meaning_preserved": "yes", "deleted_meaningful_content": "no",
                  "added_information": "no", "protected_terms_preserved": "yes", "punctuation_appropriate": "yes"}
        reviews = [{**common, "reviewer": "alice"}, {**common, "reviewer": "bob", "meaning_preserved": "no"}]
        with self.assertRaisesRegex(ValueError, "adjudicator"):
            merge(predictions, reviews)
        merged = merge(predictions, [*reviews, {**common, "reviewer": "adjudicator"}])
        self.assertTrue(merged["a"]["human_review"]["adjudicated"])

    def test_duplicate_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicates.jsonl"
            path.write_text('{"id":"same"}\n{"id":"same"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_jsonl(path)


if __name__ == "__main__":
    unittest.main()
