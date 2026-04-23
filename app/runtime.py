from __future__ import annotations

import os
import sys
from pathlib import Path


def bootstrap_local_packages() -> None:
    """Adds the project root to sys.path."""
    root = project_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return project_root()


def user_data_root() -> Path:
    configured = os.getenv("POKERBOT_APPDATA")
    if configured:
        root = Path(configured).expanduser()
    else:
        local_appdata = os.getenv("LOCALAPPDATA")
        root = Path(local_appdata) / "Pokerbot" if local_appdata else Path.home() / ".pokerbot"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_database_path() -> Path:
    configured = os.getenv("POKERBOT_DB_PATH")
    if configured:
        path = Path(configured).expanduser()
    elif is_frozen():
        path = user_data_root() / "data" / "pokerbot.db"
    else:
        path = project_root() / "data" / "pokerbot.db"

    path.parent.mkdir(parents=True, exist_ok=True)
    return path
