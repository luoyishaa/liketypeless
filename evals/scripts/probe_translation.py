"""Repeat a real annotated translation contract; exit nonzero on an observed violation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "local-api"))
from app.translation_service import translate_chinese_to_english
from evaluate import read_jsonl, translation_violations


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    sample = read_jsonl(args.manifest)[args.id]
    if not (sample.get("translation_required_any") or sample.get("translation_verbatim_terms")):
        raise ValueError("Sample has no annotated translation checks")
    failed = False
    for trial in range(args.repeats):
        text, _ = translate_chinese_to_english(sample["source_text"] + "。")
        violations = translation_violations(sample, text)
        failed |= bool(violations)
        print(json.dumps({"trial": trial + 1, "text": text, "violations": violations}, ensure_ascii=False), flush=True)
    raise SystemExit(1 if failed else 0)
