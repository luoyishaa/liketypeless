import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("publish_route_summary", SCRIPTS / "publish_route_summary.py")
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


class PublishRouteSummaryTests(unittest.TestCase):
    @staticmethod
    def report(provider, errors):
        return {"sample_count": 2, "portable_manifest_sha256": "manifest",
                "runtime": {"backend_sha256": "binary", "requested_provider": provider},
                "summary": {"character_errors": errors, "reference_characters": 10,
                            "raw_asr_cer": errors / 10,
                            "request_latency_ms": {"first": 3, "p50": 2, "p95": 3}}}

    def test_redacts_rows_and_preserves_paired_evidence(self):
        baseline = self.report("local-faster-whisper", 4)
        routed = self.report("local-routed", 2)
        paired = {"sample_count": 2, "speaker_count": 2, "threshold_seconds": 4,
                  "whisper": {"character_errors": 4}, "route": {"character_errors": 2,
                  "sensevoice_samples": 1}, "paired_gain": {"cer_points": 0.2,
                  "relative_error_reduction": 0.5, "speaker_bootstrap_95_cer_points": [0.1, 0.3]},
                  "samples": [{"id": "private", "asr_text": "private"}]}
        result = summary.summarize_pair("short", baseline, routed, paired)
        self.assertEqual(result["paired_gain"]["relative_error_reduction"], 0.5)
        self.assertEqual(result["portable_manifest_sha256"], "manifest")
        self.assertNotIn("private", str(result))

    def test_rejects_mismatched_backend_or_results(self):
        baseline = self.report("local-faster-whisper", 4)
        routed = self.report("local-routed", 2)
        paired = {"sample_count": 2, "speaker_count": 2, "threshold_seconds": 4,
                  "whisper": {"character_errors": 4}, "route": {"character_errors": 2,
                  "sensevoice_samples": 1}, "paired_gain": {"cer_points": 0.2,
                  "relative_error_reduction": 0.5, "speaker_bootstrap_95_cer_points": [0.1, 0.3]}}
        routed["runtime"]["backend_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "backend"):
            summary.summarize_pair("short", baseline, routed, paired)


if __name__ == "__main__":
    unittest.main()
