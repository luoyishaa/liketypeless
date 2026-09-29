"""Pinned model preparation. Downloads never happen inside an ASR request."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import threading
import urllib.request

REPOSITORY = "Systran/faster-whisper-small"
REVISION = "536b0662742c02347bc0e980a01041f333bce120"
# Hashes from the official Hub metadata at the fixed revision, not a moving branch.
FILES = {
    "config.json": (2370, "git", "e5047537059bd8f182d9ca64c470201585015187"),
    "model.bin": (483546902, "sha256", "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
    "tokenizer.json": (2203239, "git", "7818adb6de9fa3064d3ff81226fdd675be1f6344"),
    "vocabulary.txt": (459861, "git", "c9074644d9d1205686f16d411564729461324b75"),
}


def valid_file(path: Path, spec: tuple) -> bool:
    size, kind, expected = spec
    if not path.is_file() or path.stat().st_size != size:
        return False
    digest = hashlib.sha256() if kind == "sha256" else hashlib.sha1()
    if kind == "git":
        digest.update(f"blob {size}\0".encode())
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


class ModelManager:
    def __init__(self, directory: Path):
        self.directory = directory
        self._lock = threading.Lock()
        self._state = {"state": "missing", "downloadedBytes": 0,
                       "totalBytes": sum(spec[0] for spec in FILES.values()), "error": None,
                       "revision": REVISION}
        if all((directory / name).is_file() for name in FILES):
            self.prepare(verify_only=True)

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def prepare(self, source: Path | None = None, endpoint: str = "https://huggingface.co", verify_only=False):
        if endpoint not in ("https://huggingface.co", "https://hf-mirror.com"):
            raise ValueError("不支持的模型来源。")
        with self._lock:
            if self._state["state"] in ("downloading", "verifying"):
                raise ValueError("模型正在准备，请稍候。")
            self._state.update(state="verifying" if source or verify_only else "downloading", error=None, downloadedBytes=0)
        threading.Thread(target=self._prepare, args=(source, endpoint, verify_only), daemon=True).start()

    def _prepare(self, source: Path | None, endpoint: str, verify_only: bool):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            completed = 0
            for name, spec in FILES.items():
                target = self.directory / name
                if not valid_file(target, spec):
                    if verify_only:
                        raise ValueError("模型文件不完整，请重新下载或导入固定版本。")
                    partial = self.directory / (name + ".part")
                    if source:
                        candidate = source / name
                        if not valid_file(candidate, spec):
                            raise ValueError(f"{name} 与当前固定模型版本不一致。")
                        shutil.copyfile(candidate, partial)
                    else:
                        offset = partial.stat().st_size if partial.exists() else 0
                        if offset >= spec[0]:
                            partial.unlink()
                            offset = 0
                        request = urllib.request.Request(
                            f"{endpoint}/{REPOSITORY}/resolve/{REVISION}/{name}",
                            headers={"Range": f"bytes={offset}-"} if offset else {},
                        )
                        with urllib.request.urlopen(request, timeout=30) as response:
                            if response.status != 206:
                                offset = 0
                            with partial.open("ab" if offset else "wb") as output:
                                count = offset
                                while chunk := response.read(1024 * 1024):
                                    output.write(chunk)
                                    count += len(chunk)
                                    if count > spec[0]:
                                        raise ValueError("模型下载大小异常。")
                                    self._update(downloadedBytes=completed + count)
                    if not valid_file(partial, spec):
                        partial.unlink(missing_ok=True)
                        raise ValueError(f"{name} 校验失败，请重试。")
                    partial.replace(target)
                completed += spec[0]
                self._update(downloadedBytes=completed)
            self._update(state="ready")
        except Exception as exc:
            self._update(state="error", error=f"模型准备失败：{exc}")
