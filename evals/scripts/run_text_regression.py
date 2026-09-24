"""Run committed text cases through the product's deterministic conservative rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "local-api"
sys.path.insert(0, str(API_ROOT))
from app.text_structure import structure_text_conservatively  # noqa: E402

from evaluate import read_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hybrid", action="store_true", help="Run Ollama-backed product path; default is deterministic offline fallback")
    arguments = parser.parse_args()
    output = []
    if arguments.hybrid:
        from app.structure_service import structure_text_hybrid
    for sample in read_jsonl(arguments.manifest).values():
        started = perf_counter()
        if arguments.hybrid:
            result = structure_text_hybrid(sample["input_text"])
            row = {"id": sample["id"], "structured_text": result.text, "structure_provider": result.provider,
                   "end_to_end_ms": round((perf_counter() - started) * 1000, 3)}
        else:
            row = {"id": sample["id"], "structured_text": structure_text_conservatively(sample["input_text"])}
        output.append(row)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output), encoding="utf-8")


if __name__ == "__main__":
    main()
