"""Pinned model preparation. Downloads never happen inside an ASR request."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
import shutil
import threading
import urllib.error
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

    def _download(self, name: str, spec: tuple, endpoint: str, partial: Path, completed: int):
        expected_size = spec[0]
        # A server can close a large response without raising. Keep verified
        # byte counts and resume with a checked Content-Range, across retries
        # and application restarts.
        for attempt in range(5):
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > expected_size:
                partial.unlink()
                offset = 0
            if offset == expected_size:
                return
            request = urllib.request.Request(
                f"{endpoint}/{REPOSITORY}/resolve/{REVISION}/{name}",
                headers={"Range": f"bytes={offset}-"} if offset else {},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    if response.status == 206:
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                        if not match or int(match[1]) != offset or int(match[3]) != expected_size:
                            raise ValueError(f"{name} 续传范围异常，请重新下载。")
                    elif response.status == 200:
                        offset = 0  # Origin ignored Range: restart, never append duplicate bytes.
                    else:
                        raise ValueError(f"{name} 下载响应异常（{response.status}）。")
                    count = offset
                    with partial.open("ab" if offset else "wb") as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                            count += len(chunk)
                            if count > expected_size:
                                raise ValueError("模型下载大小异常。")
                            self._update(downloadedBytes=completed + count)
            except urllib.error.HTTPError:
                raise
            except (OSError, urllib.error.URLError):
                if attempt == 4:
                    raise ValueError(f"{name} 下载中断，已保留进度；请重试。") from None
                continue
            if partial.stat().st_size == expected_size:
                return
        raise ValueError(f"{name} 下载不完整，已保留进度；请重试。")

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
                        self._download(name, spec, endpoint, partial, completed)
                    if not valid_file(partial, spec):
                        partial.unlink(missing_ok=True)
                        raise ValueError(f"{name} 校验失败，请重试。")
                    partial.replace(target)
                completed += spec[0]
                self._update(downloadedBytes=completed)
            self._update(state="ready")
        except Exception as exc:
            self._update(state="error", error=f"模型准备失败：{exc}")
