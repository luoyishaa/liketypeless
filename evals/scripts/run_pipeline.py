"""Run real local ASR and optional text stages on a prepared manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "local-api"
sys.path.insert(0, str(API_ROOT))
from app.stt_service import get_stt_provider  # noqa: E402
from app.structure_service import structure_text_hybrid  # noqa: E402
from app.translation_service import translate_chinese_to_english  # noqa: E402
from evaluate import read_jsonl  # noqa: E402


def run(manifest: Path, provider_name: str, include_structure: bool, include_translation: bool, warmup: bool = False) -> list[dict]:
    if include_translation and not include_structure:
        raise ValueError("Translation requires --structure")
    provider = get_stt_provider(provider_name)
    samples = list(read_jsonl(manifest).values())
    if warmup and samples:
        first = samples[0]
        warmup_text = provider.transcribe(Path(first["audio_path"]), language="zh").text
        if include_structure:
            warmup_text = structure_text_hybrid(warmup_text).text
        if include_translation:
            translate_chinese_to_english(warmup_text)
        print("Warm-up completed; its latency is excluded from the scored run.", flush=True)
    outputs = []
    for sample in samples:
        if "reference" not in sample:
            continue
        started = perf_counter()
        transcript = provider.transcribe(Path(sample["audio_path"]), language="zh")
        output = {"id": sample["id"], "asr_text": transcript.text, "stt_ms": transcript.elapsed_ms,
                  "stt_provider": transcript.provider, "stt_model": transcript.model}
        if include_structure:
            result = structure_text_hybrid(transcript.text)
            output["structured_text"] = result.text
            output["structure_provider"] = result.provider
        if include_translation:
            output["translation"], output["translation_model"] = translate_chinese_to_english(output["structured_text"])
        output["end_to_end_ms"] = round((perf_counter() - started) * 1000, 3)
        outputs.append(output)
        print(f"{len(outputs)} {sample['id']} {output['end_to_end_ms']} ms", flush=True)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", default="local-faster-whisper")
    parser.add_argument("--structure", action="store_true")
    parser.add_argument("--translation", action="store_true")
    parser.add_argument("--warmup", action="store_true", help="Prime all selected stages before timed samples")
    args = parser.parse_args()
    outputs = run(args.manifest, args.provider, args.structure, args.translation, args.warmup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in outputs), encoding="utf-8")


if __name__ == "__main__":
    main()
