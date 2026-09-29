"""Packaged entrypoint: no reload, loopback only, desktop-owned lifetime."""
import ctypes
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import uvicorn
    from app.main import app, recorder, results
    if not os.environ.get("LIKETYPELESS_SESSION_TOKEN"):
        raise SystemExit("LIKETYPELESS_SESSION_TOKEN must be supplied by the desktop host")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    @app.post("/system/shutdown")
    def shutdown():
        server.should_exit = True
        return {"ok": True}

    parent = os.environ.get("LIKETYPELESS_PARENT_PID")
    if parent and sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        handle = kernel.OpenProcess(0x100000, False, int(parent))
        if not handle:
            raise SystemExit("Desktop parent is unavailable")
        def watch_parent():
            kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            os._exit(0)  # Parent crashed; do not leave an orphan microphone service.
        threading.Thread(target=watch_parent, daemon=True).start()
    print(f"LIKETYPELESS_READY:{port}", flush=True)
    try:
        server.run(sockets=[listener])
    finally:
        if recorder.status()["isRecording"]:
            try:
                recording = recorder.stop()
                identifier = results.create(recording["filePath"])
                results.update(identifier, status="failed", error="应用在录音处理前退出，录音已暂存，可重试。")
            except Exception:
                pass
        listener.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
