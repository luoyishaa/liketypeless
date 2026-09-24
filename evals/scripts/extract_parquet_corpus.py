"""Extract deterministic ASR samples from an openly hosted test-only Parquet mirror."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from make_manifest import choose
from evaluate import normalize, read_jsonl


def metadata_rows(files: list[Path], corpus: str) -> list[dict]:
    rows = []
    for shard in files:
        parquet = pq.ParquetFile(shard)
        columns = ["name", "WavPath", "text"] if corpus == "aishell-1" else ["client_id", "path", "sentence"]
        for batch in parquet.iter_batches(batch_size=256, columns=columns):
            for row in batch.to_pylist():
                if corpus == "aishell-1":
                    identifier, path, reference = row["name"], row["WavPath"], row["text"]
                    if not path.replace("\\", "/").startswith("test/"):
                        raise ValueError(f"Non-test AISHELL-1 row: {path}")
                    speaker = identifier[6:11]
                    label = f"aishell-1:{identifier}"
                else:
                    identifier = Path(row["path"].replace("\\", "/")).stem
                    speaker = row.get("client_id") or identifier
                    reference = row["sentence"]
                    label = f"common-voice-zh-cn:{identifier}"
                if reference and identifier:
                    rows.append({"id": label, "speaker": speaker, "reference": reference.replace(" ", "") if corpus == "aishell-1" else reference,
                                 "source": corpus, "split": "test", "tags": ["read"]})
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Parquet mirror has duplicate IDs")
    return rows


def extract(files: list[Path], corpus: str, count: int, output: Path, audio_dir: Path,
            max_reference_chars: int | None = None, exclude_manifest: Path | None = None) -> int:
    if count < 1 or (max_reference_chars is not None and max_reference_chars < 1):
        raise ValueError("Sample count and maximum reference length must be positive")
    rows = metadata_rows(files, corpus)
    excluded = read_jsonl(exclude_manifest) if exclude_manifest else {}
    rows = [row for row in rows if row["id"] not in excluded and
            (max_reference_chars is None or 0 < len(normalize(row["reference"])) <= max_reference_chars)]
    if not rows:
        raise ValueError("No samples satisfy the reference-length and exclusion filters")
    speaker_limit = max(1, (count + len({row["speaker"] for row in rows}) - 1) // len({row["speaker"] for row in rows})) if corpus == "aishell-1" else 3
    selected = choose(rows, count, corpus, per_speaker=speaker_limit)
    selected_by_id = {row["id"]: row for row in selected}
    audio_dir.mkdir(parents=True, exist_ok=True)
    found = set()
    for shard in files:
        for batch in pq.ParquetFile(shard).iter_batches(batch_size=64):
            for row in batch.to_pylist():
                identifier = row["name"] if corpus == "aishell-1" else Path(row["path"].replace("\\", "/")).stem
                label = f"{corpus}:{identifier}"
                if label not in selected_by_id:
                    continue
                audio = row["audio"]
                if not isinstance(audio, dict) or not audio.get("bytes"):
                    raise ValueError(f"Missing embedded audio: {label}")
                suffix = ".wav" if corpus == "aishell-1" else ".mp3"
                target = audio_dir / f"{identifier}{suffix}"
                target.write_bytes(audio["bytes"])
                selected_by_id[label]["audio_path"] = str(target.resolve())
                found.add(label)
    if found != set(selected_by_id):
        raise ValueError(f"Missing selected audio: {sorted(set(selected_by_id) - found)[:5]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=("aishell-1", "common-voice-zh-cn"), required=True)
    parser.add_argument("--shards", type=Path, nargs="+", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--max-reference-chars", type=int)
    parser.add_argument("--exclude-manifest", type=Path)
    args = parser.parse_args()
    print(f"Extracted {extract(args.shards, args.corpus, args.count, args.output, args.audio_dir, args.max_reference_chars, args.exclude_manifest)} samples")


if __name__ == "__main__":
    main()
