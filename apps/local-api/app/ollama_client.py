import json
import urllib.error
import urllib.request
from typing import Any

from .config import settings


class OllamaError(RuntimeError):
    pass


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
    except (OSError, urllib.error.URLError) as exc:
        raise OllamaError(f"Ollama is not reachable: {exc}") from exc

    text = data.get("response")
    if not isinstance(text, str):
        raise OllamaError("Ollama response did not contain text.")
    return text.strip()


def generate_chat_text(model: str, system_prompt: str, user_text: str) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        "think": False,
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
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise OllamaError(f"Ollama is not reachable: {exc}") from exc

    message = data.get("message")
    if not isinstance(message, dict):
        raise OllamaError("Ollama chat response did not contain a message.")

    text = message.get("content")
    if not isinstance(text, str):
        raise OllamaError("Ollama chat response did not contain text.")
    return text.strip()
