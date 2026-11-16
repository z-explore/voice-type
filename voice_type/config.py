"""Config loading. Defaults live here; users override in config.toml."""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Ubuntu 22.04 ships Python 3.10
    import tomli as tomllib

from .platform_util import project_dir

PROJECT_DIR = project_dir()
MODEL_DIRNAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"


def _defaults() -> dict:
    root = project_dir()
    return {
        "hotkey": {
            # evdev / pynput key name. Linux & Windows default: Right Alt
            "key": "KEY_RIGHTALT",
            # Hold shorter than this = treated as a plain Alt tap, ignored.
            "min_hold_ms": 300,
            # "auto" | "evdev" (Linux) | "pynput" (Windows / X11 fallback)
            "backend": "auto",
        },
        "audio": {
            "sample_rate": 16000,
            "device": "",          # "" = system default input; or a name/index from --list-devices
            "max_seconds": 120,
            "min_rms": 0.002,      # below this the clip is treated as silence
        },
        "asr": {
            "engine": "local",     # "local" (default, offline) | "cloud" (see [cloud])
            "model_dir": str(root / "models" / MODEL_DIRNAME),
            "language": "zh",      # "zh" | "auto" (better for heavy zh+en mixing) | "en" | "yue" ...
            "num_threads": 2,
            "use_itn": True,       # punctuation + numbers as digits
        },
        "cleanup": {
            "enabled": True,
            "remove_fillers": True,
            "remove_repeats": True,
        },
        "insert": {
            # "auto" | "win32" | "xdotool" | "wtype" | "ydotool" | "clipboard"
            "backend": "auto",
            "restore_clipboard": True,
            "paste_shortcut": "ctrl+v",
            "terminal_paste_shortcut": "ctrl+shift+v",
            "trailing_space": False,
        },
        "ui": {
            "notify": True,        # desktop notification via notify-send (Linux)
            "sound": True,         # short beep on start/stop
            "overlay": True,       # floating voice bar (Linux; ignored on Windows for now)
            "overlay_offset_x": 16,
            "overlay_offset_y": 24,
        },
        "cloud": {
            # DISABLED by default. OpenAI-compatible /v1/audio/transcriptions endpoint.
            "enabled": False,
            "base_url": "https://api.groq.com/openai/v1",
            "model": "whisper-large-v3-turbo",
            "api_key_env": "VOICE_TYPE_API_KEY",  # key is read from this env var, never stored here
            "timeout_s": 30,
            "fallback_to_local": True,
        },
    }


DEFAULTS: dict = _defaults()


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def default_config_path() -> Path:
    env = os.environ.get("VOICE_TYPE_CONFIG")
    if env:
        return Path(env).expanduser()
    root = project_dir()
    local = root / "config.toml"
    if local.exists():
        return local
    if sys.platform == "win32":
        import os as _os
        base = Path(_os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "voice-type" / "config.toml"
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg / "voice-type" / "config.toml"


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path).expanduser() if path else default_config_path()
    user: dict = {}
    if p.exists():
        with open(p, "rb") as f:
            user = tomllib.load(f)
    cfg = _merge(_defaults(), user)
    root = project_dir()
    md = Path(cfg["asr"]["model_dir"]).expanduser()
    if not md.is_absolute():
        md = root / md
    # Frozen packages always prefer models/ next to the executable when present.
    bundled = root / "models" / MODEL_DIRNAME
    if (bundled / "model.int8.onnx").exists():
        md = bundled
    cfg["asr"]["model_dir"] = str(md)
    cfg["_path"] = str(p) if p.exists() else None
    return cfg
