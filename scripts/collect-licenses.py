"""Generate dependency inventory and retain license texts in the build output."""
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil

root = Path(__file__).resolve().parents[1]
destination = root / "dist" / "third-party-licenses"
destination.mkdir(parents=True, exist_ok=True)
packages = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s]+)", (root / "apps/local-api/requirements-release.lock").read_text(), re.M)
inventory = []
for name, version in packages:
    distribution = metadata.distribution(name)
    if distribution.version != version:
        raise RuntimeError(f"Release lock mismatch: {name} expected {version}, installed {distribution.version}")
    entry = {"name": name, "version": version,
             "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See included license texts / upstream metadata",
             "files": []}
    for file in distribution.files or []:
        if re.search(r"(^|[/_.-])(licen[cs]e|copying|notice|eula)", str(file), re.I):
            source = Path(distribution.locate_file(file))
            if source.is_file() and source.stat().st_size < 2_000_000:
                target = destination / name / str(file).replace("..", "_").replace(":", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                entry["files"].append(str(target.relative_to(destination)))
    inventory.append(entry)
for name in ("react", "react-dom", "scheduler", "electron"):
    directory = root / "node_modules" / name
    package = json.loads((directory / "package.json").read_text())
    target = destination / ("npm-" + name)
    target.mkdir(exist_ok=True)
    retained = []
    for source in directory.glob("LICENSE*"):
        if source.is_file():
            shutil.copyfile(source, target / source.name)
            retained.append(str((target / source.name).relative_to(destination)))
    inventory.append({"name": name, "version": package["version"], "license": package.get("license"), "files": retained})
runtime_license = destination / "funasr-runtime" / "LICENSE"
runtime_license.parent.mkdir(exist_ok=True)
shutil.copyfile(root / "licenses" / "funasr-runtime-MIT.txt", runtime_license)
inventory.append({"name": "FunASR llama.cpp Windows x64 CPU runtime", "version": "runtime-llamacpp-v0.2.6",
                  "license": "MIT", "distribution_mode": "downloaded from official release on user request",
                  "source": "https://github.com/modelscope/FunASR/releases/tag/runtime-llamacpp-v0.2.6",
                  "files": [str(runtime_license.relative_to(destination))]})
inventory.append({"name": "SenseVoiceSmall-GGUF q8", "version": "90c1c61912018b70ada0fcc024ea24aca62f2e63",
                  "license": "GGUF repository tags Apache-2.0; original SenseVoiceSmall is tagged model-license. Model terms require separate review.",
                  "distribution_mode": "downloaded from official model repository on user request",
                  "source": "https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF",
                  "original_model": "https://huggingface.co/FunAudioLLM/SenseVoiceSmall",
                  "model_terms": "https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE",
                  "files": []})
(destination / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(destination / "README.txt").write_text(
    "Third-party dependency inventory for this candidate build. Python entries include the locked build tools, not only shipped runtime modules. "
    "Upstream license texts are retained without modification. Electron's bundled Chromium notices are also included by electron-builder. "
    "This inventory is not a legal certification; review upstream terms before public redistribution.\n", encoding="utf-8")
print(f"Retained license inventory for {len(inventory)} dependencies.")
