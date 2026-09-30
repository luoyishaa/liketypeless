"""Verified, optional portable SenseVoice artifacts in the user data directory."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from zipfile import ZipFile


MODEL_REVISION = "90c1c61912018b70ada0fcc024ea24aca62f2e63"
RUNTIME_TAG = "runtime-llamacpp-v0.2.6"
MODEL_URL = f"https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/{MODEL_REVISION}/sensevoice-small-q8.gguf"
RUNTIME_URL = f"https://github.com/modelscope/FunASR/releases/download/{RUNTIME_TAG}/funasr-llamacpp-windows-x64.zip"
MODEL_SPEC = (254208320, "4ae45c94422de949b387e2e0fb10d7e14e4c42c69db30c3444ecc7d4b844b7c5")
ARCHIVE_SPEC = (4967457, "f6a73a548413ba9fbaf2145263ea66ec53cbdad1fb11790dbeeee493e339492e")
EXE_SHA256 = "e92b69bc3b0d395dc611572566f91abcf5318ef7a54b27dcdf445bd231ded426"
MODEL_NAME = "sensevoice-small-q8.gguf"
EXE_NAME = "llama-funasr-sensevoice.exe"


def valid_file(path: Path, spec: tuple[int, str]) -> bool:
    if not path.is_file() or path.stat().st_size != spec[0]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == spec[1]


class SenseVoiceBundle:
    def __init__(self, directory: Path, *, model_url: str = MODEL_URL, runtime_url: str = RUNTIME_URL,
                 model_spec: tuple[int, str] = MODEL_SPEC, archive_spec: tuple[int, str] = ARCHIVE_SPEC,
                 exe_sha256: str = EXE_SHA256):
        self.directory = directory
        self.cleanup_staged_audio()
        self.model_url, self.runtime_url = model_url, runtime_url
        self.model_spec, self.archive_spec, self.exe_sha256 = model_spec, archive_spec, exe_sha256
        self._lock = threading.Lock()
        self._state = {"state": "ready" if self._valid_installed() else "missing", "downloadedBytes": 0,
                       "totalBytes": model_spec[0] + archive_spec[0], "error": None,
                       "revision": f"{MODEL_REVISION}+{RUNTIME_TAG}"}

    def _valid_installed(self) -> bool:
        return (valid_file(self.directory / MODEL_NAME, self.model_spec)
                and self._valid_executable(self.directory / EXE_NAME))

    def cleanup_staged_audio(self, max_age_seconds: int = 24 * 3600) -> None:
        """Remove this provider's abandoned audio copies after an unclean exit."""
        if not self.directory.is_dir():
            return
        cutoff = time.time() - max_age_seconds
        for path in self.directory.glob("clip-*.wav"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                # Cleanup must not prevent base Whisper input at startup.
                pass

    def _valid_executable(self, path: Path) -> bool:
        return path.is_file() and valid_file(path, (path.stat().st_size, self.exe_sha256))

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def paths(self) -> tuple[Path, Path]:
        if self.status()["state"] != "ready":
            raise ValueError("SenseVoice bundle is not ready")
        return self.directory / MODEL_NAME, self.directory / EXE_NAME

    def _update(self, **values) -> None:
        with self._lock:
            self._state.update(values)

    def prepare(self, source: Path | None = None) -> None:
        with self._lock:
            if self._state["state"] == "ready":
                return
            if self._state["state"] in {"downloading", "verifying"}:
                raise ValueError("短句优化模型正在准备，请稍候。")
            self._state.update(state="verifying" if source else "downloading", error=None, downloadedBytes=0)
        threading.Thread(target=self._prepare, args=(source,), daemon=True,
                         name="liketypeless-sensevoice-prepare").start()

    def _prepare(self, source: Path | None) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            model = self.directory / MODEL_NAME
            if not valid_file(model, self.model_spec):
                if source:
                    candidate = source / MODEL_NAME
                    if not valid_file(candidate, self.model_spec):
                        raise ValueError("导入的 GGUF 模型与固定版本不一致。")
                    shutil.copyfile(candidate, model.with_suffix(".part"))
                else:
                    self._download(self.model_url, model.with_suffix(".part"), self.model_spec, 0)
                partial = model.with_suffix(".part")
                if not valid_file(partial, self.model_spec):
                    partial.unlink(missing_ok=True)
                    raise ValueError("GGUF 模型校验失败，请重试。")
                partial.replace(model)
            self._update(downloadedBytes=self.model_spec[0])

            executable = self.directory / EXE_NAME
            if not self._valid_executable(executable):
                if source:
                    candidate = source / EXE_NAME
                    if not self._valid_executable(candidate):
                        raise ValueError("导入的便携运行程序与固定版本不一致。")
                    shutil.copyfile(candidate, executable.with_suffix(".part"))
                    executable.with_suffix(".part").replace(executable)
                else:
                    archive = self.directory / "runtime.zip"
                    if not valid_file(archive, self.archive_spec):
                        self._download(self.runtime_url, archive.with_suffix(".part"), self.archive_spec,
                                       self.model_spec[0])
                        partial = archive.with_suffix(".part")
                        if not valid_file(partial, self.archive_spec):
                            partial.unlink(missing_ok=True)
                            raise ValueError("便携程序压缩包校验失败，请重试。")
                        partial.replace(archive)
                    self._extract_runtime()
            if not self._valid_installed():
                raise ValueError("模型或便携程序不完整。")
            self._update(state="ready", downloadedBytes=self.model_spec[0] + self.archive_spec[0])
        except Exception as exc:
            self._update(state="error", error=f"短句优化模型准备失败：{exc}")

    def _extract_runtime(self) -> None:
        archive = self.directory / "runtime.zip"
        if not valid_file(archive, self.archive_spec):
            raise ValueError("便携程序压缩包校验失败。")
        with ZipFile(archive) as zipped:
            if zipped.namelist().count(EXE_NAME) != 1:
                raise ValueError("便携程序压缩包缺少目标程序。")
            partial = self.directory / "runtime-exe.part"
            with zipped.open(EXE_NAME) as source, partial.open("wb") as output:
                shutil.copyfileobj(source, output)
        if not valid_file(partial, (partial.stat().st_size, self.exe_sha256)):
            partial.unlink(missing_ok=True)
            raise ValueError("便携程序校验失败。")
        partial.replace(self.directory / EXE_NAME)

    def _download(self, url: str, partial: Path, spec: tuple[int, str], completed: int) -> None:
        expected_size = spec[0]
        for attempt in range(5):
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > expected_size:
                partial.unlink()
                offset = 0
            if offset == expected_size:
                return
            request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status == 206:
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                        if not match or int(match[1]) != offset or int(match[3]) != expected_size:
                            raise ValueError("下载续传范围异常，请重试。")
                    elif response.status == 200:
                        offset = 0
                    else:
                        raise ValueError(f"下载响应异常（{response.status}）。")
                    count = offset
                    with partial.open("ab" if offset else "wb") as output:
                        while block := response.read(1024 * 1024):
                            output.write(block)
                            count += len(block)
                            if count > expected_size:
                                raise ValueError("下载大小异常。")
                            self._update(downloadedBytes=completed + count)
            except (OSError, urllib.error.URLError):
                if attempt == 4:
                    raise ValueError("下载中断，已保留进度；请重试。") from None
                continue
            if partial.stat().st_size == expected_size:
                return
        raise ValueError("下载不完整，已保留进度；请重试。")
