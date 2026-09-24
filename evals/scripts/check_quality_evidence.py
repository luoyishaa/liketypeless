"""Require public benchmark reports for changes to the product's inference path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from compare_baseline import compare

CORE_FILES = {
    "apps/local-api/app/config.py",
    "apps/local-api/app/ollama_client.py",
    "apps/local-api/app/main.py",
    "apps/local-api/app/prompts.py",
    "apps/local-api/app/stt_service.py",
    "apps/local-api/app/structure_service.py",
    "apps/local-api/app/text_structure.py",
    "apps/local-api/app/translation_service.py",
    "apps/local-api/scripts/sensevoice_runner.py",
    "apps/local-api/requirements.txt",
    "apps/desktop/src/renderer/main.tsx",
}
CORE_PREFIXES = ("apps/desktop/src/main/", "apps/desktop/src/preload/", "packages/shared/src/")
TRANSLATION_FILES = {"apps/local-api/app/translation_service.py", "apps/local-api/app/ollama_client.py", "apps/local-api/app/config.py"}


def require_comparison(baseline_path: Path, candidate_path: Path, changed: set[str], label: str) -> None:
    if not baseline_path.is_file() or not candidate_path.is_file() or candidate_path.as_posix() not in changed:
        raise SystemExit(f"{label}: rerun and update {candidate_path.as_posix()} using the fixed baseline manifest.")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    summary, unsafe = compare(baseline, candidate)
    print(f"\n{label}:\n{summary}")
    if baseline["prediction_sha256"] == candidate["prediction_sha256"] or unsafe:
        raise SystemExit(f"{label}: predictions must be rerun and must pass the safety regression gate.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--baseline", type=Path, default=Path("evals/reports/public-baseline.json"))
    parser.add_argument("--candidate", type=Path, default=Path("evals/reports/public-candidate.json"))
    parser.add_argument("--longform-baseline", type=Path, default=Path("evals/reports/constructed-longform-baseline.json"))
    parser.add_argument("--longform-candidate", type=Path, default=Path("evals/reports/constructed-longform-fixed.json"))
    args = parser.parse_args()
    changed = set(subprocess.check_output(["git", "diff", "--name-only", args.base_ref, "HEAD"], text=True).splitlines())
    core_changes = {path for path in changed if path in CORE_FILES or path.startswith(CORE_PREFIXES)}
    if not core_changes:
        print("No model, prompt, or core inference changes; public benchmark report is not required.")
        return
    if not args.baseline.is_file() or not args.candidate.is_file():
        raise SystemExit(
            "Core inference files changed. Commit comparable public-baseline.json and public-candidate.json reports "
            "from the same fixed manifest, then rerun this check. Changed: " + ", ".join(sorted(core_changes))
        )
    candidate_path = args.candidate.as_posix()
    if candidate_path not in changed:
        raise SystemExit(f"Core inference changed, but {candidate_path} was not updated in this change set.")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    summary, unsafe = compare(baseline, candidate)
    print(summary)
    if baseline["prediction_sha256"] == candidate["prediction_sha256"]:
        raise SystemExit("Candidate predictions are identical to baseline; rerun the changed inference path.")
    if unsafe:
        raise SystemExit("Automatic safety gate failed.")
    if core_changes & {"apps/local-api/app/stt_service.py", "apps/local-api/scripts/sensevoice_runner.py", "apps/local-api/requirements.txt"}:
        longform_path = args.longform_candidate.as_posix()
        if not args.longform_baseline.is_file() or not args.longform_candidate.is_file() or longform_path not in changed:
            raise SystemExit("ASR implementation changed; update the long-form candidate report on the fixed probe set.")
        longform_baseline = json.loads(args.longform_baseline.read_text(encoding="utf-8"))
        longform_candidate = json.loads(args.longform_candidate.read_text(encoding="utf-8"))
        longform_summary, longform_unsafe = compare(longform_baseline, longform_candidate)
        print("\nLong-form chunking comparison:\n" + longform_summary)
        if longform_baseline["prediction_sha256"] == longform_candidate["prediction_sha256"] or longform_unsafe:
            raise SystemExit("Long-form predictions must be rerun and must pass the safety gate.")
    if core_changes & TRANSLATION_FILES:
        require_comparison(Path("evals/reports/flores200-qwen3-baseline.json"), Path("evals/reports/flores200-qwen3-candidate.json"), changed, "Public translation comparison")
        require_comparison(Path("evals/reports/high-risk-text-before.json"), Path("evals/reports/high-risk-text-candidate.json"), changed, "High-risk text comparison")


if __name__ == "__main__":
    main()
