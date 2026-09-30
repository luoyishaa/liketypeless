import csv
import importlib.util
import json
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("make_natural_review_sheet", SCRIPTS / "make_natural_review_sheet.py")
sheet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sheet)


class NaturalReviewSheetTests(unittest.TestCase):
    def test_generates_thirty_unscored_cases(self):
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "natural-review-tasks.jsonl"
        tasks = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines()]
        rows = sheet.make_rows(tasks)
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["case_id"], "NR01")
        self.assertEqual(rows[-1]["case_id"], "NR30")
        for row in rows:
            self.assertTrue(row["cue"])
            self.assertEqual(row["reference_text"], "")
            self.assertEqual(row["raw_transcript"], "")
            self.assertEqual(row["reviewer"], "")
            self.assertEqual(set(row), set(sheet.FIELDS))

    def test_rejects_duplicate_or_missing_case(self):
        tasks = [{"case_id": f"NR{i:02d}", "category": "number", "cue": "说一个数字"}
                 for i in range(1, 31)]
        tasks[-1]["case_id"] = "NR01"
        with self.assertRaisesRegex(ValueError, "NR01"):
            sheet.make_rows(tasks)


if __name__ == "__main__":
    unittest.main()
