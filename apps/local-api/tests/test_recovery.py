from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.result_store import ResultStore


class RecoveryTests(unittest.TestCase):
    def test_unfinished_audio_is_recoverable_after_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "recordings" / "unfinished.wav"
            audio.parent.mkdir()
            audio.write_bytes(b"recording")
            store = ResultStore(Path(temp))
            self.assertEqual(store.list()[0]["status"], "failed")
            self.assertEqual(len(ResultStore(Path(temp)).list()), 1)

    def test_saved_result_survives_a_new_service_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ResultStore(Path(temp))
            identifier = store.create(str(Path(temp) / "recordings" / "test.wav"))
            store.update(identifier, transcript="明天开会", text="明天开会。", status="ready")
            reopened = ResultStore(Path(temp))
            self.assertEqual(reopened.list()[0]["text"], "明天开会。")
            reopened.clear()
            self.assertEqual(reopened.list(), [])

    def test_audio_cleanup_cannot_remove_an_external_file(self):
        with tempfile.TemporaryDirectory() as temp:
            external = Path(temp) / "user-recording.wav"
            external.write_bytes(b"user audio")
            store = ResultStore(Path(temp) / "app")
            store.remove_audio(str(external))
            self.assertTrue(external.exists())


if __name__ == "__main__": unittest.main()
