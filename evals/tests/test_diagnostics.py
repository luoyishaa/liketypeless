from __future__ import annotations
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from error_analysis import alignment_counts, analyze
from evaluate import edit_distance, evaluate, translation_violations
from compare_baseline import compare
from make_review_sheet import review_rows, write_html
from merge_reviews import merge
from compare_asr_experiments import paired_delta, compare as compare_experiments
from select_review_cases import select
from check_quality_evidence import require_comparison
from run_asr_matrix import validate_runtime
from contextlib import redirect_stdout
import io


class DiagnosticsTests(unittest.TestCase):
    def test_resume_rejects_changed_engine_runtime(self):
        with patch("run_asr_matrix.importlib.metadata.version", return_value="test"), patch("run_asr_matrix.platform.python_version", return_value="3.test"), patch.dict("os.environ", {}, clear=True):
            configuration = {"python": "3.test", "packages": {"faster-whisper": "test", "ctranslate2": "test"}, "env_overrides": {}}
            validate_runtime(configuration)
            configuration["packages"]["ctranslate2"] = "other"
            with self.assertRaisesRegex(ValueError, "runtime differs"):
                validate_runtime(configuration)

    def test_experiment_comparison_checks_every_trial_and_explicit_audio_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = {"id": "a", "reference": "你好", "source": "test", "prepared_audio_sha256": "original"}
            candidate = {**original, "prepared_audio_sha256": "channel0"}
            for name, sample in (("base", original), ("candidate", candidate)):
                folder = root / name
                folder.mkdir()
                (root / f"{name}.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
                prediction = {"id": "a", "asr_text": "你好", "stt_ms": 1, "end_to_end_ms": 1}
                report = evaluate({"a": sample}, {"a": prediction})
                for trial in (1, 2):
                    (folder / f"predictions-{trial}.jsonl").write_text(json.dumps(prediction) + "\n", encoding="utf-8")
                experiment = {"manifest_sha256": report["manifest_sha256"], "trials": [report, report],
                              "configuration": {"ordering_seed": 1, "warmup_ms": 1, "provider": "test", "device": "cpu", "packages": {}}}
                (folder / "experiment.json").write_text(json.dumps(experiment), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different manifests"):
                compare_experiments(root / "base.jsonl", root / "base", root / "candidate")
            result = compare_experiments(root / "base.jsonl", root / "base", root / "candidate", root / "candidate.jsonl")
            self.assertEqual(result["comparison_type"], "audio_preprocessing")
            (root / "candidate" / "predictions-2.jsonl").write_text(json.dumps({"id": "a", "asr_text": "坏", "stt_ms": 1, "end_to_end_ms": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do not match"):
                compare_experiments(root / "base.jsonl", root / "base", root / "candidate", root / "candidate.jsonl")

    def test_evidence_gate_rejects_missing_or_stale_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            base, candidate = Path(directory) / "base.json", Path(directory) / "candidate.json"
            with self.assertRaises(SystemExit):
                require_comparison(base, candidate, set(), "test")
            sample = {"a": {"id": "a", "reference": "你好"}}
            report = evaluate(sample, {"a": {"asr_text": "你好", "stt_ms": 1, "end_to_end_ms": 1}})
            base.write_text(json.dumps(report), encoding="utf-8")
            candidate.write_text(json.dumps(report), encoding="utf-8")
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, "rerun"):
                require_comparison(base, candidate, {candidate.as_posix()}, "test")

    def test_paired_bootstrap_preserves_speaker_clusters(self):
        samples = {str(i): {"id": str(i), "reference": "你好", "speaker": str(i // 2), "source": "test"} for i in range(24)}
        before = {key: {"asr_text": "你号"} for key in samples}
        after = {key: {"asr_text": "你好"} for key in samples}
        result = paired_delta(samples, before, after, draws=100)
        self.assertEqual(result["clusters"], 12)
        self.assertEqual(result["cer_delta_95pct_cluster_bootstrap"], [-0.5, -0.5])
        with self.assertRaisesRegex(ValueError, "identical"):
            paired_delta(samples, before, {})

    def test_meeting_intervals_do_not_pretend_to_be_independent(self):
        samples = {f"aishell-4:room:{i}": {"id": f"aishell-4:room:{i}", "reference": "你好", "source": "aishell-4-meeting", "speaker": str(i)} for i in range(20)}
        predictions = {key: {"asr_text": "你好"} for key in samples}
        self.assertIsNone(paired_delta(samples, predictions, predictions)["cer_delta_95pct_cluster_bootstrap"])

    def test_fleurs_legacy_ids_are_not_treated_as_speakers(self):
        samples = {str(i): {"id": str(i), "reference": "你好", "source": "fleurs-cmn-hans-cn", "speaker": str(i)} for i in range(20)}
        predictions = {key: {"asr_text": "你好"} for key in samples}
        self.assertIsNone(paired_delta(samples, predictions, predictions)["cer_delta_95pct_cluster_bootstrap"])

    def test_review_selection_has_random_controls_without_duplicates(self):
        samples = {str(i): {"id": str(i), "reference": "你好", "source": "test"} for i in range(8)}
        predictions = {key: {"asr_text": "" if key == "0" else "你好"} for key in samples}
        selected = select(samples, predictions, worst=1, random_count=2)
        self.assertEqual(len({row["id"] for row in selected}), 3)
        self.assertEqual(selected[0]["id"], "0")
        self.assertEqual(sum(row["review_selection"] == "random_control" for row in selected), 2)

    def test_authored_risk_cases_through_real_offline_rules(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "local-api"))
        from app.text_structure import structure_text_conservatively
        from evaluate import read_jsonl
        cases = read_jsonl(Path(__file__).resolve().parents[1] / "fixtures" / "high-risk-text.jsonl")
        manifest = {key: {field: value for field, value in row.items() if not field.startswith("translation_")} for key, row in cases.items()}
        outputs = {key: {"structured_text": structure_text_conservatively(row["input_text"])} for key, row in manifest.items()}
        self.assertEqual(evaluate(manifest, outputs)["safety"]["automatic_violation_ids"], [])

    def test_alignment_counts_equal_levenshtein_distance(self):
        strings = [""] + ["".join(chars) for n in range(1, 4) for chars in itertools.product("甲乙", repeat=n)]
        for source in strings:
            for target in strings:
                counts = alignment_counts(source, target)
                self.assertEqual(counts["character_errors"], edit_distance(source, target))
                self.assertEqual(counts["character_errors"], sum(counts[key] for key in ("substitutions", "deletions", "insertions")))
        self.assertEqual(alignment_counts("你好", "")['deletions'], 2)

    def test_number_diagnostic_does_not_forgive_wrong_numbers(self):
        rows, report = analyze({"a": {"id": "a", "reference": "百分之七"}}, {"a": {"asr_text": "8%"}})
        self.assertIn("number_format_candidate", rows[0]["flags"])
        self.assertGreater(report["by_source"]["unknown"]["cer"], 0)

    def test_translation_date_and_case_contracts(self):
        sample = {"translation_required_any": [["day after tomorrow", "in two days"]], "translation_verbatim_terms": ["userID"]}
        self.assertEqual(translation_violations(sample, "Send userID in two days."), [])
        self.assertEqual(len(translation_violations(sample, "Send userid tomorrow.")), 2)

    def test_new_translation_regression_fails_comparison(self):
        sample = {"a": {"id": "a", "translation_reference": "See you the day after tomorrow.",
                        "translation_required_any": [["day after tomorrow"]]}}
        good = evaluate(sample, {"a": {"id": "a", "translation": "See you the day after tomorrow.", "end_to_end_ms": 1}})
        bad = evaluate(sample, {"a": {"id": "a", "translation": "See you tomorrow.", "end_to_end_ms": 1}})
        self.assertTrue(compare(good, bad)[1])

    def test_safety_gate_rejects_swapped_failures_at_equal_rate(self):
        samples = {key: {"id": key, "translation_reference": "Send tomorrow.", "translation_required_any": [["tomorrow"]]} for key in ("a", "b")}
        before = evaluate(samples, {"a": {"translation": "Send today.", "end_to_end_ms": 1}, "b": {"translation": "Send tomorrow.", "end_to_end_ms": 1}})
        after = evaluate(samples, {"a": {"translation": "Send tomorrow.", "end_to_end_ms": 1}, "b": {"translation": "Send today.", "end_to_end_ms": 1}})
        summary, unsafe = compare(before, after)
        self.assertTrue(unsafe)
        self.assertIn("New translation violations: b", summary)

    def test_structure_case_sensitive_terms(self):
        sample = {"a": {"id": "a", "input_text": "userID", "verbatim_terms": ["userID"]}}
        self.assertEqual(evaluate(sample, {"a": {"structured_text": "userid"}})["safety"]["automatic_violation_rate"], 1)

    def test_review_contains_translation_source_and_escapes_html(self):
        manifest = {"a": {"id": "a", "source_text": "原文</script>", "translation_reference": "Source"}}
        predictions = {"a": {"translation": "Output"}}
        rows = review_rows(manifest, predictions)
        self.assertEqual(rows[0]["input_text"], "原文</script>")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.html"
            write_html(path, rows, predictions)
            page = path.read_text(encoding="utf-8")
            data = page.split('type="application/json">', 1)[1].split('</script>', 1)[0]
            self.assertEqual(json.loads(data)["rows"][0]["input_text"], "原文</script>")
            self.assertNotIn("__REVIEW_DATA__", page)

    def test_reviews_need_distinct_people_and_complete_scores(self):
        predictions = {"a": {"asr_text": "你好"}}
        with self.assertRaisesRegex(ValueError, "distinct"):
            merge(predictions, [{"id": "a", "reviewer": "Alice"}, {"id": "a", "reviewer": " alice "}])
        with self.assertRaisesRegex(ValueError, "must score"):
            merge(predictions, [{"id": "a", "reviewer": "alice"}, {"id": "a", "reviewer": "bob"}])
        with self.assertRaisesRegex(ValueError, "different asr_text"):
            merge(predictions, [{"id": "a", "reviewer": "alice", "asr_text": "旧版本的输出"}])


if __name__ == "__main__":
    unittest.main()
