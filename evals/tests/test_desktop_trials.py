"""The desktop trial report must not convert missing real-world evidence into a pass."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "evals" / "scripts" / "summarize_desktop_trials.py"
FIELDS = (
    "trial_id", "target_app", "mode", "reference_text", "raw_transcript",
    "final_text", "outcome", "result_recoverable", "stop_to_usable_ms",
    "correction_edits", "critical_fact_changed",
)


class DesktopTrialSummaryTests(unittest.TestCase):
    def test_report_separates_real_delivery_from_recovery_and_unmeasured_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "trials.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows([
                    {"trial_id": "1", "target_app": "notepad", "mode": "basic", "reference_text": "你好",
                     "raw_transcript": "你好", "final_text": "你好。", "outcome": "direct",
                     "result_recoverable": "yes", "stop_to_usable_ms": "800", "correction_edits": "0",
                     "critical_fact_changed": "no"},
                    {"trial_id": "2", "target_app": "notepad", "mode": "basic", "reference_text": "明天",
                     "raw_transcript": "今天", "final_text": "今天。", "outcome": "manual_copy",
                     "result_recoverable": "yes", "stop_to_usable_ms": "1000", "correction_edits": "1",
                     "critical_fact_changed": "yes"},
                    {"trial_id": "3", "target_app": "browser", "mode": "enhanced", "reference_text": "开会",
                     "raw_transcript": "开会", "final_text": "开会。", "outcome": "direct",
                     "result_recoverable": "yes", "stop_to_usable_ms": "1200", "correction_edits": "0",
                     "critical_fact_changed": "no"},
                ])
            output = root / "summary.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--trials", str(source), "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["trial_count"], 3)
            self.assertEqual(report["overall"]["direct_input_count"], 2)
            self.assertEqual(report["overall"]["direct_input_rate"], 0.666667)
            self.assertEqual(report["overall"]["manual_copy_count"], 1)
            self.assertEqual(report["overall"]["wrong_target_count"], 0)
            self.assertEqual(report["overall"]["unrecoverable_count"], 0)
            self.assertEqual(report["overall"]["raw_asr_cer"], 0.166667)
            self.assertEqual(report["overall"]["direct_stop_to_usable_ms"]["p95"], 1200)
            self.assertFalse(report["release_gate"]["evaluable"])
            self.assertIsNone(report["release_gate"]["passed"])

    def test_failed_asr_can_have_empty_transcript_and_counts_as_cer_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "trials.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow({
                    "trial_id": "failed-1", "target_app": "notepad", "mode": "basic",
                    "reference_text": "你好", "raw_transcript": "", "final_text": "",
                    "outcome": "lost", "result_recoverable": "no", "stop_to_usable_ms": "",
                    "correction_edits": "0", "critical_fact_changed": "no",
                })
            output = root / "summary.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--trials", str(source), "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["overall"]["raw_asr_cer"], 1.0)
            self.assertEqual(report["overall"]["unrecoverable_count"], 1)
            self.assertIsNone(report["overall"]["direct_stop_to_usable_ms"]["p95"])

    def test_release_gate_requires_app_coverage_and_zero_wrong_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "trials.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                for app in ("notepad", "browser", "word"):
                    for index in range(20):
                        writer.writerow({
                            "trial_id": f"{app}-{index}", "target_app": app, "mode": "basic",
                            "reference_text": "你好", "raw_transcript": "你好", "final_text": "你好。",
                            "outcome": "wrong_target" if app == "word" and index == 19 else "direct",
                            "result_recoverable": "yes", "stop_to_usable_ms": "500",
                            "correction_edits": "0", "critical_fact_changed": "no",
                        })
            output = root / "summary.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--trials", str(source), "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["release_gate"]["evaluable"])
            self.assertFalse(report["release_gate"]["passed"])
            self.assertEqual(report["overall"]["direct_input_count"], 59)
            self.assertEqual(report["overall"]["wrong_target_count"], 1)


if __name__ == "__main__":
    unittest.main()
