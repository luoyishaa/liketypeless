from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from time import perf_counter
from typing import Protocol

from .config import settings


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


class SpeechToTextProvider(Protocol):
    provider_name: str

    def transcribe(self, file_path: Path, language: str | None = None) -> TranscriptionResult:
        pass


class LocalFasterWhisperProvider:
    provider_name = "local-faster-whisper"

    def __init__(self) -> None:
        self._model = None
        self._loaded_model_name: str | None = None
        self._loaded_device: str | None = None
        self._loaded_compute_type: str | None = None
        self._converter = None
        self._dll_dirs_added = False

    def transcribe(self, file_path: Path, language: str | None = None) -> TranscriptionResult:
        if not file_path.exists():
            raise STTError(f"Audio file does not exist: {file_path}")

        started_at = perf_counter()
        model = self._load_model()
        selected_language = language or settings.stt_language

        try:
            segments, detected_language, duration = self._transcribe_audio(model, file_path, selected_language)
        except Exception as exc:
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
            return self._transcribe_single_file(model, file_path, language)

        return self._transcribe_in_chunks(model, file_path, language, duration, chunk_seconds)

    def _transcribe_single_file(self, model, file_path: Path, language: str) -> tuple[list[TranscriptSegment], str, float]:
        segments_iter, info = self._transcribe_with_optional_vad(model, file_path, language)
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
                segments, chunk_language, _chunk_duration = self._transcribe_single_file(model, chunk_path, detected_language)
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

    def _transcribe_with_optional_vad(self, model, file_path: Path, language: str):
        if not settings.stt_vad_filter:
            return model.transcribe(
                str(file_path),
                language=language,
                vad_filter=False,
                beam_size=settings.stt_beam_size,
                without_timestamps=settings.stt_without_timestamps,
            )

        try:
            return model.transcribe(
                str(file_path),
                language=language,
                vad_filter=True,
                beam_size=settings.stt_beam_size,
                without_timestamps=settings.stt_without_timestamps,
            )
        except Exception as exc:
            if "onnxruntime" not in str(exc).lower() and "vad" not in str(exc).lower():
                raise

            return model.transcribe(
                str(file_path),
                language=language,
                vad_filter=False,
                beam_size=settings.stt_beam_size,
                without_timestamps=settings.stt_without_timestamps,
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

                self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
                self._loaded_model_name = model_name
                self._loaded_device = device
                self._loaded_compute_type = compute_type
                return self._model
            except Exception as exc:
                last_error = exc
                self._model = None

        raise STTError(f"Unable to load faster-whisper model '{model_name}': {last_error}")

    def _add_optional_nvidia_dll_paths(self) -> None:
        if self._dll_dirs_added:
            return

        site_packages = Path(__file__).resolve().parents[3] / ".venv" / "Lib" / "site-packages"
        dll_dirs = [
            site_packages / "nvidia" / "cudnn" / "bin",
            site_packages / "nvidia" / "cublas" / "bin",
            site_packages / "nvidia" / "cuda_nvrtc" / "bin",
        ]
        existing_dirs = [path for path in dll_dirs if path.exists()]
        for path in existing_dirs:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(path))

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


def create_stt_providers() -> dict[str, SpeechToTextProvider]:
    providers: dict[str, SpeechToTextProvider] = {
        LocalFasterWhisperProvider.provider_name: LocalFasterWhisperProvider(),
        LocalSenseVoiceProvider.provider_name: LocalSenseVoiceProvider(),
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
