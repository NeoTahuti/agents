import os
import subprocess
import sys
import time
import webbrowser
import runpy
import threading
from pathlib import Path


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PORT = os.environ.get("MEGA_BRAIN_PORT", "4176")


def main():
    server_thread = threading.Thread(target=runpy.run_path, args=(str(ROOT / "server.py"),), kwargs={"run_name": "__main__"}, daemon=True)
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
