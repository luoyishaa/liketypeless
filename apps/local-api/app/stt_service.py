from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import threading
from time import perf_counter
from typing import Protocol

from .config import settings
from .sensevoice_bundle import SenseVoiceBundle


class STTError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    provider: str
    model: str
    text: str
    language: str
    duration_seconds: float
    elapsed_ms: int
    segments: list[TranscriptSegment]
    fallback_reason: str | None = None


class SpeechToTextProvider(Protocol):
    provider_name: str

    def transcribe(self, file_path: Path, language: str | None = None) -> TranscriptionResult:
        pass


class LocalFasterWhisperProvider:
    provider_name = "local-faster-whisper"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._loaded_model_name: str | None = None
        self._loaded_device: str | None = None
        self._loaded_compute_type: str | None = None
        self._converter = None
        self._dll_dirs_added = False
        self._dll_handles = []
        self._fallback_reason = None

    def runtime_status(self):
        return {"device": self._loaded_device, "computeType": self._loaded_compute_type,
                "fallbackReason": self._fallback_reason}

    def transcribe(self, file_path: Path, language: str | None = None) -> TranscriptionResult:
        if not file_path.exists():
            raise STTError(f"Audio file does not exist: {file_path}")

        started_at = perf_counter()
        selected_language = language or settings.stt_language
        with self._lock:
            try:
                model = self._load_model()
                segments, detected_language, duration = self._transcribe_audio(model, file_path, selected_language)
            except Exception as exc:
                if settings.stt_device == "auto" and self._loaded_device == "cuda":
                    try:
                        from faster_whisper import WhisperModel
                        self._model = WhisperModel(self._configured_model_name(), device="cpu", compute_type="int8", local_files_only=True)
                        self._loaded_device, self._loaded_compute_type = "cpu", "int8"
                        self._fallback_reason = "GPU 处理失败，已回退 CPU。"
                        segments, detected_language, duration = self._transcribe_audio(self._model, file_path, selected_language)
                    except Exception as fallback_error:
                        raise STTError(f"CPU 回退识别失败：{fallback_error}") from fallback_error
                else:
                    raise STTError(f"faster-whisper transcription failed: {exc}") from exc

        text = self._normalize_chinese("".join(segment.text for segment in segments).strip())

        return TranscriptionResult(
            provider=self.provider_name,
            model=self._loaded_model_name or self._configured_model_name(),
            text=text,
            language=detected_language,
            duration_seconds=duration,
            elapsed_ms=round((perf_counter() - started_at) * 1000),
            segments=segments,
        )

    def _transcribe_audio(self, model, file_path: Path, language: str) -> tuple[list[TranscriptSegment], str, float]:
        duration = self._audio_duration_seconds(file_path)
        chunk_seconds = settings.stt_chunk_seconds
        if chunk_seconds <= 0 or duration <= chunk_seconds:
            return self._transcribe_single_file(
                model, file_path, language, without_timestamps=False if duration > 30 else None
            )

        return self._transcribe_in_chunks(model, file_path, language, duration, chunk_seconds)

    def _transcribe_single_file(
        self, model, file_path: Path, language: str, without_timestamps: bool | None = None
    ) -> tuple[list[TranscriptSegment], str, float]:
        segments_iter, info = self._transcribe_with_optional_vad(model, file_path, language, without_timestamps)
        return (
            self._collect_segments(segments_iter),
            str(getattr(info, "language", language) or language),
            float(getattr(info, "duration", 0.0) or 0.0),
        )

    def _transcribe_in_chunks(
        self, model, file_path: Path, language: str, duration: float, chunk_seconds: int
    ) -> tuple[list[TranscriptSegment], str, float]:
        all_segments: list[TranscriptSegment] = []
        detected_language = language
        with tempfile.TemporaryDirectory(prefix="liketypeless-stt-") as temporary_directory:
            for offset_seconds, chunk_path in self._write_wav_chunks(file_path, Path(temporary_directory), chunk_seconds):
                segments, chunk_language, _chunk_duration = self._transcribe_single_file(
                    model, chunk_path, detected_language, without_timestamps=False
                )
                detected_language = chunk_language or detected_language
                all_segments.extend(
                    TranscriptSegment(
                        start=segment.start + offset_seconds,
                        end=segment.end + offset_seconds,
                        text=segment.text,
                    )
                    for segment in segments
                )

        return all_segments, detected_language, duration

    def _audio_duration_seconds(self, file_path: Path) -> float:
        try:
            import soundfile as sf

            return float(sf.info(str(file_path)).duration)
        except Exception:
            return 0.0

    def _write_wav_chunks(self, file_path: Path, output_directory: Path, chunk_seconds: int):
        try:
            import soundfile as sf
        except ImportError as exc:
            raise STTError("soundfile is required for long-recording chunk transcription") from exc

        with sf.SoundFile(str(file_path)) as source:
            sample_rate = source.samplerate
            frames_per_chunk = sample_rate * chunk_seconds
            offset_frames = 0
            index = 0
            while offset_frames < len(source):
                source.seek(offset_frames)
                audio_frames = source.read(frames_per_chunk, dtype="float32", always_2d=True)
                if len(audio_frames) == 0:
                    break
                chunk_path = output_directory / f"chunk-{index:04d}.wav"
                sf.write(str(chunk_path), audio_frames, sample_rate, subtype="PCM_16")
                yield offset_frames / sample_rate, chunk_path
                offset_frames += len(audio_frames)
                index += 1

    def _transcribe_with_optional_vad(
        self, model, file_path: Path, language: str, without_timestamps: bool | None = None
    ):
        suppress_timestamps = settings.stt_without_timestamps if without_timestamps is None else without_timestamps
        if not settings.stt_vad_filter:
            return model.transcribe(
                str(file_path),
                language=language,
                vad_filter=False,
                beam_size=settings.stt_beam_size,
                without_timestamps=suppress_timestamps,
            )

        try:
            return model.transcribe(
                str(file_path),
                language=language,
                vad_filter=True,
                beam_size=settings.stt_beam_size,
                without_timestamps=suppress_timestamps,
            )
        except Exception as exc:
            if "onnxruntime" not in str(exc).lower() and "vad" not in str(exc).lower():
                raise

            return model.transcribe(
                str(file_path),
                language=language,
                vad_filter=False,
                beam_size=settings.stt_beam_size,
                without_timestamps=suppress_timestamps,
            )

    def _collect_segments(self, segments_iter) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=self._normalize_chinese(segment.text.strip()),
            )
            for segment in segments_iter
        ]

    def _normalize_chinese(self, text: str) -> str:
        if not text:
            return text

        try:
            if self._converter is None:
                from opencc import OpenCC

                self._converter = OpenCC("t2s")
            return self._converter.convert(text)
        except Exception:
            return text

    def _load_model(self):
        model_name = self._configured_model_name()
        candidates = self._runtime_candidates()

        if (
            self._model is not None
            and self._loaded_model_name == model_name
            and (self._loaded_device, self._loaded_compute_type) in candidates
        ):
            return self._model

        last_error: Exception | None = None
        for device, compute_type in candidates:
            try:
                self._add_optional_nvidia_dll_paths()
                from faster_whisper import WhisperModel

                self._model = WhisperModel(model_name, device=device, compute_type=compute_type, local_files_only=True)
                self._loaded_model_name = model_name
                self._loaded_device = device
                self._loaded_compute_type = compute_type
                return self._model
            except Exception as exc:
                last_error = exc
                self._model = None
                if device == "cuda":
                    self._fallback_reason = "GPU 不可用，已回退 CPU。"

        raise STTError(f"Unable to load faster-whisper model '{model_name}': {last_error}")

    def _add_optional_nvidia_dll_paths(self) -> None:
        if self._dll_dirs_added:
            return

        site_packages = Path(getattr(sys, "_MEIPASS", Path(sys.prefix) / "Lib" / "site-packages"))
        dll_dirs = [
            site_packages / "nvidia" / "cudnn" / "bin",
            site_packages / "nvidia" / "cublas" / "bin",
            site_packages / "nvidia" / "cuda_nvrtc" / "bin",
        ]
        existing_dirs = [path for path in dll_dirs if path.exists()]
        for path in existing_dirs:
            if hasattr(os, "add_dll_directory"):
                self._dll_handles.append(os.add_dll_directory(str(path)))

        if existing_dirs:
            os.environ["PATH"] = ";".join([*(str(path) for path in existing_dirs), os.environ.get("PATH", "")])

        self._dll_dirs_added = True

    def _configured_model_name(self) -> str:
        return settings.stt_model_path or settings.stt_model

    def _runtime_candidates(self) -> list[tuple[str, str]]:
        device = settings.stt_device.lower()
        compute_type = settings.stt_compute_type.lower()

        if device != "auto" and compute_type != "auto":
            return [(device, compute_type)]

        if device == "cuda":
            return [("cuda", "float16" if compute_type == "auto" else compute_type)]

        if device == "cpu":
            return [("cpu", "int8" if compute_type == "auto" else compute_type)]

        if compute_type == "auto":
            return [("cuda", "float16"), ("cpu", "int8")]

        return [("cuda", compute_type), ("cpu", compute_type)]


class LocalSenseVoiceProvider:
    provider_name = "local-sensevoice"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None

    def transcribe(self, file_path: Path, language: str | None = None) -> TranscriptionResult:
        del language
        if not file_path.exists():
            raise STTError(f"Audio file does not exist: {file_path}")

        python_path = Path(settings.sensevoice_python)
        runner_path = Path(settings.sensevoice_runner)
        if not python_path.exists():
            raise STTError(f"SenseVoice Python runtime does not exist: {python_path}")
        if not runner_path.exists():
            raise STTError(f"SenseVoice runner does not exist: {runner_path}")

        with self._lock:
            payload, elapsed_ms = self._transcribe_with_worker(python_path, runner_path, file_path)

        text = str(payload.get("text", "")).strip()
        return TranscriptionResult(
            provider=self.provider_name,
            model=str(payload.get("model", "iic/SenseVoiceSmall")),
            text=text,
            language=str(payload.get("language", "zh")),
            duration_seconds=0.0,
            elapsed_ms=elapsed_ms,
            segments=[TranscriptSegment(start=0.0, end=0.0, text=text)] if text else [],
        )

    def _transcribe_with_worker(self, python_path: Path, runner_path: Path, file_path: Path) -> tuple[dict[str, object], int]:
        started_at = perf_counter()
        process = self._ensure_worker(python_path, runner_path)
        if process.stdin is None or process.stdout is None:
            raise STTError("SenseVoice worker pipes are not available.")

        try:
            process.stdin.write(json.dumps({"audioFile": str(file_path)}) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
        except Exception as exc:
            self._stop_worker()
            raise STTError(f"SenseVoice worker communication failed: {exc}") from exc

        if not line:
            self._stop_worker()
            raise STTError("SenseVoice worker exited without a response.")

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise STTError(f"SenseVoice worker returned invalid JSON: {line}") from exc

        if "error" in payload:
            raise STTError(str(payload["error"]))

        return payload, round((perf_counter() - started_at) * 1000)

    def _ensure_worker(self, python_path: Path, runner_path: Path) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process

        self._process = subprocess.Popen(
            [str(python_path), "-u", str(runner_path), "--server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if self._process.stdout is None:
            self._stop_worker()
            raise STTError("SenseVoice worker stdout is not available.")

        ready_line = self._process.stdout.readline()
        if not ready_line:
            self._stop_worker()
            raise STTError("SenseVoice worker failed to start.")

        try:
            ready_payload = json.loads(ready_line)
        except json.JSONDecodeError as exc:
            self._stop_worker()
            raise STTError(f"SenseVoice worker returned invalid ready payload: {ready_line}") from exc

        if ready_payload.get("status") != "ready":
            self._stop_worker()
            raise STTError(f"SenseVoice worker failed to become ready: {ready_payload}")

        return self._process

    def _stop_worker(self) -> None:
        if self._process is None:
            return
        self._process.kill()
        self._process = None


class RoutedSpeechProvider:
    """Short verified GGUF clips; all other paths retain the proven Whisper provider."""

    provider_name = "local-routed"
    threshold_seconds = 4.0

    def __init__(self, whisper: SpeechToTextProvider, bundle: SenseVoiceBundle):
        self.whisper = whisper
        self.bundle = bundle

    def runtime_status(self):
        runtime = self.whisper.runtime_status()
        return {**runtime, "shortModelState": self.bundle.status()["state"],
                "shortModelDirectory": str(self.bundle.directory),
                "shortRouteThresholdSeconds": self.threshold_seconds}

    def transcribe(self, file_path: Path, language: str | None = None) -> TranscriptionResult:
        started_at = perf_counter()
        try:
            import soundfile as sf
            info = sf.info(str(file_path))
            duration = float(info.duration)
        except Exception:
            return self.whisper.transcribe(file_path, language=language)
        if duration > self.threshold_seconds:
            return self.whisper.transcribe(file_path, language=language)
        if file_path.suffix.lower() != ".wav":
            return self._fallback(file_path, language, started_at,
                                  "短句录音格式不适用，已回退 Whisper。")
        if self.bundle.status()["state"] != "ready":
            return self._fallback(file_path, language, started_at, "短句优化模型未准备，已使用 Whisper。")

        try:
            model, executable = self.bundle.paths()
            # The upstream Windows CLI uses narrow file arguments. Pass ASCII
            # basenames from its Unicode working directory, including for audio.
            with tempfile.NamedTemporaryFile(dir=model.parent, prefix="clip-", suffix=".wav",
                                             delete=False) as staged:
                staged_path = Path(staged.name)
            try:
                if info.samplerate == 16000 and info.channels == 1 and info.subtype == "PCM_16":
                    shutil.copyfile(file_path, staged_path)
                else:
                    self._normalize_short_audio(file_path, staged_path, info.samplerate)
                result = subprocess.run([str(executable), "-m", model.name, "-a", staged_path.name,
                                         "--backend", "cpu"], cwd=str(model.parent), capture_output=True,
                                        text=True, encoding="utf-8", errors="replace", timeout=15,
                                        check=False)
            finally:
                staged_path.unlink(missing_ok=True)
            if result.returncode != 0 or not result.stdout.strip():
                raise STTError("便携识别程序未返回可用文字")
            text = result.stdout.strip()
            return TranscriptionResult(provider="local-sensevoice-gguf", model="SenseVoiceSmall-GGUF:q8",
                                       text=text, language="zh", duration_seconds=duration,
                                       elapsed_ms=round((perf_counter() - started_at) * 1000),
                                       segments=[TranscriptSegment(start=0, end=duration, text=text)])
        except Exception:
            # This optimizer is optional; decoding, conversion and native failures
            # must all preserve the base Whisper result.
            return self._fallback(file_path, language, started_at, "短句优化识别失败，已回退 Whisper。")

    @staticmethod
    def _normalize_short_audio(source: Path, target: Path, sample_rate: int) -> None:
        """Convert a short microphone fallback rate to CLI-compatible PCM16."""
        import av
        import numpy as np
        import soundfile as sf

        audio, _ = sf.read(str(source), dtype="int16", always_2d=True)
        if audio.size == 0:
            raise STTError("短句录音为空")
        mono = np.rint(audio.astype(np.float32).mean(axis=1)).astype(np.int16)
        frame = av.AudioFrame.from_ndarray(mono.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = sample_rate
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = resampler.resample(frame) + resampler.resample(None)
        if not frames:
            raise STTError("短句录音转换失败")
        resampled = np.concatenate([output.to_ndarray().reshape(-1) for output in frames])
        sf.write(str(target), resampled, 16000, subtype="PCM_16")

    def _fallback(self, file_path: Path, language: str | None, started_at: float,
                  reason: str) -> TranscriptionResult:
        result = self.whisper.transcribe(file_path, language=language)
        return replace(result, fallback_reason=reason,
                       elapsed_ms=round((perf_counter() - started_at) * 1000))


sensevoice_bundle = SenseVoiceBundle(settings.sensevoice_bundle_dir or settings.data_dir / "models" / "sensevoice")


def create_stt_providers() -> dict[str, SpeechToTextProvider]:
    whisper = LocalFasterWhisperProvider()
    providers: dict[str, SpeechToTextProvider] = {
        LocalFasterWhisperProvider.provider_name: whisper,
        LocalSenseVoiceProvider.provider_name: LocalSenseVoiceProvider(),
        RoutedSpeechProvider.provider_name: RoutedSpeechProvider(whisper, sensevoice_bundle),
    }
    return providers


def create_stt_provider() -> SpeechToTextProvider:
    providers = create_stt_providers()
    if settings.stt_provider not in providers:
        raise STTError(f"Unsupported STT provider: {settings.stt_provider}")

    return providers[settings.stt_provider]


stt_providers = create_stt_providers()


def get_stt_provider(provider_name: str | None = None) -> SpeechToTextProvider:
    selected_provider = provider_name or settings.stt_provider
    provider = stt_providers.get(selected_provider)
    if provider is None:
        raise STTError(f"Unsupported STT provider: {selected_provider}")
    return provider


stt_provider = get_stt_provider()
