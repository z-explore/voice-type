"""Platform helpers and frozen-app paths (PyInstaller onedir)."""
from __future__ import annotations

import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_dir() -> Path:
    """Install / project root: next to the exe when frozen, else repo root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Writable app data (locks, logs, corpus)."""
    if is_windows():
        import os
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        d = base / "voice-type"
    else:
        import os
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        d = base / "voice-type"
    d.mkdir(parents=True, exist_ok=True)
    return d
