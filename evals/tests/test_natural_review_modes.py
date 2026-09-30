import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("natural_review_modes", SCRIPTS / "natural_review_modes.py")
modes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(modes)


class NaturalReviewModesTests(unittest.TestCase):
    def rows(self):
        return [{"case_id": f"NR{i:02d}", "raw_transcript": f"第{i}项", "basic_text": "",
                 "enhanced_text": "", "enhanced_provider": "", "reviewer": ""} for i in range(1, 31)]

    def test_exports_only_actual_raw_text_for_same_input_pairing(self):
        manifest = modes.export_manifest(self.rows())
        self.assertEqual(manifest[0], {"id": "NR01", "source": "natural-review",
                                       "input_text": "第1项"})
        rows = self.rows()
        rows[0]["raw_transcript"] = ""
        with self.assertRaisesRegex(ValueError, "NR01"):
            modes.export_manifest(rows)

    def test_merges_responses_without_filling_manual_judgements(self):
        rows = self.rows()
        report = {"samples": [{"id": row["case_id"], "raw_text": row["raw_transcript"],
                               "basic": {"text": "基础", "provider": "local-conservative-rules"},
                               "enhanced": {"text": "增强", "provider": "hybrid-conservative-llm:qwen3:8b"}}
                              for row in rows]}
        merged = modes.merge_mode_report(rows, report)
        self.assertEqual(merged[0]["basic_text"], "基础")
        self.assertEqual(merged[0]["enhanced_provider"], "hybrid-conservative-llm:qwen3:8b")
        self.assertEqual(merged[0]["reviewer"], "")
        report["samples"][0]["raw_text"] = "different"
        with self.assertRaisesRegex(ValueError, "NR01"):
            modes.merge_mode_report(rows, report)


if __name__ == "__main__":
    unittest.main()
