from __future__ import annotations

from .config import settings
from .ollama_client import OllamaError, generate_chat_text

TRANSLATION_PROMPT = """Translate the user's Chinese voice input into natural English. Preserve meaning, facts, lists, names, and tone. Output only the English translation. Do not explain or summarize."""


def translate_chinese_to_english(text: str) -> tuple[str, str]:
    if not text.strip():
        return "", "none"
    try:
        translated = generate_chat_text(settings.default_model, TRANSLATION_PROMPT, text)
    except OllamaError as exc:
        raise RuntimeError(f"English translation failed: {exc}") from exc
    if not translated:
        raise RuntimeError("English translation returned empty text.")
    return translated, f"translation:{settings.default_model}"
