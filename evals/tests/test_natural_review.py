import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("summarize_natural_review", SCRIPTS / "summarize_natural_review.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class NaturalReviewTests(unittest.TestCase):
    def row(self, index: int):
        return {"case_id": f"NR{index:02d}", "reference_text": "明天开会", "raw_transcript": "明天开会",
                "machine_id": "win11-a", "app_version": "candidate", "asr_model": "whisper-small",
                "warm_state": "warm",
                "basic_text": "明天开会。", "enhanced_text": "明天开会。",
                "enhanced_provider": "local-conservative-rules", "basic_usable": "1", "enhanced_usable": "1",
                "basic_correction_edits": "0", "enhanced_correction_edits": "0",
                "basic_fact_changed": "0", "enhanced_fact_changed": "0", "reviewer": "r1"}

    def test_requires_thirty_complete_independent_reviews(self):
        rows = [self.row(index) for index in range(1, 31)]
        summary = review.summarize(rows)
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["raw_asr_cer"], 0)
        self.assertEqual(summary["enhanced_model_used_count"], 0)
        self.assertEqual(summary["enhanced_fallback_count"], 30)
        rows[0]["reviewer"] = ""
        pending = review.summarize(rows)
        self.assertFalse(pending["complete"])
        self.assertIsNone(pending["raw_asr_cer"])

    def test_fact_change_is_never_hidden_by_fewer_edits(self):
        rows = [self.row(index) for index in range(1, 31)]
        rows[2]["enhanced_provider"] = "hybrid-conservative-llm:qwen3:8b"
        rows[2]["enhanced_correction_edits"] = "0"
        rows[2]["basic_correction_edits"] = "2"
        rows[2]["enhanced_fact_changed"] = "1"
        summary = review.summarize(rows)
        self.assertEqual(summary["enhanced_critical_fact_changes"], 1)
        self.assertEqual(summary["enhanced_model_used_count"], 1)
        self.assertEqual(summary["paired_correction_edits_saved"], 2)


if __name__ == "__main__":
    unittest.main()
