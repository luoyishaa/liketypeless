import json
import threading
from time import monotonic
import urllib.error
import urllib.request
from typing import Any

from .config import settings


class OllamaError(RuntimeError):
    pass


class ModelReadiness:
    """Keep slow model loading off the voice-input request path."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple[str, str] | None = None
        self._state = "unavailable"
        self._ready_until = 0.0
        self._retry_after = 0.0

    def ready_or_prepare(self, base_url: str, model: str) -> bool:
        key = (base_url, model)
        with self._lock:
            if key != self._key:
                self._key = key
                self._state = "unavailable"
                self._ready_until = 0.0
                self._retry_after = 0.0
            if self._state == "ready" and monotonic() < self._ready_until:
                return True
            if self._state == "loading" or monotonic() < self._retry_after:
                return False
            self._state = "loading"
        threading.Thread(target=self._prewarm, args=(key,), daemon=True, name="liketypeless-ollama-prewarm").start()
        return False

    def _prewarm(self, key: tuple[str, str]) -> None:
        base_url, model = key
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps({"model": model, "stream": False, "keep_alive": "5m"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 200:
                    raise OllamaError(f"Ollama preload failed with HTTP {response.status}")
                response.read()
        except Exception:
            with self._lock:
                if self._key == key:
                    self._state = "unavailable"
                    self._retry_after = monotonic() + 15
            return
        with self._lock:
            if self._key == key:
                self._state = "ready"
                self._ready_until = monotonic() + 240

    def mark_unavailable(self) -> None:
        with self._lock:
            self._state = "unavailable"
            self._retry_after = monotonic() + 15

    def status(self, base_url: str, model: str) -> dict[str, str]:
        with self._lock:
            state = self._state if self._key == (base_url, model) else "unavailable"
            if state == "ready" and monotonic() >= self._ready_until:
                state = "unavailable"
            return {"state": state, "model": model}


model_readiness = ModelReadiness()


def is_ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{settings.ollama_base_url}/api/tags", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def generate_text(model: str, prompt: str) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "top_p": 0.8,
            "num_predict": settings.llm_num_predict
        }
    }
    request = urllib.request.Request(
        f"{settings.ollama_base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise OllamaError(f"Ollama is not reachable: {exc}") from exc

    text = data.get("response")
    if not isinstance(text, str):
        raise OllamaError("Ollama response did not contain text.")
    return text.strip()


def generate_chat_text(model: str, system_prompt: str, user_text: str, timeout: float = 120) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "5m",
        "options": {
            "temperature": 0,
            "top_p": 0.8,
            "num_predict": settings.llm_num_predict,
        },
    }
    request = urllib.request.Request(
        f"{settings.ollama_base_url}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise OllamaError(f"Ollama is not reachable: {exc}") from exc

    if not isinstance(data, dict):
        raise OllamaError("Ollama response must be an object.")
    message = data.get("message")
    if not isinstance(message, dict):
        raise OllamaError("Ollama chat response did not contain a message.")

    text = message.get("content")
    if not isinstance(text, str):
        raise OllamaError("Ollama chat response did not contain text.")
    return text.strip()
