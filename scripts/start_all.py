"""
Unified Production Launcher — Runs FastAPI Web Dashboard (CRUD + AI + Radar)
and Telegram Bot Daemon concurrently in a single process supervisor.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    port = os.getenv("PORT", "8000")
    web_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.web.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
    ]
    bot_cmd = [sys.executable, "-m", "src.bot.main"]

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []

    print(f"[start_all] Starting FastAPI Web Dashboard on 0.0.0.0:{port}...")
    web_proc = subprocess.Popen(web_cmd, cwd=str(ROOT_DIR))
    processes.append(("web", web_proc))

    if os.getenv("TELEGRAM_BOT_TOKEN"):
        print("[start_all] Starting Telegram Bot Daemon...")
        bot_proc = subprocess.Popen(bot_cmd, cwd=str(ROOT_DIR))
        processes.append(("bot", bot_proc))
    else:
        print(
            "[start_all] TELEGRAM_BOT_TOKEN not set; skipping Telegram Bot Daemon "
            "(Web Dashboard & API remain active)."
        )

    def shutdown(signum: int, _frame: object) -> None:
        print(f"\n[start_all] Received signal {signum}, shutting down...")
        for name, proc in processes:
            if proc.poll() is None:
                print(f"[start_all] Terminating {name} (pid={proc.pid})...")
                proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        for name, proc in processes:
            ret = proc.poll()
            if ret is not None:
                print(f"[start_all] Process '{name}' exited with code {ret}.")
                for other_name, other_proc in processes:
                    if other_name != name and other_proc.poll() is None:
                        other_proc.terminate()
                return ret
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
