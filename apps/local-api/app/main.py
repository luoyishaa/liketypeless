from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pathlib import Path
from time import perf_counter
import secrets
import asyncio
from typing import Literal

from .audio_recorder import AudioRecorder, AudioRecorderError
from .config import settings
from .ollama_client import is_ollama_reachable
from .structure_service import structure_text_hybrid
from .text_structure import structure_text_conservatively, PROVIDER_NAME
from .stt_service import STTError, get_stt_provider, stt_provider
from .translation_service import translate_chinese_to_english
from .model_manager import ModelManager
from .result_store import ResultStore


class StructureRequest(BaseModel):
    text: str = Field(min_length=1)
    model: str | None = None
    cleanupMode: Literal["basic", "enhanced"] = "basic"


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
    ollamaReachable: bool | None
    defaultModel: str
    modelReady: bool
    runtime: dict


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
    resultId: str
    degraded: bool = False
    degradationReason: str | None = None
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
    outputMode: Literal["zh"] = "zh"
    cleanupMode: Literal["basic", "enhanced"] = "basic"


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
recorder = AudioRecorder(recordings_dir=settings.data_dir / "recordings")
results = ResultStore(settings.data_dir)
models = ModelManager(Path(settings.stt_model_path))
operation_lock = asyncio.Lock()


@app.middleware("http")
async def require_session(request: Request, call_next):
    if not settings.session_token or not secrets.compare_digest(
        request.headers.get("Authorization", ""), f"Bearer {settings.session_token}"
    ):
        return JSONResponse(status_code=401, content={"detail": "本机服务会话凭据无效，请重新启动应用。"})
    if request.method == "POST":
        if operation_lock.locked():
            return JSONResponse(status_code=409, content={"detail": "正在处理上一项操作，请稍候。"})
        async with operation_lock:
            return await call_next(request)
    return await call_next(request)

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
        ollamaReachable=None,
        defaultModel=settings.default_model,
        modelReady=models.status()["state"] == "ready",
        runtime=stt_provider.runtime_status(),
    )


@app.get("/audio/devices", response_model=list[AudioDevice])
def audio_devices() -> list[AudioDevice]:
    try:
        return [AudioDevice(**device) for device in recorder.list_input_devices()]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法检测麦克风，请检查连接与系统权限：{exc}") from exc


@app.get("/audio/recording/status", response_model=RecordingStatus)
def recording_status() -> RecordingStatus:
    return RecordingStatus(**recorder.status())


@app.post("/audio/recording/start", response_model=RecordingStatus)
def start_recording(request: StartRecordingRequest | None = None) -> RecordingStatus:
    if models.status()["state"] != "ready":
        raise HTTPException(status_code=409, detail="请先在首次使用引导中准备语音模型。")
    try:
        return RecordingStatus(**recorder.start(device_id=request.deviceId if request else None))
    except AudioRecorderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法开始录音，请重新选择麦克风或检查系统权限：{exc}") from exc


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
    identifier = results.create(audio_file_path)
    return process_recording(identifier, recording, request or VoiceFinishRequest(), total_started_at, recording_stop_elapsed_ms)


def process_recording(identifier, recording, request, total_started_at, recording_stop_elapsed_ms=0):
    audio_file_path = recording["filePath"]
    try:
        transcript = stt_provider.transcribe(Path(audio_file_path), language=settings.stt_language)
    except STTError as exc:
        results.update(identifier, status="failed", error=str(exc))
        raise HTTPException(status_code=502, detail="识别失败，录音已暂存。请在最近结果中重试。") from exc

    results.update(identifier, transcript=transcript.text, text=transcript.text, status="recognized")

    structured_text = ""
    structure_elapsed_ms = 0
    structure_model = "none"
    if transcript.text:
        structure_started_at = perf_counter()
        if request and request.cleanupMode == "enhanced":
            structure_result = structure_text_hybrid(transcript.text, timeout=4)
            structured_text = structure_result.text
            structure_model = structure_result.provider
        else:
            structured_text = structure_text_conservatively(transcript.text)
            structure_model = PROVIDER_NAME
        structure_elapsed_ms = round((perf_counter() - structure_started_at) * 1000)

    degraded = request.cleanupMode == "enhanced" and structure_model == PROVIDER_NAME
    results.update(identifier, text=structured_text or transcript.text, status="ready" if transcript.text else "empty")
    results.remove_audio(audio_file_path)
    results.prune()
    return VoiceFinishResponse(
        resultId=identifier,
        degraded=degraded,
        degradationReason="智能整理不可用或未通过安全检查，已使用基础整理。" if degraded else None,
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


class ModelPrepareRequest(BaseModel):
    sourcePath: str | None = None
    endpoint: Literal["https://huggingface.co", "https://hf-mirror.com"] = "https://huggingface.co"


@app.get("/models/status")
def model_status():
    return models.status()


@app.post("/models/prepare")
def prepare_model(request: ModelPrepareRequest):
    if recorder.status()["isRecording"]:
        raise HTTPException(status_code=409, detail="请先结束录音。")
    if models.status()["state"] == "ready":
        return models.status()
    try:
        models.prepare(Path(request.sourcePath) if request.sourcePath else None, request.endpoint)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return models.status()


@app.get("/results")
def recent_results():
    results.prune()
    return results.list()


@app.post("/results/clear")
def clear_results():
    if recorder.status()["isRecording"]:
        raise HTTPException(status_code=409, detail="请先结束录音再清除记录。")
    results.clear()
    return {"ok": True}


@app.post("/results/{identifier}/retry", response_model=VoiceFinishResponse)
def retry_result(identifier: str, request: VoiceFinishRequest):
    if recorder.status()["isRecording"]:
        raise HTTPException(status_code=409, detail="请先结束录音。")
    item = results.get(identifier)
    if not item or not Path(item["audio"]).is_file():
        raise HTTPException(status_code=410, detail="重试录音已过期；已有文字仍可复制。")
    import soundfile as sf
    info = sf.info(item["audio"])
    return process_recording(identifier, {"filePath": item["audio"], "durationSeconds": info.duration,
                             "audioRms": 0, "audioPeak": 0}, request, perf_counter())


@app.post("/llm/structure", response_model=StructureResponse)
def structure_text(request: StructureRequest) -> StructureResponse:
    del request.model
    if request.cleanupMode == "enhanced":
        result = structure_text_hybrid(request.text, timeout=4)
        return StructureResponse(model=result.provider, originalText=request.text, structuredText=result.text)
    return StructureResponse(model=PROVIDER_NAME, originalText=request.text,
                             structuredText=structure_text_conservatively(request.text))


@app.post("/llm/translate", response_model=TranslationResponse)
def translate_text(request: TranslationRequest) -> TranslationResponse:
    try:
        translated_text, model = translate_chinese_to_english(request.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TranslationResponse(originalText=request.text, translatedText=translated_text, model=model)
