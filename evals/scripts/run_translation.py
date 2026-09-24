"""Run the product's Ollama translation path on a FLORES-200 manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "local-api"
sys.path.insert(0, str(API_ROOT))
from app.translation_service import translate_chinese_to_english  # noqa: E402
from evaluate import read_jsonl  # noqa: E402


def run(manifest: Path, output: Path) -> None:
    samples = read_jsonl(manifest)
    completed = read_jsonl(output) if output.is_file() else {}
    if set(completed) - set(samples):
        raise ValueError("Existing predictions contain IDs outside the manifest")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for sample in samples.values():
            if sample["id"] in completed:
                continue
            started = perf_counter()
            translated, model = translate_chinese_to_english(sample["source_text"])
            row = {"id": sample["id"], "translation": translated, "translation_model": model,
                   "end_to_end_ms": round((perf_counter() - started) * 1000, 3)}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"{len(completed) + 1}/{len(samples)} {sample['id']} {row['end_to_end_ms']} ms", flush=True)
            completed[row["id"]] = row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.manifest, args.output)


if __name__ == "__main__":
    main()
