"""Sample aligned Chinese-English FLORES-200 devtest lines deterministically."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from make_manifest import rank


def make_manifest(root: Path, count: int) -> list[dict[str, str]]:
    base = root / "flores200_dataset" / "devtest"
    if not base.is_dir():
        base = root / "devtest"
    chinese = (base / "zho_Hans.devtest").read_text(encoding="utf-8").splitlines()
    english = (base / "eng_Latn.devtest").read_text(encoding="utf-8").splitlines()
    if len(chinese) != len(english) or not chinese or count < 1 or count > len(chinese):
        raise ValueError("FLORES-200 devtest lines must align and cover the requested sample count")
    indices = sorted(range(len(chinese)), key=lambda index: rank(f"flores200:{index}"))[:count]
    return [{"id": f"flores200-devtest:{index + 1:04d}", "source": "flores200-zho-eng", "split": "devtest",
             "source_text": chinese[index], "translation_reference": english[index]} for index in sorted(indices)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = make_manifest(args.root, args.count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} aligned translation samples")


if __name__ == "__main__":
    main()
