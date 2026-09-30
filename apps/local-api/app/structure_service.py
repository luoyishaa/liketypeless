from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .config import settings
from .ollama_client import OllamaError, generate_chat_text, model_readiness
from .text_structure import PROVIDER_NAME as RULES_PROVIDER
from .text_structure import ensure_terminal_punctuation, structure_text_conservatively


HYBRID_PROVIDER_NAME = "hybrid-conservative-llm"

SYSTEM_PROMPT = """你是一个保守的中文语音输入整理器。

目标：把语音识别文本整理成可直接粘贴的文本。

只允许做：
1. 调整标点和换行，使原话更易读。
2. 完整陈述句以“。”结束，明确疑问以“？”结束，明确感叹才使用“！”。
3. 保留用户已有的“第一、第二、另外、最后”等结构。

禁止做：
1. 总结、扩写、润色、改写观点。
2. 添加用户没有说的信息。
3. 改变用户语气。
4. 把普通输入改写成总结、标题或提纲。
5. 删除、添加或改动任何字词、数字、英文和专有名词。

输出要求：
- 只输出整理后的正文，不要解释。
- 不要使用 Markdown 代码块。
- 保留原文的全部字词和顺序；口头填充词也不能删改。
- 如果原文已经有编号，保留编号；出现“第一、第二”等结构时，可以调整换行。
- 即使原文没有标点，也要按照语义补充标点。"""


@dataclass(frozen=True)
class StructureResult:
    provider: str
    text: str
    degradation_reason: str | None = None


def structure_text_hybrid(text: str, timeout: float = 2) -> StructureResult:
    rules_text = structure_text_conservatively(text)
    if not rules_text:
        return StructureResult(provider=RULES_PROVIDER, text="")

    if not model_readiness.ready_or_prepare(settings.ollama_base_url, settings.default_model):
        state = model_readiness.status(settings.ollama_base_url, settings.default_model)["state"]
        reason = ("智能整理模型正在准备，本次已使用基础整理。" if state == "loading"
                  else "智能整理模型不可用，本次已使用基础整理。")
        return StructureResult(provider=RULES_PROVIDER, text=rules_text, degradation_reason=reason)

    try:
        llm_text = generate_chat_text(model=settings.default_model, system_prompt=SYSTEM_PROMPT, user_text=rules_text, timeout=timeout)
    except OllamaError:
        model_readiness.mark_unavailable()
        return StructureResult(provider=RULES_PROVIDER, text=rules_text,
                               degradation_reason="智能整理响应失败或超时，本次已使用基础整理。")

    llm_text = ensure_terminal_punctuation(llm_text)
    if not _is_safe_result(source=rules_text, candidate=llm_text):
        return StructureResult(provider=RULES_PROVIDER, text=rules_text,
                               degradation_reason="智能整理改变了原文内容，本次已使用基础整理。")

    return StructureResult(provider=f"{HYBRID_PROVIDER_NAME}:{settings.default_model}", text=llm_text)


def _is_safe_result(source: str, candidate: str) -> bool:
    if not candidate:
        return False

    source_len = max(len(source), 1)
    candidate_len = len(candidate)
    if candidate_len < source_len * 0.45:
        return False
    if candidate_len > source_len * 1.8:
        return False

    # The optional model may format but may not silently rewrite recognized
    # words. This protects dates, numbers, negation and names equally, without
    # trying to guess which token in a Chinese sentence is a named entity.
    if _semantic_skeleton(source) != _semantic_skeleton(candidate):
        return False

    forbidden_markers = ("我认为", "总结", "以下是", "整理如下", "标题：")
    if any(marker in candidate for marker in forbidden_markers):
        return False

    return _keeps_source_clauses(source, candidate)


def _semantic_skeleton(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    retained = []
    for index, char in enumerate(normalized):
        if char.isspace() or char in "，,。！？!?；;、":
            continue
        if char == "." and not (index > 0 and index + 1 < len(normalized)
                                 and normalized[index - 1].isdigit() and normalized[index + 1].isdigit()):
            continue
        retained.append(char)
    return "".join(retained)


def _keeps_source_clauses(source: str, candidate: str) -> bool:
    source_clauses = [_normalize_clause(clause) for clause in re.split(r"[\n，,。！？；;]", source)]
    source_clauses = [clause for clause in source_clauses if len(clause) >= 5]
    if not source_clauses:
        return True

    candidate_chars = set(_normalize_clause(candidate))
    for clause in source_clauses:
        clause_chars = set(clause)
        if not clause_chars:
            continue
        if len(clause_chars & candidate_chars) / len(clause_chars) < 0.65:
            return False
    return True


def _normalize_clause(text: str) -> str:
    text = re.sub(r"^\s*\d+[.、]\s*", "", text)
    text = re.sub(r"\s+", "", text)
    return text
