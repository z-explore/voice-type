"""Drives EvdevListener with a fake /dev/input device (pipe-backed), no real hardware needed."""
import os
import threading
import time
from types import SimpleNamespace

import pytest

evdev = pytest.importorskip("evdev")
from evdev import ecodes  # noqa: E402

from voice_type import hotkey  # noqa: E402


class FakeDev:
    def __init__(self, path):
        self.path, self.name = path, "Fake Keyboard"
        self.r, self.w = os.pipe()
        self.queue = []

    def capabilities(self):
        return {ecodes.EV_KEY: [ecodes.KEY_A, ecodes.KEY_RIGHTALT, ecodes.KEY_TAB]}

    def fileno(self):
        return self.r

    def push(self, code, value):
        self.queue.append(SimpleNamespace(type=ecodes.EV_KEY, code=code, value=value))
        os.write(self.w, b"x")

    def read(self):
        os.read(self.r, 4096)
        out, self.queue = self.queue, []
        return out

    def close(self):
        pass


def test_evdev_listener_alt_alone_and_alt_tab(monkeypatch):
    dev = FakeDev("/dev/input/event-fake")
    monkeypatch.setattr(hotkey, "_list_event_paths", lambda: [dev.path])
    monkeypatch.setattr(hotkey.os, "access", lambda p, m: True)
    monkeypatch.setattr(evdev, "InputDevice", lambda p: dev)
    actions = []
    sm = hotkey.PTTStateMachine("KEY_RIGHTALT")
    lst = hotkey.EvdevListener(sm, actions.append)
    lst.start()
    time.sleep(0.2)
    alt, tab = ecodes.KEY_RIGHTALT, ecodes.KEY_TAB
    # Right Alt+Tab must not start recording
    dev.push(alt, 1); time.sleep(0.05); dev.push(tab, 1); dev.push(tab, 0); time.sleep(0.05); dev.push(alt, 0)
    time.sleep(0.2)
    # Clean tap (with auto-repeat while held) starts on release
    dev.push(alt, 1); time.sleep(0.1); dev.push(alt, 2); time.sleep(0.05); dev.push(alt, 0)
    time.sleep(0.2)
    # Second clean tap stops
    dev.push(alt, 1); time.sleep(0.05); dev.push(alt, 0)
    time.sleep(0.3)
    lst.stop()
    assert actions == ["start", "stop"]
