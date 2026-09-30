"""Select an audio- and speaker-disjoint ASR holdout from prepared manifests."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate import normalize, read_jsonl
from make_manifest import rank


def select_holdout(candidates: Iterable[dict[str, Any]], baseline: Iterable[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("Holdout count must be positive")
    candidates = list(candidates)
    previous = list(baseline)
    for row in candidates:
        if not row.get("speaker"):
            raise ValueError(f"{row.get('id')}: speaker metadata is required for a speaker-disjoint holdout")
        if not row.get("source_audio_sha256"):
            raise ValueError(f"{row.get('id')}: source_audio_sha256 is required for an audio-disjoint holdout")
    candidate_sources = {row.get("source") for row in candidates}
    for row in previous:
        if row.get("source") in candidate_sources and not row.get("speaker"):
            raise ValueError(f"{row.get('id')}: baseline speaker metadata is missing")
    excluded_ids = {row["id"] for row in previous}
    excluded_speakers = {(row.get("source"), row["speaker"]) for row in previous if row.get("speaker")}
    excluded_audio = {row["source_audio_sha256"] for row in previous if row.get("source_audio_sha256")}
    eligible = [row for row in candidates if row["id"] not in excluded_ids
                and (row.get("source"), row.get("speaker")) not in excluded_speakers
                and row.get("source_audio_sha256") not in excluded_audio]
    selected = sorted(eligible, key=lambda row: rank(row["id"]))[:count]
    if len(selected) < count:
        raise ValueError(f"Holdout needs {count} disjoint recordings, found {len(selected)}")
    return sorted(selected, key=lambda row: row["id"])


def portable_hash(rows: Iterable[dict[str, Any]]) -> str:
    portable = {row["id"]: {key: value for key, value in row.items() if key != "audio_path"} for row in rows}
    return hashlib.sha256(json.dumps(portable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True, help="Prepared source manifest with speaker and audio hashes")
    parser.add_argument("--exclude", type=Path, action="append", default=[], help="Previously used manifest; repeat as needed")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--max-reference-chars", type=int, help="Optional short-utterance stratum")
    parser.add_argument("--source-revision", required=True, help="Pinned publisher revision or archive SHA-256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    if args.max_reference_chars is not None and args.max_reference_chars < 1:
        parser.error("--max-reference-chars must be positive")
    if args.output.exists() or args.lock.exists():
        parser.error("Holdout is already frozen; use new output paths rather than replacing it")
    candidates = list(read_jsonl(args.candidate).values())
    if args.max_reference_chars is not None:
        candidates = [row for row in candidates if 0 < len(normalize(row["reference"])) <= args.max_reference_chars]
    excluded = [row for path in args.exclude for row in read_jsonl(path).values()]
    selected = select_holdout(candidates, excluded, args.count)
    if len({row["source_audio_sha256"] for row in selected}) != len(selected):
        raise ValueError("Selected holdout contains duplicate source audio")
    lock = {
        "schema_version": 1,
        "sample_count": len(selected),
        "speaker_count": len({(row["source"], row["speaker"]) for row in selected}),
        "source_revision": args.source_revision,
        "source_splits": sorted({f"{row['source']}:{row.get('split', 'unknown')}" for row in selected}),
        "manifest_sha256": portable_hash(selected),
        "excluded_manifest_sha256": portable_hash(excluded),
        "selection_seed": "20260924",
        "max_reference_chars": args.max_reference_chars,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    args.lock.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(lock, ensure_ascii=False))


if __name__ == "__main__":
    main()
