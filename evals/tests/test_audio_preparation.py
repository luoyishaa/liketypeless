from __future__ import annotations
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_audio import prepare
from evaluate import read_jsonl


class AudioPreparationTests(unittest.TestCase):
    def test_channel_selection_preserves_signal_and_rejects_missing_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stereo.wav"
            with wave.open(str(source), "wb") as handle:
                handle.setparams((2, 2, 16000, 0, "NONE", "not compressed"))
                handle.writeframes(struct.pack("<hh", 1000, -1000) * 1600)
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"id": "a", "audio_path": str(source), "reference": "测试"}), encoding="utf-8")
            output = root / "channel0.jsonl"
            prepare(manifest, output, root / "cache", channel=0)
            row = read_jsonl(output)["a"]
            with wave.open(row["audio_path"], "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(struct.unpack("<h", handle.readframes(1))[0], 1000)
            with self.assertRaises(subprocess.CalledProcessError):
                prepare(manifest, root / "invalid.jsonl", root / "cache", channel=8)
            self.assertFalse((root / "invalid.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
