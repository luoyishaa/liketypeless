"""Exercise authored risk cases through actual structure and translation stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "local-api"))
from app.structure_service import structure_text_hybrid
from app.translation_service import translate_chinese_to_english
from evaluate import evaluate, read_jsonl


def run(manifest: Path, output: Path, report: Path) -> None:
    samples = read_jsonl(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    predictions = {}
    # Fail rather than silently reuse stale predictions after a prompt or model change.
    with output.open("x", encoding="utf-8") as handle:
        for sample in samples.values():
            started = perf_counter()
            structured = structure_text_hybrid(sample["input_text"])
            # Translate the product's structured output: this detects propagated errors too.
            translated, model = translate_chinese_to_english(structured.text)
            row = {"id": sample["id"], "structured_text": structured.text, "translation": translated,
                   "structure_provider": structured.provider, "translation_model": model,
                   "end_to_end_ms": round((perf_counter() - started) * 1000, 3)}
            predictions[row["id"]] = row
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"{len(predictions)}/{len(samples)} {row['id']}", flush=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(evaluate(samples, predictions), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.manifest, args.output, args.report)
