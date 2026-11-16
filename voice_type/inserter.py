"""Insert text at the caret of the focused window.

Chinese text is never "typed" key by key through xdotool (that is unreliable for CJK);
instead we use the clipboard + a paste shortcut, or wtype which sends real Unicode.

auto order:
  X11      : xclip/xsel + xdotool key ctrl+v
  Wayland  : wtype "<text>"                (wlroots / KDE; NOT GNOME)
             wl-copy + ydotool ctrl+v      (GNOME Wayland; needs ydotoold + /dev/uinput)
             wl-copy + xdotool ctrl+v      (only works for XWayland windows)
  last resort: copy to clipboard and tell the user to press Ctrl+V
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time

log = logging.getLogger("voice_type.insert")

TERMINALS = ("gnome-terminal", "terminator", "konsole", "xterm", "alacritty", "kitty", "tilix",
             "xfce4-terminal", "wezterm", "urxvt", "mate-terminal", "lxterminal", "foot", "ptyxis")

# Linux input keycodes for ydotool >= 1.0 ("key 29:1 47:1 47:0 29:0")
_YDO = {"ctrl": 29, "shift": 42, "alt": 56, "super": 125, "v": 47, "insert": 110}


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(args, inp: str | None = None, timeout: float = 3.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=inp.encode("utf-8") if inp is not None else None,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def session_type() -> str:
    if sys.platform == "win32":
        return "win32"
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "none"


def is_gnome() -> bool:
    return "gnome" in (os.environ.get("XDG_CURRENT_DESKTOP", "") + os.environ.get("DESKTOP_SESSION", "")).lower()


class Inserter:
    def __init__(self, cfg: dict):
        c = cfg["insert"]
        self.backend = c.get("backend", "auto")
        self.restore = c.get("restore_clipboard", True)
        self.paste = c.get("paste_shortcut", "ctrl+v")
        self.term_paste = c.get("terminal_paste_shortcut", "ctrl+shift+v")
        self.trailing_space = c.get("trailing_space", False)
        self.session = session_type()

    # ---------------- clipboard helpers
    def _clip_get(self) -> str | None:
        try:
            if self.session == "wayland" and _has("wl-paste"):
                r = _run(["wl-paste", "--no-newline", "--type", "text"], timeout=1.0)
            elif _has("xclip"):
                r = _run(["xclip", "-selection", "clipboard", "-o"], timeout=1.0)
            elif _has("xsel"):
                r = _run(["xsel", "--clipboard", "--output"], timeout=1.0)
            else:
                return None
            return r.stdout.decode("utf-8") if r.returncode == 0 else None
        except Exception:
            return None

    def _clip_set(self, text: str) -> bool:
        # wl-copy / xclip fork a child that keeps serving the clipboard and inherits our
        # stdout/stderr, so capturing them would block until the timeout.
        def put(args) -> bool:
            return subprocess.run(args, input=text.encode("utf-8"), stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=3.0).returncode == 0
        try:
            if self.session == "wayland" and _has("wl-copy"):
                return put(["wl-copy"])
            if _has("xclip"):
                return put(["xclip", "-selection", "clipboard", "-i"])
            if _has("xsel"):
                return put(["xsel", "--clipboard", "--input"])
        except Exception as e:
            log.debug("clipboard set failed: %s", e)
        return False

    # ---------------- key senders
    def _focused_is_terminal(self) -> bool:
        if self.session != "x11" or not _has("xdotool"):
            return False
        try:
            r = _run(["xdotool", "getactivewindow", "getwindowclassname"], timeout=1.0)
            cls = r.stdout.decode("utf-8", "ignore").strip().lower()
            return any(t in cls for t in TERMINALS)
        except Exception:
            return False

    def _shortcut(self) -> str:
        return self.term_paste if self._focused_is_terminal() else self.paste

    def _xdotool_paste(self, combo: str) -> bool:
        return _has("xdotool") and _run(["xdotool", "key", "--clearmodifiers", combo]).returncode == 0

    def _ydotool_legacy(self) -> bool:
        if not hasattr(self, "_ydo_legacy"):
            try:
                r = _run(["ydotool", "key", "--help"], timeout=2.0)
                out = (r.stdout + r.stderr).decode("utf-8", "ignore")
                self._ydo_legacy = "separated by plus" in out
            except Exception:
                self._ydo_legacy = False
        return self._ydo_legacy

    def _ydotool_paste(self, combo: str) -> bool:
        if not _has("ydotool"):
            return False
        # ydotool 0.1.x (Ubuntu 22.04 apt) only takes names ("ctrl+v"); it parses "29:1" as
        # the digit keys 2 and 9 and still exits 0, so the numeric form must not be tried first.
        if self._ydotool_legacy():
            return _run(["ydotool", "key", combo]).returncode == 0
        keys = [_YDO[k] for k in combo.lower().split("+") if k in _YDO]
        seq = [f"{k}:1" for k in keys] + [f"{k}:0" for k in reversed(keys)]
        return _run(["ydotool", "key", *seq]).returncode == 0

    def _wtype(self, text: str) -> bool:
        return _has("wtype") and _run(["wtype", "--", text], timeout=10).returncode == 0

    # ---------------- public
    def pick_backend(self) -> str:
        if self.backend != "auto":
            return self.backend
        if self.session == "win32":
            return "win32"
        if self.session == "x11":
            return "xdotool" if _has("xdotool") and (_has("xclip") or _has("xsel")) else "clipboard"
        if self.session == "wayland":
            if _has("wtype") and not is_gnome():
                return "wtype"
            if _has("ydotool") and _has("wl-copy"):
                return "ydotool"
            if _has("xdotool") and _has("wl-copy"):
                return "xdotool"   # works only for XWayland apps
            return "clipboard"
        return "print"

    def _win32_clip_get(self) -> str | None:
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            log.debug("win32 clipboard get failed: %s", e)
        return None

    def _win32_clip_set(self, text: str) -> bool:
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception as e:
            log.debug("win32 clipboard set failed: %s", e)
            return False

    def _win32_paste(self, text: str) -> str:
        old = self._win32_clip_get() if self.restore else None
        if not self._win32_clip_set(text):
            log.error("无法写入剪贴板，文本: %s", text)
            print(text, flush=True)
            return "print"
        time.sleep(0.05)
        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            with kb.pressed(Key.ctrl):
                kb.press("v")
                kb.release("v")
        except Exception as e:
            log.warning("Windows 自动粘贴失败，文字已复制，请手动 Ctrl+V: %s", e)
            return "clipboard"
        if old is not None and self.restore:
            time.sleep(0.4)
            self._win32_clip_set(old)
        return "win32"

    def insert(self, text: str) -> str:
        """Returns the method actually used ("print" means no display - text only logged)."""
        if not text:
            return "none"
        if self.trailing_space:
            text += " "
        b = self.pick_backend()
        if b == "print":
            print(text, flush=True)
            return "print"
        if b == "win32":
            return self._win32_paste(text)
        if b == "wtype" and self._wtype(text):
            return "wtype"
        old = self._clip_get() if self.restore else None
        if not self._clip_set(text):
            log.error("无法写入剪贴板 (缺少 xclip / wl-clipboard?)，文本: %s", text)
            print(text, flush=True)
            return "print"
        time.sleep(0.05)
        combo = self._shortcut()
        ok = False
        if b == "xdotool":
            ok = self._xdotool_paste(combo)
        elif b == "ydotool":
            ok = self._ydotool_paste(combo)
        elif b == "wtype":                     # wtype failed for direct text: try its paste
            ok = _has("wtype") and _run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"]).returncode == 0
        if not ok:
            log.warning("自动粘贴失败/不可用，文字已复制到剪贴板，请手动按 Ctrl+V")
            return "clipboard"
        if old is not None and self.restore:
            time.sleep(0.4)                    # let the app read the clipboard first
            self._clip_set(old)
        return b
