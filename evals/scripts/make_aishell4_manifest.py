"""Sample annotated AISHELL-4 meeting utterances from official test TextGrids."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from make_manifest import choose

INTERVAL = re.compile(r"^\s*intervals \[\d+\]:")
ANNOTATION = re.compile(r"<[^>]*>")


def read_textgrid(path: Path) -> list[tuple[str, float, float, str]]:
    speaker = ""
    current: dict[str, float] | None = None
    rows: list[tuple[str, float, float, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if stripped.startswith("name = "):
            speaker = stripped.partition("=")[2].strip().strip('"')
        elif INTERVAL.match(line):
            current = {}
        elif current is not None and stripped.startswith("xmin = "):
            current["start"] = float(stripped.partition("=")[2])
        elif current is not None and stripped.startswith("xmax = "):
            current["end"] = float(stripped.partition("=")[2])
        elif current is not None and stripped.startswith("text = "):
            raw = stripped.partition("=")[2].strip().strip('"').replace('""', '"')
            text = ANNOTATION.sub("", raw).strip()
            if text and current.get("end", 0) > current.get("start", 0):
                rows.append((speaker, current["start"], current["end"], text))
            current = None
    return rows


def make_manifest(root: Path, count: int, allow_overlap: bool = False) -> list[dict]:
    data = root / "test" if (root / "test").is_dir() else root
    grids = sorted((data / "TextGrid").glob("*.TextGrid"))
    if not grids:
        raise FileNotFoundError("AISHELL-4 requires test/TextGrid/*.TextGrid and matching test/wav/*.flac")
    rows = []
    for grid in grids:
        audio = data / "wav" / f"{grid.stem}.flac"
        if not audio.is_file():
            continue
        intervals = read_textgrid(grid)
        for number, (speaker, start, end, reference) in enumerate(intervals):
            if end - start < 0.5:
                continue
            overlap = sum(max(0.0, min(end, other_end) - max(start, other_start))
                          for other_speaker, other_start, other_end, _ in intervals if other_speaker != speaker)
            if overlap > 0.1 and not allow_overlap:
                continue
            rows.append({"id": f"aishell-4:{grid.stem}:{speaker}:{number}", "audio_path": str(audio.resolve()),
                         "reference": reference, "source": "aishell-4-meeting", "split": "test",
                         "speaker": f"{grid.stem}:{speaker}", "start_seconds": start, "end_seconds": end,
                         "duration_seconds": round(end - start, 3), "overlap_seconds": round(overlap, 3),
                         "tags": ["meeting", "far-field", "overlap" if overlap > 0.1 else "single-speaker"]})
    if not rows:
        raise ValueError("No annotated AISHELL-4 utterances with matching audio")
    speakers = len({row["speaker"] for row in rows})
    return choose(rows, count, "AISHELL-4 test", per_speaker=max(3, math.ceil(count / speakers) + 2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--allow-overlap", action="store_true", help="Diagnostic only: per-speaker CER becomes ambiguous")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = make_manifest(args.root, args.count, args.allow_overlap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} meeting utterances")


if __name__ == "__main__":
    main()
