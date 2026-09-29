"""Verify the product's complete pinned-model download against the official source."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "local-api"))
from app.model_manager import FILES, ModelManager  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--report", type=Path)
args = parser.parse_args()
manager = ModelManager(args.directory)
if manager.status()["state"] not in ("ready", "verifying"):
    manager.prepare()
last_bucket = -1
while True:
    status = manager.status()
    if status["state"] in ("ready", "error"):
        print(json.dumps(status, ensure_ascii=False), flush=True)
        if status["state"] == "error":
            raise SystemExit(1)
        if args.report:
            result = {"source": "https://huggingface.co", "revision": status["revision"],
                      "totalBytes": status["totalBytes"], "verified": True,
                      "files": {name: {"bytes": (args.directory / name).stat().st_size,
                                       "digest": spec[2]} for name, spec in FILES.items()}}
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        break
    bucket = status["downloadedBytes"] // 25000000
    if bucket != last_bucket:
        print(f"{status['downloadedBytes']}/{status['totalBytes']} bytes", flush=True)
        last_bucket = bucket
    time.sleep(0.5)
