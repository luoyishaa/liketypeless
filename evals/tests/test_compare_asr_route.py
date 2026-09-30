import importlib.util
import json
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("compare_asr_route", SCRIPTS / "compare_asr_route.py")
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


class CompareAsrRouteTests(unittest.TestCase):
    def test_audio_mismatch_is_rejected(self):
        samples = [{"id": "one", "reference": "你好", "duration_seconds": 2, "speaker": "s"}]
        whisper = {"samples": [{"id": "one", "audio_sha256": "a", "asr_text": "你"}]}
        sensevoice = {"samples": [{"id": "one", "audio_sha256": "b", "asr_text": "你好"}]}
        with self.assertRaisesRegex(ValueError, "audio"):
            comparison.compare(samples, whisper, sensevoice, threshold_seconds=4)

    def test_route_selects_by_duration_and_reports_paired_errors(self):
        samples = [
            {"id": "short", "reference": "你好", "duration_seconds": 2, "speaker": "a"},
            {"id": "long", "reference": "明天开会", "duration_seconds": 6, "speaker": "b"},
        ]
        whisper = {"samples": [
            {"id": "short", "audio_sha256": "a", "asr_text": "你"},
            {"id": "long", "audio_sha256": "b", "asr_text": "明天开会"},
        ]}
        sensevoice = {"samples": [
            {"id": "short", "audio_sha256": "a", "asr_text": "你好"},
            {"id": "long", "audio_sha256": "b", "asr_text": "今天开会"},
        ]}
        report = comparison.compare(samples, whisper, sensevoice, threshold_seconds=4)
        self.assertEqual(report["route"]["sensevoice_samples"], 1)
        self.assertEqual(report["route"]["character_errors"], 0)
        self.assertEqual(report["whisper"]["character_errors"], 1)

    def test_aggregate_baseline_can_be_sliced_to_exact_selected_ids(self):
        samples = [{"id": "one", "reference": "你好", "duration_seconds": 2, "speaker": "s"}]
        whisper = {"samples": [{"id": "one", "audio_sha256": "a", "asr_text": "你好"},
                               {"id": "other", "audio_sha256": "b", "asr_text": "其他"}]}
        sensevoice = {"samples": [{"id": "one", "audio_sha256": "a", "asr_text": "你好"}]}
        self.assertEqual(comparison.compare(samples, whisper, sensevoice, threshold_seconds=4)["sample_count"], 1)

    def test_product_route_report_is_scored_as_actual_candidate_not_resimulated(self):
        samples = [{"id": "one", "reference": "你好", "duration_seconds": 5, "speaker": "s"}]
        whisper = {"samples": [{"id": "one", "audio_sha256": "a", "asr_text": "你"}]}
        routed = {"samples": [{"id": "one", "audio_sha256": "a", "asr_text": "你",
                               "provider": "local-faster-whisper", "stt_fallback_reason": None}]}
        report = comparison.compare(samples, whisper, routed, threshold_seconds=4, candidate_is_routed=True)
        self.assertEqual(report["route"]["character_errors"], 1)
        self.assertEqual(report["route"]["sensevoice_samples"], 0)


if __name__ == "__main__":
    unittest.main()
