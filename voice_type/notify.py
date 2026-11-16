"""Status feedback: voice bar near the pointer, optional notify-send, optional beep."""
from __future__ import annotations

import logging
import shutil
import subprocess

from .audio import beep
from .overlay import VoiceBar

log = logging.getLogger("voice_type")

_TITLES = {"recording": "🎙 录音中…", "transcribing": "⏳ 识别中…", "done": "✅ 已输入",
           "error": "⚠️ 出错", "cancelled": "已取消", "ready": "voice-type 已就绪"}


class Status:
    def __init__(self, cfg: dict, level_fn=None):
        import sys
        ui = cfg.get("ui", {})
        self.notify = ui.get("notify", True) and shutil.which("notify-send") is not None
        self.sound = ui.get("sound", True)
        # Overlay is a Linux X11/GTK capsule; skip on Windows portable builds.
        overlay_on = bool(ui.get("overlay", True)) and not sys.platform.startswith("win")
        self.bar = VoiceBar(
            enabled=overlay_on,
            offset_x=int(ui.get("overlay_offset_x", 16)),
            offset_y=int(ui.get("overlay_offset_y", 24)),
            level_fn=level_fn,
        )
        self.bar.start()

    def __call__(self, state: str, detail: str = "") -> None:
        log.info("[%s] %s", state, detail)
        if self.sound and state == "recording":
            beep(880)
        elif self.sound and state == "transcribing":
            beep(660)
        self.bar.show(state, detail)
        if self.notify and state in ("recording", "transcribing", "done", "error", "ready"):
            try:
                subprocess.Popen(
                    ["notify-send", "-a", "voice-type", "-t", "1500", "-u", "low",
                     "-h", "string:x-canonical-private-synchronous:voice-type",
                     _TITLES[state], detail[:120]],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
