from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def normalize(text: str) -> str:
    return "".join(character for character in text.lower() if not character.isspace() and character not in "，。！？、；：,.!?;:")


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[right_index] + 1, previous[right_index - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = round((len(values) - 1) * percentile_value)
    return values[index]


def evaluate(manifest: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    matched = [(row, predictions[row_id]) for row_id, row in manifest.items() if row_id in predictions]
    missing = sorted(set(manifest) - set(predictions))
    reference_chars = sum(len(normalize(row["reference"])) for row, _ in matched)
    errors = sum(edit_distance(normalize(row["reference"]), normalize(prediction.get("asr_text", ""))) for row, prediction in matched)
    latencies = [float(prediction["end_to_end_ms"]) for _, prediction in matched if "end_to_end_ms" in prediction]

    protected_total = protected_kept = unsafe_outputs = translation_total = translation_exact = 0
    for row, prediction in matched:
        structured = normalize(prediction.get("structured_text", ""))
        terms = prediction.get("protected_terms", [])
        protected_total += len(terms)
        protected_kept += sum(normalize(term) in structured for term in terms)
        if terms and any(normalize(term) not in structured for term in terms):
            unsafe_outputs += 1
        if "translation_reference" in prediction:
            translation_total += 1
            translation_exact += normalize(prediction.get("translation", "")) == normalize(prediction["translation_reference"])

    return {
        "schema_version": 1,
        "samples": {"manifest": len(manifest), "matched": len(matched), "missing_predictions": missing},
        "asr": {"cer": round(errors / max(reference_chars, 1), 6), "character_errors": errors, "reference_characters": reference_chars},
        "latency_ms": {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95), "count": len(latencies)},
        "safety": {"protected_term_recall": round(protected_kept / max(protected_total, 1), 6), "unsafe_output_rate": round(unsafe_outputs / max(len(matched), 1), 6), "protected_terms": protected_total},
        "translation": {"exact_match_rate": round(translation_exact / max(translation_total, 1), 6), "count": translation_total},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
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
