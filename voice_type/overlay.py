"""Voice bar: Handy-style pill at the bottom of the screen (overlay_gtk.py), or a plain
Tk bar near the mouse pointer when the system python has no GTK bindings."""
from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger("voice_type")

_LABELS = {
    "recording": "🎙  录音中",
    "transcribing": "⏳  识别中",
    "done": "✅  已输入",
    "error": "⚠️  出错",
}


def pointer_xy() -> tuple[int, int] | None:
    """Best-effort mouse position. Works on X11; often fails on pure Wayland."""
    if not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.check_output(
            ["xdotool", "getmouselocation", "--shell"],
            text=True, timeout=0.4, stderr=subprocess.DEVNULL,
        )
        vals: dict[str, str] = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k] = v
        if "X" in vals and "Y" in vals:
            return int(vals["X"]), int(vals["Y"])
    except Exception:
        return None
    return None


def parse_xdotool_location(text: str) -> tuple[int, int] | None:
    vals: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k] = v
    if "X" in vals and "Y" in vals:
        return int(vals["X"]), int(vals["Y"])
    return None


def bar_position(
    pointer: tuple[int, int] | None,
    bar_w: int,
    bar_h: int,
    screen_w: int,
    screen_h: int,
    offset_x: int = 16,
    offset_y: int = 24,
) -> tuple[int, int]:
    """Place the bar just below-right of the pointer, or bottom-center if unknown."""
    if pointer is None:
        x = max(8, (screen_w - bar_w) // 2)
        y = max(8, screen_h - bar_h - 80)
        return x, y
    px, py = pointer
    x = px + offset_x
    y = py + offset_y
    if x + bar_w > screen_w - 8:
        x = px - bar_w - offset_x
    if y + bar_h > screen_h - 8:
        y = py - bar_h - offset_y
    x = min(max(8, x), max(8, screen_w - bar_w - 8))
    y = min(max(8, y), max(8, screen_h - bar_h - 8))
    return x, y


WAVE_BARS = 18
WAVE_H = 28


def level_to_height(unit: float, max_h: int = WAVE_H, min_h: int = 3) -> int:
    """unit: 0..1 band level from audio.spectrum_levels."""
    return int(round(min_h + min(1.0, max(0.0, unit)) * (max_h - min_h)))


GTK_SCRIPT = Path(__file__).with_name("overlay_gtk.py")
SYSTEM_PYTHON = "/usr/bin/python3"


def gtk_pill_available() -> bool:
    """The pill needs python3-gi, which lives in the system python, not in the venv."""
    if not Path(SYSTEM_PYTHON).exists():
        return False
    probe = ("import gi; gi.require_version('Gtk', '3.0'); gi.require_version('PangoCairo', '1.0'); "
             "from gi.repository import Gtk, PangoCairo")
    try:
        return subprocess.run([SYSTEM_PYTHON, "-c", probe], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except Exception:
        return False


class VoiceBar:
    """level_fn() -> list of 0..1 band levels while recording."""

    def __init__(self, enabled: bool = True, offset_x: int = 16, offset_y: int = 24, level_fn=None):
        self.enabled = enabled
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.level_fn = level_fn
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = False
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._recording = False

    def start(self) -> None:
        if not self.enabled or self._started:
            return
        if gtk_pill_available() and self._start_pill():
            self._started = True
            return
        try:
            import tkinter  # noqa: F401
        except ImportError:
            log.warning("未安装 python3-tk，无法显示靠近鼠标的语音条（sudo apt install python3-tk）")
            self.enabled = False
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="voice-bar")
        self._thread.start()

    # ---------------- GTK pill (child process)
    def _start_pill(self) -> bool:
        try:
            self._proc = subprocess.Popen([SYSTEM_PYTHON, str(GTK_SCRIPT)], stdin=subprocess.PIPE,
                                          stdout=subprocess.DEVNULL, text=True, encoding="utf-8")
        except Exception as e:
            log.warning("无法启动底部语音条，改用简易语音条: %s", e)
            return False
        threading.Thread(target=self._pump_levels, daemon=True, name="voice-bar-level").start()
        return True

    def _send(self, line: str) -> None:
        with self._proc_lock:
            if self._proc is None or self._proc.poll() is not None:
                return
            try:
                self._proc.stdin.write(line + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                log.warning("语音条进程已退出")
                self._proc = None

    def _pump_levels(self) -> None:
        while self._proc is not None:
            if self._recording and self.level_fn is not None:
                try:
                    self._send("levels " + ",".join(f"{v:.3f}" for v in self.level_fn()))
                except Exception:
                    pass
            time.sleep(0.033)

    def show(self, state: str, detail: str = "") -> None:
        if not self.enabled:
            return
        if not self._started:
            self.start()
        if self._proc is not None:
            self._recording = state == "recording"
            if state in ("cancelled", "ready"):
                self._send("hide")
            elif state in _LABELS:
                clean = " ".join((detail or "").split())
                self._send(f"show {state}\t{clean}")
            return
        if state in ("cancelled", "ready"):
            self._q.put(("hide", state, detail))
            return
        if state in _LABELS:
            self._q.put(("show", state, detail))

    def hide(self) -> None:
        if self._proc is not None:
            self._recording = False
            self._send("hide")
        elif self._started:
            self._q.put(("hide", "", ""))

    def _run(self) -> None:
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError as e:
            log.warning("无法创建语音条窗口（没有可用的图形界面）: %s", e)
            self.enabled = False
            return

        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg="#1c1c1e")
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        for typ in ("notification", "tooltip", "dock"):
            try:
                root.attributes("-type", typ)
                break
            except tk.TclError:
                continue

        wrap = tk.Frame(root, bg="#1c1c1e", padx=18, pady=10)
        wrap.pack()
        title = tk.Label(
            wrap, text="", fg="#f5f5f7", bg="#1c1c1e",
            font=("sans-serif", 12, "bold"), justify="left",
        )
        title.pack(anchor="w")
        subtitle = tk.Label(
            wrap, text="", fg="#a1a1a6", bg="#1c1c1e",
            font=("sans-serif", 9), justify="left",
        )
        bar_w, gap = 4, 3
        wave = tk.Canvas(wrap, width=WAVE_BARS * (bar_w + gap) - gap, height=WAVE_H,
                         bg="#1c1c1e", highlightthickness=0)
        bars = [wave.create_rectangle(0, 0, 0, 0, fill="#ff453a", outline="")
                for _ in range(WAVE_BARS)]
        heights = [3] * WAVE_BARS
        cur_state = [""]

        def draw_wave() -> None:
            for i, h in enumerate(heights):
                x = i * (bar_w + gap)
                top = (WAVE_H - h) / 2
                wave.coords(bars[i], x, top, x + bar_w, top + h)

        hide_job: list = [None]

        def cancel_hide() -> None:
            if hide_job[0] is not None:
                try:
                    root.after_cancel(hide_job[0])
                except Exception:
                    pass
                hide_job[0] = None

        def do_hide() -> None:
            cancel_hide()
            cur_state[0] = ""
            root.withdraw()

        def place(state: str, detail: str) -> None:
            cancel_hide()
            cur_state[0] = state
            title.configure(text=_LABELS.get(state, state))
            subtitle.pack_forget()
            wave.pack_forget()
            if state == "recording" and self.level_fn is not None:
                heights[:] = [3] * WAVE_BARS
                draw_wave()
                wave.pack(anchor="w", pady=(6, 0))
            else:
                text = (detail or "").strip()[:40]
                if text:
                    subtitle.configure(text=text)
                    subtitle.pack(anchor="w")
            root.update_idletasks()
            w = max(root.winfo_reqwidth(), 160)
            h = root.winfo_reqheight()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            x, y = bar_position(
                pointer_xy(), w, h, sw, sh, self.offset_x, self.offset_y,
            )
            root.geometry(f"+{x}+{y}")
            root.deiconify()
            try:
                root.lift()
            except tk.TclError:
                pass
            if state in ("done", "error"):
                hide_job[0] = root.after(1200, do_hide)

        def poll() -> None:
            try:
                while True:
                    action, state, detail = self._q.get_nowait()
                    if action == "hide":
                        do_hide()
                    else:
                        place(state, detail)
            except queue.Empty:
                pass
            if cur_state[0] == "recording" and self.level_fn is not None:
                try:
                    level = max(self.level_fn(), default=0.0)
                except Exception:
                    level = 0.0
                heights.pop(0)
                heights.append(level_to_height(level))
                draw_wave()
            root.after(40, poll)

        poll()
        root.mainloop()
