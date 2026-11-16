"""Toggle hotkey (press once to start, press again to stop).

PTTStateMachine is pure logic (unit-tested). A clean tap of the hotkey returns:
    "start"  - on release while idle (so Alt+Tab / AltGr chords never start recording)
    "stop"   - on press while recording (does not wait for release; avoids stuck
               recording when the key-up event is dropped by the input stack)

A chord (Right Alt+Tab, AltGr+key, Alt+click, or another modifier already held) is
ignored for *starting*. While recording, a bare hotkey press stops immediately;
Alt+Tab during recording will therefore also stop (acceptable tradeoff vs getting stuck).
Listeners never grab/suppress keys, so normal shortcuts keep working.

Two listener backends:
    evdev  - reads /dev/input/event*; works on X11 *and* Wayland; user must be in group `input`.
    pynput - X11 only (uses XRecord); no extra permissions. Used as fallback on X11.
"""
from __future__ import annotations

import logging
import os
import selectors
import threading
import time
from typing import Callable

log = logging.getLogger("voice_type.hotkey")

IDLE, RECORDING = "idle", "recording"


class PTTStateMachine:
    # If a non-hotkey "down" is seen but its "up" is lost (Bluetooth lag, remote
    # desktop, flaky input), that key would forever mark every Alt tap as a combo
    # and recording could not be stopped. Drop entries older than this.
    OTHER_KEY_TTL_S = 3.0

    def __init__(self, hotkey: str = "KEY_RIGHTALT", min_hold_ms: int = 0,
                 other_key_ttl_s: float | None = None):
        self.hotkey = hotkey
        self.min_hold = min_hold_ms / 1000.0  # kept for config compatibility; toggle fires on release
        self.other_key_ttl = self.OTHER_KEY_TTL_S if other_key_ttl_s is None else other_key_ttl_s
        self.state = IDLE
        self.hot_down = False
        self.combo = False
        self._suppress_up = False  # ignore the real up after an eager stop
        self.others_down: dict[str, float] = {}  # key -> monotonic time of last down

    def _prune_others(self, t: float) -> None:
        if self.other_key_ttl <= 0 or not self.others_down:
            return
        ttl = self.other_key_ttl
        stale = [k for k, t0 in self.others_down.items() if t - t0 > ttl]
        for k in stale:
            log.debug("dropping stale other key %s (held > %.1fs, likely missed up)", k, ttl)
            del self.others_down[k]

    def _toggle(self) -> str | None:
        if self.state == IDLE:
            self.state = RECORDING
            return "start"
        if self.state == RECORDING:
            self.state = IDLE
            return "stop"
        return None

    def feed(self, key: str, down: bool, t: float | None = None, repeat: bool = False) -> str | None:
        """key: evdev-style name (KEY_A, BTN_LEFT, ...). Returns an action or None."""
        now = time.monotonic() if t is None else t
        if key == self.hotkey:
            if repeat:
                return None
            if down:
                # Previous eager-stop's up never arrived — don't let suppress_up
                # eat the release of this new tap.
                if self._suppress_up:
                    self._suppress_up = False
                # Missed a previous release while still armed.
                if self.hot_down:
                    log.debug("hotkey down while already down; recovering from missed up")
                    self.hot_down = False
                    self.combo = False
                    if self.state == RECORDING:
                        self._suppress_up = True
                        return self._toggle()
                    # idle: fall through and re-arm for a fresh tap
                self._prune_others(now)
                self.combo = bool(self.others_down)
                # Stop on press so a dropped key-up cannot leave us stuck recording.
                if self.state == RECORDING and not self.combo:
                    self.hot_down = False
                    self._suppress_up = True
                    return self._toggle()
                self.hot_down = True
                return None
            if self._suppress_up:
                self._suppress_up = False
                self.hot_down = False
                self.combo = False
                return None
            if not self.hot_down:
                return None
            self.hot_down = False
            was_combo = self.combo
            self.combo = False
            if was_combo:
                log.debug("hotkey tap ignored (chord with %s)",
                          sorted(self.others_down) or "earlier key")
                return None
            # Only start (or legacy stop) on release; stop normally happens on press.
            return self._toggle()
        if down and not repeat:
            self.others_down[key] = now
            if self.hot_down:
                self.combo = True
        elif not down:
            self.others_down.pop(key, None)
        return None


# --------------------------------------------------------------------------- evdev backend
def evdev_available() -> tuple[bool, str]:
    try:
        import evdev  # noqa: F401
    except Exception as e:
        return False, f"python-evdev 未安装: {e}"
    devs = [p for p in _list_event_paths() if os.access(p, os.R_OK)]
    if not devs:
        return False, "没有可读的 /dev/input/event* (需要把用户加入 input 组并重新登录)"
    return True, f"{len(devs)} readable input devices"


def _list_event_paths() -> list[str]:
    try:
        return sorted(os.path.join("/dev/input", n) for n in os.listdir("/dev/input") if n.startswith("event"))
    except FileNotFoundError:
        return []


class EvdevListener(threading.Thread):
    RESCAN_S = 3.0

    def __init__(self, sm: PTTStateMachine, on_action: Callable[[str], None]):
        super().__init__(daemon=True, name="evdev-listener")
        import evdev
        from evdev import ecodes
        self.evdev, self.ec = evdev, ecodes
        self.sm, self.on_action = sm, on_action
        if sm.hotkey not in ecodes.ecodes:
            raise ValueError(f"未知按键名: {sm.hotkey} (示例: KEY_LEFTALT, KEY_RIGHTALT, KEY_RIGHTCTRL)")
        self.hot_code = ecodes.ecodes[sm.hotkey]
        self.sel = selectors.DefaultSelector()
        self.devices: dict[str, object] = {}
        self._stop_ev = threading.Event()

    def _is_input_dev(self, dev) -> bool:
        keys = dev.capabilities().get(self.ec.EV_KEY, [])
        return self.hot_code in keys or self.ec.BTN_LEFT in keys or self.ec.KEY_A in keys

    def _rescan(self) -> None:
        for path in _list_event_paths():
            if path in self.devices or not os.access(path, os.R_OK):
                continue
            try:
                dev = self.evdev.InputDevice(path)
                if dev.name.startswith("ydotoold") or not self._is_input_dev(dev):
                    dev.close()            # skip our own virtual keyboard + non-key devices
                    continue
                self.devices[path] = dev
                self.sel.register(dev, selectors.EVENT_READ)
                log.debug("listening on %s (%s)", path, dev.name)
            except OSError:
                continue

    def _drop(self, dev) -> None:
        try:
            self.sel.unregister(dev)
        except Exception:
            pass
        self.devices.pop(dev.path, None)
        try:
            dev.close()
        except Exception:
            pass

    def _keyname(self, code: int) -> str:
        n = self.ec.KEY.get(code) or self.ec.BTN.get(code) or str(code)
        return n[0] if isinstance(n, (list, tuple)) else n

    def run(self) -> None:
        self._rescan()
        log.info("evdev hotkey listener on %d devices, hotkey=%s", len(self.devices), self.sm.hotkey)
        last_scan = time.monotonic()
        while not self._stop_ev.is_set():
            for key, _ in self.sel.select(timeout=0.5):
                dev = key.fileobj
                try:
                    for ev in dev.read():
                        if ev.type != self.ec.EV_KEY:
                            continue
                        name = self.sm.hotkey if ev.code == self.hot_code else self._keyname(ev.code)
                        act = self.sm.feed(name, down=ev.value != 0, repeat=ev.value == 2)
                        if act:
                            self.on_action(act)
                except (OSError, BlockingIOError) as e:
                    if isinstance(e, BlockingIOError):
                        continue
                    log.info("device removed: %s", getattr(dev, "path", "?"))
                    self._drop(dev)
            if time.monotonic() - last_scan > self.RESCAN_S:   # keyboard hot-plug
                self._rescan()
                last_scan = time.monotonic()

    def stop(self) -> None:
        self._stop_ev.set()


# --------------------------------------------------------------------------- pynput backend (X11)
_PYNPUT_MAP = {
    "KEY_LEFTALT": "alt_l", "KEY_RIGHTALT": "alt_r", "KEY_LEFTCTRL": "ctrl_l", "KEY_RIGHTCTRL": "ctrl_r",
    "KEY_LEFTMETA": "cmd_l", "KEY_RIGHTMETA": "cmd_r", "KEY_CAPSLOCK": "caps_lock",
    "KEY_SCROLLLOCK": "scroll_lock", "KEY_PAUSE": "pause", "KEY_INSERT": "insert",
    **{f"KEY_F{i}": f"f{i}" for i in range(1, 13)},
}


class PynputListener:
    def __init__(self, sm: PTTStateMachine, on_action: Callable[[str], None]):
        from pynput import keyboard, mouse
        name = _PYNPUT_MAP.get(sm.hotkey)
        if not name:
            raise ValueError(f"pynput 后端不支持 {sm.hotkey}")
        targets = {getattr(keyboard.Key, name)}
        if name == "alt_r":                      # many layouts report Right Alt as AltGr
            targets.add(keyboard.Key.alt_gr)
        self.sm, self.on_action, self.targets = sm, on_action, targets

        def keyname(k):
            return sm.hotkey if k in targets else str(k)

        def press(k):
            # pynput reports auto-repeat as repeated presses; the state machine ignores
            # a hotkey "down" while already armed, and other keys only matter once.
            act = sm.feed(keyname(k), True)
            if act:
                on_action(act)

        def release(k):
            act = sm.feed(keyname(k), False)
            if act:
                on_action(act)

        def click(x, y, button, pressed):
            act = sm.feed(f"BTN_{button}", pressed)
            if act:
                on_action(act)

        self.kl = keyboard.Listener(on_press=press, on_release=release)
        self.ml = mouse.Listener(on_click=click)

    def start(self):
        self.kl.start()
        self.ml.start()
        log.info("pynput (X11) hotkey listener started, hotkey=%s", self.sm.hotkey)

    def stop(self):
        self.kl.stop()
        self.ml.stop()


def make_listener(cfg: dict, sm: PTTStateMachine, on_action):
    import sys
    backend = cfg["hotkey"].get("backend", "auto")
    session = os.environ.get("XDG_SESSION_TYPE", "")
    # Windows: pynput only (no evdev).
    if sys.platform == "win32":
        if backend not in ("auto", "pynput"):
            raise RuntimeError(f"Windows 仅支持 pynput 热键后端，当前: {backend}")
        return PynputListener(sm, on_action)
    if backend in ("auto", "evdev"):
        ok, why = evdev_available()
        if ok:
            return EvdevListener(sm, on_action)
        if backend == "evdev":
            raise RuntimeError(why)
        log.warning("evdev 不可用: %s", why)
    if backend in ("auto", "pynput"):
        if session == "wayland" and backend == "auto":
            raise RuntimeError("Wayland 下必须用 evdev 监听按键: sudo usermod -aG input $USER 然后重新登录")
        return PynputListener(sm, on_action)
    raise RuntimeError(f"unknown hotkey backend {backend}")
