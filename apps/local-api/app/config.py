import os
from pathlib import Path

from pydantic import BaseModel


class AppSettings(BaseModel):
    data_dir: Path = Path(os.getenv("LIKETYPELESS_DATA_DIR", str(Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "liketypeless")))
    session_token: str = os.getenv("LIKETYPELESS_SESSION_TOKEN", "")
    default_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    stt_provider: str = "local-faster-whisper"
    stt_model: str = "small"
    stt_model_path: str | None = None
    stt_language: str = "zh"
    stt_device: str = "auto"
    stt_compute_type: str = "auto"
    stt_beam_size: int = 1
    stt_without_timestamps: bool = True
    stt_vad_filter: bool = False
    stt_chunk_seconds: int = 90
    sensevoice_python: str = str(Path(__file__).resolve().parents[3] / ".venv-asr-py312" / "Scripts" / "python.exe")
    sensevoice_runner: str = str(Path(__file__).resolve().parents[1] / "scripts" / "sensevoice_runner.py")
    sensevoice_bundle_dir: Path | None = None
    llm_num_predict: int = 220
    hf_endpoint: str = "https://huggingface.co"


def default_stt_model_path() -> str | None:
    configured_path = os.getenv("LIKETYPELESS_STT_MODEL_PATH")
    if configured_path:
        return configured_path

    return str(AppSettings().data_dir / "models" / "small")


settings = AppSettings(
    default_model=os.getenv("LIKETYPELESS_OLLAMA_MODEL", "qwen3:8b"),
    ollama_base_url=os.getenv("LIKETYPELESS_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    stt_provider=os.getenv("LIKETYPELESS_STT_PROVIDER", "local-faster-whisper"),
    stt_model=os.getenv("LIKETYPELESS_STT_MODEL", "small"),
    stt_model_path=default_stt_model_path(),
    stt_language=os.getenv("LIKETYPELESS_STT_LANGUAGE", "zh"),
    stt_device=os.getenv("LIKETYPELESS_STT_DEVICE", "auto"),
    stt_compute_type=os.getenv("LIKETYPELESS_STT_COMPUTE_TYPE", "auto"),
    stt_beam_size=int(os.getenv("LIKETYPELESS_STT_BEAM_SIZE", "1")),
    stt_without_timestamps=os.getenv("LIKETYPELESS_STT_WITHOUT_TIMESTAMPS", "1") != "0",
    stt_vad_filter=os.getenv("LIKETYPELESS_STT_VAD_FILTER", "0") == "1",
    stt_chunk_seconds=max(0, int(os.getenv("LIKETYPELESS_STT_CHUNK_SECONDS", "90"))),
    sensevoice_python=os.getenv(
        "LIKETYPELESS_SENSEVOICE_PYTHON",
        str(Path(__file__).resolve().parents[3] / ".venv-asr-py312" / "Scripts" / "python.exe"),
    ),
    sensevoice_runner=os.getenv(
        "LIKETYPELESS_SENSEVOICE_RUNNER",
        str(Path(__file__).resolve().parents[1] / "scripts" / "sensevoice_runner.py"),
    ),
    sensevoice_bundle_dir=Path(os.environ["LIKETYPELESS_SENSEVOICE_BUNDLE_DIR"])
    if os.getenv("LIKETYPELESS_SENSEVOICE_BUNDLE_DIR") else None,
    llm_num_predict=int(os.getenv("LIKETYPELESS_LLM_NUM_PREDICT", "220")),
    hf_endpoint=os.getenv("HF_ENDPOINT", "https://huggingface.co"),
)

os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
