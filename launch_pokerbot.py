from __future__ import annotations

import os
import threading
import time
import urllib.request
import webbrowser

from app.runtime import bootstrap_local_packages

bootstrap_local_packages()

import uvicorn

from app.main import app
from app.runtime import default_database_path


def browser_enabled() -> bool:
    value = os.getenv("POKERBOT_OPEN_BROWSER", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def launch_browser_when_ready(url: str, health_url: str, timeout_seconds: int = 20) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1):
                webbrowser.open(url)
                return
        except Exception:
            time.sleep(0.5)

    webbrowser.open(url)


def main() -> None:
    bind_host = os.getenv("POKERBOT_HOST", "127.0.0.1")
    port = int(os.getenv("POKERBOT_PORT", "8000"))
    browser_host = "127.0.0.1" if bind_host in {"0.0.0.0", "::"} else bind_host
    app_url = f"http://{browser_host}:{port}/"
    health_url = f"http://{browser_host}:{port}/api/health"

    print(f"Starting Pokerbot at {app_url}")
    print(f"Local database: {default_database_path()}")
    print("Close this window to stop Pokerbot.")

    if browser_enabled():
        threading.Thread(
            target=launch_browser_when_ready,
            args=(app_url, health_url),
            daemon=True,
        ).start()

    uvicorn.run(app, host=bind_host, port=port, reload=False)


if __name__ == "__main__":
    main()
