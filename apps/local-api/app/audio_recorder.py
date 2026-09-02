from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioRecorderError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(self, recordings_dir: Path, sample_rate: int = 16_000, channels: int = 1) -> None:
        self.recordings_dir = recordings_dir
        self.preferred_sample_rate = sample_rate
        self.active_sample_rate = sample_rate
        self.channels = channels
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray[Any, np.dtype[np.float32]]] = []
        self._started_at: float | None = None

    def list_input_devices(self) -> list[dict[str, Any]]:
        devices = sd.query_devices()
        input_devices: list[dict[str, Any]] = []

        for index, device in enumerate(devices):
            max_input_channels = int(device.get("max_input_channels", 0))
            if max_input_channels <= 0:
                continue

            input_devices.append(
                {
                    "id": index,
                    "name": str(device.get("name", f"Input device {index}")),
                    "maxInputChannels": max_input_channels,
                    "defaultSampleRate": float(device.get("default_samplerate", 0)),
                }
            )

        return input_devices

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "isRecording": self._stream is not None,
                "startedAt": self._started_at,
                "sampleRate": self.active_sample_rate,
                "channels": self.channels,
            }

    def start(self, device_id: int | None = None) -> dict[str, Any]:
        with self._lock:
            if self._stream is not None:
                raise AudioRecorderError("Recording is already active.")

            self._chunks = []
            self._started_at = time.time()
            stream, sample_rate = self._create_stream(device_id)
            stream.start()
            self._stream = stream
            self.active_sample_rate = sample_rate
            return {
                "isRecording": True,
                "startedAt": self._started_at,
                "sampleRate": self.active_sample_rate,
                "channels": self.channels,
            }

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._stream is None:
                raise AudioRecorderError("Recording is not active.")

            stream = self._stream
            chunks = self._chunks
            started_at = self._started_at
            self._stream = None
            self._chunks = []
            self._started_at = None

        stream.stop()
        stream.close()

        if not chunks:
            raise AudioRecorderError("Recording stopped without captured audio.")

        audio = np.concatenate(chunks, axis=0)
        duration_seconds = float(len(audio) / self.active_sample_rate)
        audio_mono = audio.mean(axis=1) if audio.ndim > 1 else audio
        audio_rms = float(np.sqrt(np.mean(audio_mono**2))) if len(audio_mono) else 0.0
        audio_peak = float(np.max(np.abs(audio_mono))) if len(audio_mono) else 0.0
        file_path = self._write_wav(audio)

        return {
            "filePath": str(file_path),
            "durationSeconds": duration_seconds if started_at is not None else 0,
            "sampleRate": self.active_sample_rate,
            "channels": self.channels,
            "audioRms": audio_rms,
            "audioPeak": audio_peak,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._stream is None:
                raise AudioRecorderError("Recording is not active.")
            if not self._chunks:
                raise AudioRecorderError("Recording has not captured audio yet.")
            audio = np.concatenate(self._chunks, axis=0)
            sample_rate = self.active_sample_rate

        file_path = self._write_wav(audio, directory_name="previews")
        return {
            "filePath": str(file_path),
            "durationSeconds": float(len(audio) / sample_rate),
        }

    def _create_stream(self, device_id: int | None) -> tuple[sd.InputStream, int]:
        try:
            stream = sd.InputStream(
                samplerate=self.preferred_sample_rate,
                channels=self.channels,
                dtype="float32",
                device=device_id,
                callback=self._on_audio,
            )
            return stream, self.preferred_sample_rate
        except Exception:
            default_sample_rate = self._default_input_sample_rate(device_id)
            stream = sd.InputStream(
                samplerate=default_sample_rate,
                channels=self.channels,
                dtype="float32",
                device=device_id,
                callback=self._on_audio,
            )
            return stream, default_sample_rate

    def _default_input_sample_rate(self, device_id: int | None) -> int:
        try:
            device = sd.query_devices(device=device_id, kind="input")
            sample_rate = int(device.get("default_samplerate", 44_100))
        except Exception:
            sample_rate = 44_100
        return sample_rate

    def _on_audio(
        self,
        indata: np.ndarray[Any, np.dtype[np.float32]],
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time_info
        if status:
            # Avoid raising from the callback thread. Short overruns can happen.
            pass

        with self._lock:
            if self._stream is not None:
                self._chunks.append(indata.copy())

    def _write_wav(self, audio: np.ndarray[Any, np.dtype[np.float32]], directory_name: str | None = None) -> Path:
        output_directory = self.recordings_dir / directory_name if directory_name else self.recordings_dir
        output_directory.mkdir(parents=True, exist_ok=True)
        file_path = output_directory / f"{uuid.uuid4().hex}.wav"
        sf.write(file_path, audio, self.active_sample_rate, subtype="PCM_16")
        return file_path
