"""Create an auditable human review CSV from manifest and model predictions."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from evaluate import read_jsonl

FIELDS = [
    "id", "reviewer", "source", "audio_path", "reference", "input_text", "asr_text", "structured_text", "protected_terms", "forbidden_phrases",
    "translation_reference", "translation", "asr_faithfulness_1_to_5", "meaning_preserved", "deleted_meaningful_content",
    "added_information", "protected_terms_preserved", "punctuation_appropriate",
    "translation_faithfulness_1_to_5", "translation_naturalness_1_to_5", "notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = read_jsonl(args.manifest)
    predictions = read_jsonl(args.predictions)
    if manifest.keys() != predictions.keys():
        raise ValueError("Manifest and predictions must contain the same IDs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for identifier, sample in manifest.items():
            output = predictions[identifier]
            writer.writerow({
                "id": identifier, "source": sample.get("source", ""), "audio_path": sample.get("audio_path", ""),
                "reference": sample.get("reference", ""),
                "input_text": sample.get("input_text", ""), "asr_text": output.get("asr_text", ""),
                "structured_text": output.get("structured_text", ""),
                "protected_terms": " | ".join(sample.get("protected_terms", [])),
                "forbidden_phrases": " | ".join(sample.get("forbidden_phrases", [])),
                "translation_reference": sample.get("translation_reference", ""),
                "translation": output.get("translation", ""),
            })


if __name__ == "__main__":
    main()
