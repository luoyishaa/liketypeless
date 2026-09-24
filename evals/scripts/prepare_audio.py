"""Convert a manifest's clips to local 16 kHz mono PCM WAV files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

from evaluate import read_jsonl


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(manifest: Path, output: Path, cache: Path, channel: int | None = None) -> int:
    from imageio_ffmpeg import get_ffmpeg_exe

    rows = read_jsonl(manifest)
    if channel is not None and channel < 0:
        raise ValueError("Channel index must be nonnegative")
    cache.mkdir(parents=True, exist_ok=True)
    prepared = []
    source_hashes: dict[Path, str] = {}
    for row in rows.values():
        source = Path(row["audio_path"])
        if not source.is_file():
            raise FileNotFoundError(f"{row['id']}: {source}")
        if source not in source_hashes:
            source_hashes[source] = file_hash(source)
        cache_identity = f"{source.resolve()}:{source.stat().st_size}:{source.stat().st_mtime_ns}:{row.get('start_seconds')}:{row.get('end_seconds')}"
        if channel is not None:
            cache_identity += f":channelmap={channel}"
        key = hashlib.sha256(cache_identity.encode()).hexdigest()
        target = cache / f"{key}.wav"
        if not target.is_file():
            partial = cache / f"{key}.partial.wav"
            command = [get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"]
            if "start_seconds" in row:
                command += ["-ss", str(row["start_seconds"])]
            command += ["-i", str(source)]
            if "start_seconds" in row:
                command += ["-t", str(float(row["end_seconds"]) - float(row["start_seconds"]))]
            if channel is not None:
                command += ["-af", f"channelmap=map={channel}:channel_layout=mono"]
            command += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(partial)]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        with wave.open(str(target), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getframerate() != 16000 or handle.getsampwidth() != 2:
                raise ValueError(f"{target}: expected 16 kHz mono PCM16")
            duration = handle.getnframes() / handle.getframerate()
        if duration <= 0:
            raise ValueError(f"{row['id']}: empty audio")
        prepared.append({**row, "audio_path": str(target.resolve()), "source_audio_sha256": source_hashes[source],
                         "prepared_audio_sha256": file_hash(target),
                         "duration_seconds": round(duration, 3)})
        prepared[-1].pop("start_seconds", None)
        prepared[-1].pop("end_seconds", None)
        if channel is not None:
            prepared[-1]["audio_channel"] = channel
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prepared), encoding="utf-8")
    return len(prepared)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--channel", type=int, help="Select one zero-based source channel instead of downmixing; use a separate diagnostic manifest")
    args = parser.parse_args()
    print(f"Prepared {prepare(args.manifest, args.output, args.cache, args.channel)} audio samples")


if __name__ == "__main__":
    main()
