"""Evaluate predictions against a fixed JSONL manifest."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import re
from pathlib import Path
import unicodedata
from typing import Any

def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{path}:{number}: missing id")
        if identifier in rows:
            raise ValueError(f"{path}:{number}: duplicate id {identifier}")
        rows[identifier] = row
    return rows


def normalize(text: str) -> str:
    return "".join(
        char.casefold() for char in unicodedata.normalize("NFKC", text)
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def normalize_protected(text: str) -> str:
    """Safety matching keeps decimal points, signs, and path separators meaningful."""
    ignored = set("，。！？；：,!?;:")
    return "".join(char.casefold() for char in unicodedata.normalize("NFKC", text)
                   if not char.isspace() and char not in ignored)


def translation_violations(sample: dict, text: str) -> list[str]:
    """Narrow annotated lexical checks, not an automatic semantic judgement."""
    failures = []
    for term in sample.get("translation_verbatim_terms", []):
        if not term or term not in text:
            failures.append(f"verbatim:{term}")
    for alternatives in sample.get("translation_required_any", []):
        if not alternatives or any(not term.strip() for term in alternatives):
            raise ValueError("Translation alternatives must contain nonempty terms")
        if not any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE) for term in alternatives):
            failures.append("any:" + "|".join(alternatives))
    return failures


def edit_distance(reference: str, hypothesis: str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for index, reference_char in enumerate(reference, 1):
        current = [index]
        for position, hypothesis_char in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[position] + 1, previous[position - 1] + (reference_char != hypothesis_char)))
        previous = current
    return previous[-1]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def duration_bucket(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 10:
        return "lt10s"
    if seconds < 30:
        return "10to30s"
    return "gte30s"


def reference_length_bucket(text: str) -> str:
    length = len(normalize(text))
    if length < 5:
        return "lt5chars"
    if length < 20:
        return "5to19chars"
    return "gte20chars"


def _summarize(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    asr_rows = [(sample, output) for sample, output in rows if "reference" in sample]
    characters = sum(len(normalize(sample["reference"])) for sample, _ in asr_rows)
    errors = sum(edit_distance(normalize(sample["reference"]), normalize(output["asr_text"])) for sample, output in asr_rows)
    latencies = [float(output["end_to_end_ms"]) for _, output in rows if "end_to_end_ms" in output]
    audio_seconds = sum(float(sample.get("duration_seconds", 0)) for sample, _ in asr_rows)
    asr_ms = sum(float(output.get("stt_ms", 0)) for _, output in asr_rows)
    human_asr_scores = [float(output["human_review"]["asr_faithfulness_1_to_5"])
                        for _, output in asr_rows if isinstance(output.get("human_review"), dict)
                        and "asr_faithfulness_1_to_5" in output["human_review"]]
    return {
        "samples": len(rows),
        "asr": {"cer": ratio(errors, characters), "character_errors": errors, "reference_characters": characters,
                "samples": len(asr_rows), "human_reviewed": len(human_asr_scores),
                "human_faithfulness_mean_1_to_5": round(sum(human_asr_scores) / len(human_asr_scores), 3) if human_asr_scores else None},
        "latency_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95), "samples": len(latencies)},
        "asr_real_time_factor": round(asr_ms / 1000 / audio_seconds, 6) if audio_seconds and asr_ms else None,
    }


def evaluate(manifest: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not manifest:
        raise ValueError("Manifest is empty")
    missing = sorted(set(manifest) - set(predictions))
    extras = sorted(set(predictions) - set(manifest))
    if missing or extras:
        raise ValueError(f"Prediction IDs must match manifest: missing={missing[:10]}, extra={extras[:10]}")
    rows = [(sample, predictions[identifier]) for identifier, sample in manifest.items()]
    for sample, output in rows:
        if output.get("error"):
            raise ValueError(f"{sample['id']}: inference error: {output['error']}")
        for condition, field in (("reference", "asr_text"), ("input_text", "structured_text"), ("translation_reference", "translation")):
            if condition in sample and not isinstance(output.get(field), str):
                raise ValueError(f"{sample['id']}: missing {field}")
        if "reference" in sample and not normalize(sample["reference"]):
            raise ValueError(f"{sample['id']}: empty normalized ASR reference")
        if "reference" in sample and (not isinstance(output.get("stt_ms"), (int, float)) or not math.isfinite(output["stt_ms"]) or output["stt_ms"] < 0):
            raise ValueError(f"{sample['id']}: missing or invalid stt_ms")
        if ("reference" in sample or "translation_reference" in sample) and "end_to_end_ms" not in output:
            raise ValueError(f"{sample['id']}: missing end_to_end_ms")
        if "end_to_end_ms" in output and (not isinstance(output["end_to_end_ms"], (int, float)) or not math.isfinite(output["end_to_end_ms"]) or output["end_to_end_ms"] < 0):
            raise ValueError(f"{sample['id']}: invalid end_to_end_ms")

    by_source: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    by_duration: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    by_reference_length: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    protected_count = kept_count = unsafe_count = structure_count = 0
    unsafe_ids: list[str] = []
    translation_pairs: list[tuple[str, str]] = []
    translation_checked = 0
    translation_unsafe_ids = []
    human_review_count = human_faithful_count = 0
    translation_faithfulness_scores: list[float] = []
    translation_naturalness_scores: list[float] = []
    for sample, output in rows:
        by_source[str(sample.get("source", "unknown"))].append((sample, output))
        if "reference" in sample:
            by_duration[duration_bucket(sample.get("duration_seconds"))].append((sample, output))
            by_reference_length[reference_length_bucket(sample["reference"])].append((sample, output))
        if "input_text" in sample:
            structure_count += 1
            structured = normalize_protected(output["structured_text"])
            required = sample.get("protected_terms", [])
            forbidden = sample.get("forbidden_phrases", [])
            verbatim = sample.get("verbatim_terms", [])
            if any(not normalize_protected(term) for term in [*required, *forbidden, *verbatim]):
                raise ValueError(f"{sample['id']}: empty protected or forbidden term")
            protected_count += len(required) + len(verbatim)
            kept_count += sum(normalize_protected(term) in structured for term in required) + sum(term in output["structured_text"] for term in verbatim)
            violation = (any(normalize_protected(term) not in structured for term in required)
                         or any(normalize_protected(term) in structured for term in forbidden)
                         or any(term not in output["structured_text"] for term in verbatim))
            if violation:
                unsafe_count += 1
                unsafe_ids.append(sample["id"])
        if "translation_reference" in sample:
            translation_pairs.append((output["translation"], sample["translation_reference"]))
            if sample.get("translation_verbatim_terms") or sample.get("translation_required_any"):
                translation_checked += 1
                if translation_violations(sample, output["translation"]):
                    translation_unsafe_ids.append(sample["id"])
        review = output.get("human_review")
        if isinstance(review, dict):
            if "input_text" in sample:
                human_review_count += 1
                if (review.get("meaning_preserved") is True and review.get("added_information") is False
                        and review.get("deleted_meaningful_content") is False
                        and review.get("protected_terms_preserved") is True):
                    human_faithful_count += 1
            if "translation_reference" in sample and "translation_faithfulness_1_to_5" in review:
                translation_faithfulness_scores.append(float(review["translation_faithfulness_1_to_5"]))
            if "translation_reference" in sample and "translation_naturalness_1_to_5" in review:
                translation_naturalness_scores.append(float(review["translation_naturalness_1_to_5"]))

    chrf = None
    if translation_pairs:
        from sacrebleu.metrics import CHRF
        hypotheses, references = zip(*translation_pairs)
        chrf = round(CHRF(word_order=2).corpus_score(list(hypotheses), [list(references)]).score, 4)
    portable_manifest = {identifier: {key: value for key, value in sample.items() if key != "audio_path"}
                         for identifier, sample in manifest.items()}
    return {
        "schema_version": 4,
        "manifest_sha256": hashlib.sha256(json.dumps(portable_manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "prediction_sha256": hashlib.sha256(json.dumps(predictions, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "sample_count": len(rows),
        "overall": _summarize(rows),
        "by_source": {key: _summarize(value) for key, value in sorted(by_source.items())},
        "by_duration": {key: _summarize(value) for key, value in sorted(by_duration.items())},
        "by_reference_length": {key: _summarize(value) for key, value in sorted(by_reference_length.items())},
        "safety": {
            "structure_samples": structure_count,
            "protected_term_recall": ratio(kept_count, protected_count),
            "protected_terms": protected_count,
            "automatic_violation_rate": ratio(unsafe_count, structure_count),
            "automatic_violation_ids": unsafe_ids,
            "human_reviewed": human_review_count,
            "human_faithful_rate": ratio(human_faithful_count, human_review_count),
        },
        "translation": {
            "samples": len(translation_pairs), "chrf_plus_plus": chrf,
            "automatic_checked_samples": translation_checked,
            "automatic_violation_rate": ratio(len(translation_unsafe_ids), translation_checked),
            "automatic_violation_ids": translation_unsafe_ids,
            "human_reviewed": len(translation_faithfulness_scores),
            "human_faithfulness_mean_1_to_5": round(sum(translation_faithfulness_scores) / len(translation_faithfulness_scores), 3) if translation_faithfulness_scores else None,
            "human_naturalness_mean_1_to_5": round(sum(translation_naturalness_scores) / len(translation_naturalness_scores), 3) if translation_naturalness_scores else None,
        },
        "limitations": ["Automatic structure checks cover annotated terms and forbidden phrases; semantic fidelity requires human review."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = evaluate(read_jsonl(arguments.manifest), read_jsonl(arguments.predictions))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
