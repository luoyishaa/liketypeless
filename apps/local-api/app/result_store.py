"""Crash-recoverable results, confined audio retention and atomic SQLite writes."""
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager


class ResultStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.database = directory / "results.sqlite3"
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, created REAL, audio TEXT, transcript TEXT, text TEXT, status TEXT, error TEXT)")
        self.prune()
        with self._connect() as db:
            known = {row[0] for row in db.execute("SELECT audio FROM results")}
        for audio in (directory / "recordings").glob("*.wav"):
            if str(audio) not in known:
                identifier = self.create(str(audio))
                self.update(identifier, status="failed", error="恢复了上次未处理的录音，可重试识别。")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, audio: str) -> str:
        identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO results VALUES (?, ?, ?, '', '', 'processing', NULL)", (identifier, time.time(), audio))
        return identifier

    def update(self, identifier, *, transcript=None, text=None, status=None, error=None):
        with self._connect() as db:
            db.execute("UPDATE results SET transcript=COALESCE(?,transcript), text=COALESCE(?,text), status=COALESCE(?,status), error=? WHERE id=?",
                       (transcript, text, status, error, identifier))

    def get(self, identifier):
        with self._connect() as db:
            row = db.execute("SELECT * FROM results WHERE id=?", (identifier,)).fetchone()
        return dict(row) if row else None

    def list(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM results ORDER BY created DESC LIMIT 50")]

    def remove_audio(self, audio):
        path = Path(audio).resolve()
        root = (self.directory / "recordings").resolve()
        if path.is_relative_to(root) and path.suffix == ".wav":
            path.unlink(missing_ok=True)

    def prune(self):
        cutoff = time.time() - 86400
        root = self.directory / "recordings"
        if root.exists():
            for path in root.rglob("*.wav"):
                if path.stat().st_mtime < cutoff:
                    self.remove_audio(str(path))
        with self._connect() as db:
            db.execute("DELETE FROM results WHERE id NOT IN (SELECT id FROM results ORDER BY created DESC LIMIT 50)")

    def clear(self):
        root = self.directory / "recordings"
        if root.exists():
            for path in root.rglob("*.wav"):
                self.remove_audio(str(path))
        with self._connect() as db:
            db.execute("DELETE FROM results")
