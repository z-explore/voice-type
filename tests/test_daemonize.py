"""Detaching from the terminal must not break systemd / foreground modes."""
from __future__ import annotations

import os

from voice_type.platform_util import should_daemonize


def test_foreground_flag_disables_daemonize():
    assert should_daemonize(foreground=True) is False


def test_systemd_invocation_disables_daemonize(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "abc")
    assert should_daemonize(foreground=False) is False


def test_explicit_env_disables_daemonize(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setenv("VOICE_TYPE_FOREGROUND", "1")
    assert should_daemonize(foreground=False) is False
