from __future__ import annotations

from dataclasses import dataclass
import re

from .config import settings
from .ollama_client import OllamaError, generate_chat_text
from .text_structure import PROVIDER_NAME as RULES_PROVIDER
from .text_structure import ensure_terminal_punctuation, structure_text_conservatively


HYBRID_PROVIDER_NAME = "hybrid-conservative-llm"

SYSTEM_PROMPT = """你是一个保守的中文语音输入整理器。

目标：把语音识别文本整理成可直接粘贴的文本。

只允许做：
1. 去掉口头禅、无意义停顿词和重复连接词。
2. 修正明显的语音识别错字。
3. 必须补充中文标点：完整陈述句以“。”结束，明确疑问以“？”结束，明确感叹才使用“！”；连续分句之间使用“，”。
4. 保留用户已有的“第一、第二、另外、最后”等结构。

禁止做：
1. 总结、扩写、润色、改写观点。
2. 添加用户没有说的信息。
3. 改变用户语气。
4. 把普通输入改写成总结、标题或提纲。
5. 删除有实际意义的句子。

输出要求：
- 只输出整理后的正文，不要解释。
- 不要使用 Markdown 代码块。
- 除去口头填充词和明显重复后，保留原本意思和措辞。
- 如果原文已经有编号，保留编号；如果出现“第一、第二”等结构，按行编号。
- 即使原文没有标点，也要按照语义补充标点。"""


@dataclass(frozen=True)
class StructureResult:
    provider: str
    text: str


def structure_text_hybrid(text: str, timeout: float = 120) -> StructureResult:
    rules_text = structure_text_conservatively(text)
    if not rules_text:
        return StructureResult(provider=RULES_PROVIDER, text="")

    try:
        llm_text = generate_chat_text(model=settings.default_model, system_prompt=SYSTEM_PROMPT, user_text=rules_text, timeout=timeout)
    except OllamaError:
        return StructureResult(provider=RULES_PROVIDER, text=rules_text)

    llm_text = ensure_terminal_punctuation(llm_text)
    if not _is_safe_result(source=rules_text, candidate=llm_text):
        return StructureResult(provider=RULES_PROVIDER, text=rules_text)

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

    forbidden_markers = ("我认为", "总结", "以下是", "整理如下", "标题：")
    if any(marker in candidate for marker in forbidden_markers):
        return False

    return _keeps_source_clauses(source, candidate)


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
