import os
import subprocess
import sys
import time
import webbrowser
import runpy
import threading
import traceback
import server
from pathlib import Path


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PORT = os.environ.get("MEGA_BRAIN_PORT", "4180")
LOG_PATH = Path(os.environ.get("TEMP", str(ROOT))) / "mega-brain-launcher.log"


def run_server():
    try:
        server.run_server()
    except Exception:
        LOG_PATH.write_text(traceback.format_exc(), encoding="utf-8")


def main():
    os.environ.setdefault("MEGA_BRAIN_PORT", PORT)
    server.PORT = int(PORT)
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}/frontend/")
    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
