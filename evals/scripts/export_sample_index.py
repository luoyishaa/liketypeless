"""Publish an audio sample index without transcripts or machine-specific paths."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from evaluate import read_jsonl

FIELDS = ("id", "source", "split", "speaker", "duration_seconds", "source_audio_sha256", "prepared_audio_sha256", "audio_channel")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_jsonl(args.manifest)
    if any(not row.get("prepared_audio_sha256") for row in rows.values()):
        raise ValueError("Publish only prepared manifests with audio hashes")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps({key: row[key] for key in FIELDS if key in row}, ensure_ascii=False) + "\n"
                                  for row in rows.values()), encoding="utf-8")
