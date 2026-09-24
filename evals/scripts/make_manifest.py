"""Create deterministic public-corpus manifests from locally downloaded official data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def rank(identifier: str) -> str:
    return hashlib.sha256(f"20260924:{identifier}".encode()).hexdigest()


def choose(rows: list[dict[str, Any]], count: int, label: str, per_speaker: int | None = None, group_field: str = "speaker") -> list[dict[str, Any]]:
    if per_speaker:
        selected: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for row in sorted(rows, key=lambda item: rank(item["id"])):
            speaker = row.get(group_field, row["id"])
            if counts.get(speaker, 0) < per_speaker:
                selected.append(row)
                counts[speaker] = counts.get(speaker, 0) + 1
            if len(selected) == count:
                break
    else:
        selected = sorted(rows, key=lambda item: rank(item["id"]))[:count]
    if len(selected) < count:
        raise ValueError(f"{label}: requested {count} usable samples but found {len(selected)}")
    return sorted(selected, key=lambda item: item["id"])


def aishell(root: Path, count: int) -> list[dict[str, Any]]:
    data = root / "data_aishell" if (root / "data_aishell").is_dir() else root
    transcript_file = data / "transcript" / "aishell_transcript_v0.8.txt"
    test_root = data / "wav" / "test"
    if not transcript_file.is_file() or not test_root.is_dir():
        raise FileNotFoundError("AISHELL-1 requires data_aishell/transcript/aishell_transcript_v0.8.txt and extracted wav/test")
    transcript = {}
    for line in transcript_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            identifier, text = line.strip().split(maxsplit=1)
            transcript[identifier] = text.replace(" ", "")
    rows = []
    for path in test_root.rglob("*.wav"):
        if path.stem in transcript:
            rows.append({"id": f"aishell-1:{path.stem}", "audio_path": str(path.resolve()), "reference": transcript[path.stem],
                         "source": "aishell-1", "split": "test", "speaker": path.parent.name, "tags": ["read"]})
    return choose(rows, count, "AISHELL-1", per_speaker=max(1, (count + len({row['speaker'] for row in rows}) - 1) // max(len({row['speaker'] for row in rows}), 1)))


def common_voice(root: Path, count: int) -> list[dict[str, Any]]:
    tsv = root / "test.tsv"
    clips = root / "clips"
    if not tsv.is_file() or not clips.is_dir():
        raise FileNotFoundError("Common Voice requires test.tsv and clips/ from the same release")
    rows = []
    with tsv.open(encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle, delimiter="\t"):
            filename = item.get("path", "")
            path = (clips / filename).resolve()
            if path.parent != clips.resolve() or not path.is_file():
                continue
            reference = (item.get("sentence") or item.get("text") or "").strip()
            if not reference:
                continue
            rows.append({"id": f"common-voice-zh-cn:{path.stem}", "audio_path": str(path), "reference": reference,
                         "source": "common-voice-zh-cn", "split": "test", "speaker": item.get("client_id") or path.stem,
                         "tags": ["read"]})
    return choose(rows, count, "Common Voice zh-CN", per_speaker=3)


def fleurs(root: Path, count: int) -> list[dict[str, Any]]:
    """Read Google's headerless FLEURS cmn_hans_cn test.tsv and extracted test/ WAVs."""
    tsv = root / "test.tsv"
    clips = root / "test"
    if not tsv.is_file() or not clips.is_dir():
        raise FileNotFoundError("FLEURS requires test.tsv and extracted test/ WAVs")
    rows = []
    with tsv.open(encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle, delimiter="\t"), 1):
            if len(fields) < 3:
                raise ValueError(f"{tsv}:{line_number}: expected at least 3 TSV columns")
            corpus_id, filename, reference = fields[:3]
            path = (clips / filename).resolve()
            if path.parent != clips.resolve() or not path.is_file() or not reference.strip():
                continue
            rows.append({"id": f"fleurs-cmn-hans-cn:{path.stem}", "audio_path": str(path),
                         "reference": reference.strip(), "source": "fleurs-cmn-hans-cn", "split": "test",
                         "corpus_id": corpus_id, "tags": ["read"]})
    # The first TSV column is a corpus/text ID, not a speaker identifier.
    return choose(rows, count, "FLEURS cmn_hans_cn", per_speaker=3, group_field="corpus_id")


def wenetspeech(root: Path, net_count: int, meeting_count: int) -> list[dict[str, Any]]:
    try:
        import ijson
    except ImportError as exc:
        raise RuntimeError("Install evals/requirements.txt to read WenetSpeech.json") from exc
    metadata = root / "WenetSpeech.json"
    if not metadata.is_file():
        raise FileNotFoundError("WenetSpeech requires WenetSpeech.json")
    buckets: dict[str, list[dict[str, Any]]] = {"TEST_NET": [], "TEST_MEETING": []}
    with metadata.open("rb") as handle:
        for audio in ijson.items(handle, "audios.item"):
            relative = Path(audio["path"])
            path = (root / relative).resolve()
            if not path.is_file():
                continue
            for segment in audio.get("segments", []):
                text = str(segment.get("text", "")).strip()
                start = float(segment.get("begin_time", 0))
                end = float(segment.get("end_time", 0))
                if not text or end <= start:
                    continue
                for split in buckets:
                    if split not in segment.get("subsets", []):
                        continue
                    buckets[split].append({
                        "id": f"wenetspeech:{split.lower()}:{segment['sid']}", "audio_path": str(path), "reference": text,
                        "source": f"wenetspeech-{split.lower()}", "split": split.lower(), "start_seconds": start, "end_seconds": end,
                        "duration_seconds": round(end - start, 3), "tags": ["meeting" if split == "TEST_MEETING" else "internet"],
                    })
    return choose(buckets["TEST_NET"], net_count, "WenetSpeech test_net") + choose(buckets["TEST_MEETING"], meeting_count, "WenetSpeech test_meeting")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aishell-root", type=Path)
    parser.add_argument("--common-voice-root", type=Path)
    parser.add_argument("--fleurs-root", type=Path)
    parser.add_argument("--wenetspeech-root", type=Path)
    parser.add_argument("--include-manifest", type=Path, action="append", default=[], help="Append already prepared JSONL sources")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aishell-count", type=int, default=300)
    parser.add_argument("--common-voice-count", type=int, default=150)
    parser.add_argument("--fleurs-count", type=int, default=150)
    parser.add_argument("--wenet-net-count", type=int, default=75)
    parser.add_argument("--wenet-meeting-count", type=int, default=75)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    if args.aishell_root:
        rows += aishell(args.aishell_root, args.aishell_count)
    if args.common_voice_root:
        rows += common_voice(args.common_voice_root, args.common_voice_count)
    if args.fleurs_root:
        rows += fleurs(args.fleurs_root, args.fleurs_count)
    if args.wenetspeech_root:
        rows += wenetspeech(args.wenetspeech_root, args.wenet_net_count, args.wenet_meeting_count)
    for path in args.include_manifest:
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        parser.error("Provide at least one dataset root")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate IDs across source manifests")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} samples to {args.output}")


if __name__ == "__main__":
    main()
