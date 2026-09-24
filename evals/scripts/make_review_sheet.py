"""Create an auditable human review CSV from manifest and model predictions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from evaluate import read_jsonl

FIELDS = [
    "id", "reviewer", "source", "audio_path", "reference", "input_text", "asr_text", "structured_text", "protected_terms", "forbidden_phrases",
    "translation_reference", "translation", "asr_faithfulness_1_to_5", "meaning_preserved", "deleted_meaningful_content",
    "added_information", "protected_terms_preserved", "punctuation_appropriate",
    "translation_faithfulness_1_to_5", "translation_naturalness_1_to_5", "notes",
]


def review_rows(manifest: dict, predictions: dict) -> list[dict]:
    if not manifest or manifest.keys() != predictions.keys():
        raise ValueError("Nonempty manifest and predictions must contain the same IDs")
    rows = []
    for identifier, sample in manifest.items():
        output = predictions[identifier]
        rows.append({
            "id": identifier, "source": sample.get("source", ""), "audio_path": sample.get("audio_path", ""),
            "reference": sample.get("reference", ""),
            "input_text": sample.get("input_text", sample.get("source_text", "")), "asr_text": output.get("asr_text", ""),
            "structured_text": output.get("structured_text", ""),
            "protected_terms": " | ".join([*sample.get("protected_terms", []), *sample.get("verbatim_terms", [])]),
            "forbidden_phrases": " | ".join(sample.get("forbidden_phrases", [])),
            "translation_reference": sample.get("translation_reference", ""), "translation": output.get("translation", ""),
        })
    return rows


def write_html(path: Path, rows: list[dict], predictions: dict) -> None:
    payload = []
    for row in rows:
        output = predictions[row["id"]]
        payload.append({**row, "audio_url": Path(row["audio_path"]).resolve().as_uri() if row["audio_path"] else "",
                        "stages": [name for name, field in (("asr", "asr_text"), ("structure", "structured_text"), ("translation", "translation")) if field in output]})
    encoded = json.dumps({"rows": payload, "fields": FIELDS}, ensure_ascii=False).replace("<", "\\u003c")
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    template = (Path(__file__).resolve().parents[1] / "review" / "review.html").read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.replace("__REVIEW_DATA__", encoded).replace("__REVIEW_FINGERPRINT__", fingerprint), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--html", type=Path, help="Optional local listening/scoring page with CSV export")
    args = parser.parse_args()
    manifest = read_jsonl(args.manifest)
    predictions = read_jsonl(args.predictions)
    rows = review_rows(manifest, predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if args.html:
        write_html(args.html, rows, predictions)


if __name__ == "__main__":
    main()
