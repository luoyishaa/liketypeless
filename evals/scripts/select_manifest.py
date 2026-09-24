"""Create a stable, source-balanced subset of an existing manifest."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

from evaluate import read_jsonl
from make_manifest import rank


def select(manifest: Path, per_source: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in read_jsonl(manifest).values():
        groups[row["source"]].append(row)
    result = []
    for source, rows in sorted(groups.items()):
        if len(rows) < per_source:
            raise ValueError(f"{source}: only {len(rows)} samples")
        result.extend(sorted(rows, key=lambda row: rank(row["id"]))[:per_source])
    return sorted(result, key=lambda row: row["id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--per-source", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.per_source < 1:
        parser.error("--per-source must be positive")
    rows = select(args.manifest, args.per_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Selected {len(rows)} samples")


if __name__ == "__main__":
    main()
