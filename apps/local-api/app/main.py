from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pathlib import Path
from time import perf_counter

from .audio_recorder import AudioRecorder, AudioRecorderError
from .config import settings
from .ollama_client import is_ollama_reachable
from .structure_service import structure_text_hybrid
from .stt_service import STTError, get_stt_provider, stt_provider
from .translation_service import translate_chinese_to_english


class StructureRequest(BaseModel):
    text: str = Field(min_length=1)
    model: str | None = None


class StructureResponse(BaseModel):
    model: str
    originalText: str
    structuredText: str


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1)


class TranslationResponse(BaseModel):
    originalText: str
    translatedText: str
    model: str


class HealthResponse(BaseModel):
    status: str
    ollamaReachable: bool
    defaultModel: str


class AudioDevice(BaseModel):
    id: int
    name: str
    maxInputChannels: int
    defaultSampleRate: float


class RecordingStatus(BaseModel):
    isRecording: bool
    startedAt: float | None
    sampleRate: int
    channels: int


class StartRecordingRequest(BaseModel):
    deviceId: int | None = None


class StopRecordingResponse(BaseModel):
    filePath: str
    durationSeconds: float
    sampleRate: int
    channels: int
    audioRms: float
    audioPeak: float


class TranscriptSegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class TranscribeRequest(BaseModel):
    filePath: str
    language: str | None = None
    provider: str | None = None


class TranscribeResponse(BaseModel):
    provider: str
    model: str
    text: str
    language: str
    durationSeconds: float
    sttElapsedMs: int
    segments: list[TranscriptSegmentResponse]


class VoiceFinishResponse(BaseModel):
    audioFilePath: str
    durationSeconds: float
    audioRms: float
    audioPeak: float
    transcript: str
    structuredText: str
    sttProvider: str
    sttModel: str
    llmModel: str
    recordingStopElapsedMs: int
    sttElapsedMs: int
    llmElapsedMs: int
    totalElapsedMs: int


class VoiceFinishRequest(BaseModel):
    outputMode: str = "zh"


class VoiceTranscribeResponse(BaseModel):
    audioFilePath: str
    durationSeconds: float
    audioRms: float
    audioPeak: float
    transcript: str
    sttProvider: str
    sttModel: str
    recordingStopElapsedMs: int
    sttElapsedMs: int
    totalElapsedMs: int


class VoicePreviewResponse(BaseModel):
    durationSeconds: float
    transcript: str
    sttProvider: str
    sttModel: str
    sttElapsedMs: int


app = FastAPI(title="liketypeless local API", version="0.1.0")
recorder = AudioRecorder(recordings_dir=Path(__file__).resolve().parents[1] / "data" / "recordings")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ollamaReachable=is_ollama_reachable(),
        defaultModel=settings.default_model,
    )


@app.get("/audio/devices", response_model=list[AudioDevice])
def audio_devices() -> list[AudioDevice]:
    try:
        return [AudioDevice(**device) for device in recorder.list_input_devices()]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to list audio devices: {exc}") from exc


@app.get("/audio/recording/status", response_model=RecordingStatus)
def recording_status() -> RecordingStatus:
    return RecordingStatus(**recorder.status())


@app.post("/audio/recording/start", response_model=RecordingStatus)
def start_recording(request: StartRecordingRequest | None = None) -> RecordingStatus:
    try:
        return RecordingStatus(**recorder.start(device_id=request.deviceId if request else None))
    except AudioRecorderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to start recording: {exc}") from exc


@app.post("/audio/recording/stop", response_model=StopRecordingResponse)
def stop_recording() -> StopRecordingResponse:
    try:
        return StopRecordingResponse(**recorder.stop())
    except AudioRecorderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to stop recording: {exc}") from exc


@app.post("/stt/transcribe", response_model=TranscribeResponse)
def transcribe_audio(request: TranscribeRequest) -> TranscribeResponse:
    try:
        result = get_stt_provider(request.provider).transcribe(Path(request.filePath), language=request.language)
    except STTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TranscribeResponse(
        provider=result.provider,
        model=result.model,
        text=result.text,
        language=result.language,
        durationSeconds=result.duration_seconds,
        sttElapsedMs=result.elapsed_ms,
        segments=[TranscriptSegmentResponse(start=segment.start, end=segment.end, text=segment.text) for segment in result.segments],
    )


@app.post("/voice/recording/transcribe", response_model=VoiceTranscribeResponse)
def transcribe_voice_recording() -> VoiceTranscribeResponse:
    total_started_at = perf_counter()
    stop_started_at = perf_counter()
    try:
        recording = recorder.stop()
    except AudioRecorderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to stop recording: {exc}") from exc
    recording_stop_elapsed_ms = round((perf_counter() - stop_started_at) * 1000)

    audio_file_path = recording["filePath"]
    try:
        transcript = stt_provider.transcribe(Path(audio_file_path), language=settings.stt_language)
    except STTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return VoiceTranscribeResponse(
        audioFilePath=audio_file_path,
        durationSeconds=float(recording["durationSeconds"]),
        audioRms=float(recording["audioRms"]),
        audioPeak=float(recording["audioPeak"]),
        transcript=transcript.text,
        sttProvider=transcript.provider,
        sttModel=transcript.model,
        recordingStopElapsedMs=recording_stop_elapsed_ms,
        sttElapsedMs=transcript.elapsed_ms,
        totalElapsedMs=round((perf_counter() - total_started_at) * 1000),
    )


@app.post("/voice/recording/preview", response_model=VoicePreviewResponse)
def preview_voice_recording() -> VoicePreviewResponse:
    try:
        snapshot = recorder.snapshot()
    except AudioRecorderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to snapshot recording: {exc}") from exc

    snapshot_path = Path(snapshot["filePath"])
    try:
        transcript = stt_provider.transcribe(snapshot_path, language=settings.stt_language)
    except STTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        snapshot_path.unlink(missing_ok=True)

    return VoicePreviewResponse(
        durationSeconds=float(snapshot["durationSeconds"]),
        transcript=transcript.text,
        sttProvider=transcript.provider,
        sttModel=transcript.model,
        sttElapsedMs=transcript.elapsed_ms,
    )


@app.post("/voice/recording/finish", response_model=VoiceFinishResponse)
def finish_voice_recording(request: VoiceFinishRequest | None = None) -> VoiceFinishResponse:
    total_started_at = perf_counter()
    stop_started_at = perf_counter()
    try:
        recording = recorder.stop()
    except AudioRecorderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to stop recording: {exc}") from exc
    recording_stop_elapsed_ms = round((perf_counter() - stop_started_at) * 1000)

    audio_file_path = recording["filePath"]
    try:
        transcript = stt_provider.transcribe(Path(audio_file_path), language=settings.stt_language)
    except STTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    structured_text = ""
    structure_elapsed_ms = 0
    structure_model = "none"
    if transcript.text:
        structure_started_at = perf_counter()
        structure_result = structure_text_hybrid(transcript.text)
        structured_text = structure_result.text
        structure_model = structure_result.provider
        structure_elapsed_ms = round((perf_counter() - structure_started_at) * 1000)

    output_mode = request.outputMode if request else "zh"
    if output_mode == "zh-to-en" and structured_text:
        translation_started_at = perf_counter()
        try:
            structured_text, structure_model = translate_chinese_to_english(structured_text)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        structure_elapsed_ms += round((perf_counter() - translation_started_at) * 1000)

    return VoiceFinishResponse(
        audioFilePath=audio_file_path,
        durationSeconds=float(recording["durationSeconds"]),
        audioRms=float(recording["audioRms"]),
        audioPeak=float(recording["audioPeak"]),
        transcript=transcript.text,
        structuredText=structured_text,
        sttProvider=transcript.provider,
        sttModel=transcript.model,
        llmModel=structure_model,
        recordingStopElapsedMs=recording_stop_elapsed_ms,
        sttElapsedMs=transcript.elapsed_ms,
        llmElapsedMs=structure_elapsed_ms,
        totalElapsedMs=round((perf_counter() - total_started_at) * 1000),
    )


@app.post("/llm/structure", response_model=StructureResponse)
def structure_text(request: StructureRequest) -> StructureResponse:
    del request.model
    structure_result = structure_text_hybrid(request.text)

    return StructureResponse(
        model=structure_result.provider,
        originalText=request.text,
        structuredText=structure_result.text,
    )


@app.post("/llm/translate", response_model=TranslationResponse)
def translate_text(request: TranslationRequest) -> TranslationResponse:
    try:
        translated_text, model = translate_chinese_to_english(request.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TranslationResponse(originalText=request.text, translatedText=translated_text, model=model)
