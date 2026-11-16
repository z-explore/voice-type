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


def log_file_path() -> Path:
    return user_data_dir() / "voice-type.log"


def should_daemonize(*, foreground: bool) -> bool:
    """Detach from the terminal so closing the console does not kill the app.

    Skip when: --foreground, Windows, systemd service, or not attached to a TTY
    (desktop / autostart already outlive the terminal).
    """
    import os

    if foreground or is_windows():
        return False
    if os.environ.get("VOICE_TYPE_FOREGROUND") == "1":
        return False
    # systemd user/system units set INVOCATION_ID; keep Type=simple PID stable.
    if os.environ.get("INVOCATION_ID"):
        return False
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def daemonize(log_path: Path | None = None) -> Path:
    """Double-fork into background; return path of the log file used for stdio."""
    import os

    if is_windows():
        raise RuntimeError("daemonize is not supported on Windows")

    path = Path(log_path) if log_path else log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)

    os.chdir("/")
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)
    return path
