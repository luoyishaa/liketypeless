"""Stitch disjoint real test clips into controlled >90-second chunking probes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import wave

from evaluate import read_jsonl
from make_manifest import rank
from prepare_audio import file_hash

SILENCE_SECONDS = 0.4


def make_longform(source: Path, output: Path, audio_dir: Path, count: int, minimum_seconds: float) -> list[dict]:
    if count < 1 or minimum_seconds <= 90:
        raise ValueError("Long-form probes must be positive and longer than the 90-second chunk threshold")
    candidates = sorted(read_jsonl(source).values(), key=lambda row: rank(row["id"]))
    audio_dir.mkdir(parents=True, exist_ok=True)
    cursor = 0
    rows = []
    for index in range(count):
        selected = []
        seconds = 0.0
        while seconds < minimum_seconds and cursor < len(candidates):
            sample = candidates[cursor]
            cursor += 1
            selected.append(sample)
            seconds += float(sample["duration_seconds"]) + SILENCE_SECONDS
        if seconds < minimum_seconds:
            raise ValueError(f"Only enough non-overlapping audio for {index} long-form samples")
        target = audio_dir / f"stitched-{index + 1:02d}.wav"
        silence = b"\0\0" * round(16000 * SILENCE_SECONDS)
        with wave.open(str(target), "wb") as output_audio:
            output_audio.setnchannels(1)
            output_audio.setsampwidth(2)
            output_audio.setframerate(16000)
            for sample in selected:
                with wave.open(str(sample["audio_path"]), "rb") as input_audio:
                    if (input_audio.getnchannels(), input_audio.getsampwidth(), input_audio.getframerate()) != (1, 2, 16000):
                        raise ValueError(f"{sample['id']}: input must be 16 kHz mono PCM16")
                    output_audio.writeframes(input_audio.readframes(input_audio.getnframes()))
                output_audio.writeframes(silence)
        with wave.open(str(target), "rb") as check:
            actual_duration = check.getnframes() / check.getframerate()
        ids = [sample["id"] for sample in selected]
        rows.append({"id": f"constructed-longform:{index + 1:02d}", "source": "constructed-longform", "split": "derived-test",
                     "audio_path": str(target.resolve()), "reference": "。".join(sample["reference"] for sample in selected),
                     "duration_seconds": round(actual_duration, 3), "prepared_audio_sha256": file_hash(target),
                     "source_ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
                     "source_ids": ids, "tags": ["synthetic-stitch", "chunking-probe"]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--minimum-seconds", type=float, default=110)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = make_longform(args.manifest, args.output, args.audio_dir, args.count, args.minimum_seconds)
    print(f"Wrote {len(rows)} disjoint long-form probes, {sum(row['duration_seconds'] for row in rows):.1f} audio seconds")


if __name__ == "__main__":
    main()
