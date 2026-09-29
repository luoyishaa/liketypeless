from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for package in ("faster_whisper", "ctranslate2", "tokenizers", "soundfile", "sounddevice", "opencc"):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
datas += copy_metadata("faster-whisper")
# GPU libraries are optional; CPU inference works without an NVIDIA driver.
for package in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
    binaries += collect_dynamic_libs(package)
analysis = Analysis([str(root / "scripts" / "serve_product.py")], pathex=[str(root)],
                    datas=datas, binaries=binaries, hiddenimports=hiddenimports + ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"],
                    excludes=["torch", "funasr", "modelscope", "pytest", "tkinter"])
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="liketypeless-api", console=True, upx=False)
coll = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="liketypeless-api")
