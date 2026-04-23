from __future__ import annotations

import os

from app.runtime import bootstrap_local_packages
from app.runtime import is_frozen

bootstrap_local_packages()

import uvicorn


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    host = os.getenv("POKERBOT_HOST", "0.0.0.0")
    port = int(os.getenv("POKERBOT_PORT", "8000"))
    reload_enabled = env_flag("POKERBOT_RELOAD", default=not is_frozen())
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_enabled)


if __name__ == "__main__":
    main()
