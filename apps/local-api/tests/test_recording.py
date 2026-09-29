"""Microphone boundary tests use synthetic input, never the user's microphone."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.audio_recorder import AudioRecorder


class FakeMicrophone:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.disconnected = False
        self.closed = False
    def start(self): pass
    def feed(self): self.callback(np.ones((1600, 1), dtype=np.float32) * 0.1, 1600, None, None)
    def stop(self):
        if self.disconnected: raise OSError("device disconnected")
    def close(self): self.closed = True


class RecordingTests(unittest.TestCase):
    def test_disconnection_does_not_discard_already_captured_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            streams = []
            def open_stream(**kwargs):
                stream = FakeMicrophone(**kwargs); streams.append(stream); return stream
            with patch("sounddevice.InputStream", side_effect=open_stream):
                recorder = AudioRecorder(Path(temp))
                recorder.start()
                streams[0].feed()
                streams[0].disconnected = True
                result = recorder.stop()
                self.assertEqual(sf.info(result["filePath"]).frames, 1600)
                self.assertFalse(recorder.status()["isRecording"])
                self.assertTrue(streams[0].closed)

    def test_one_hundred_capture_cycles_release_each_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            streams = []
            def open_stream(**kwargs):
                stream = FakeMicrophone(**kwargs); streams.append(stream); return stream
            with patch("sounddevice.InputStream", side_effect=open_stream):
                recorder = AudioRecorder(Path(temp))
                for _ in range(100):
                    recorder.start(); streams[-1].feed()
                    result = recorder.stop()
                    self.assertEqual(sf.info(result["filePath"]).frames, 1600)
                self.assertTrue(all(stream.closed for stream in streams))


if __name__ == "__main__": unittest.main()
