from voice_type.hotkey import PTTStateMachine

ALT = "KEY_RIGHTALT"


def run(events, min_hold_ms=0):
    sm = PTTStateMachine(ALT, min_hold_ms)
    return [a for a in (sm.feed(k, d, t=t, repeat=r) for k, d, t, r in events) if a]


def test_tap_starts_then_tap_stops():
    ev = [(ALT, True, 0.0, False), (ALT, False, 0.08, False),
          (ALT, True, 1.0, False), (ALT, False, 1.08, False)]
    assert run(ev) == ["start", "stop"]


def test_start_happens_on_release_not_press():
    sm = PTTStateMachine(ALT)
    assert sm.feed(ALT, True, t=0) is None
    assert sm.feed(ALT, False, t=0.08) == "start"


def test_alt_tab_does_not_toggle():
    ev = [(ALT, True, 0.0, False), ("KEY_TAB", True, 0.05, False), ("KEY_TAB", False, 0.1, False),
          (ALT, False, 0.15, False)]
    assert run(ev) == []


def test_alt_tab_while_recording_does_not_stop():
    ev = [(ALT, True, 0.0, False), (ALT, False, 0.08, False),
          (ALT, True, 1.0, False), ("KEY_TAB", True, 1.05, False), ("KEY_TAB", False, 1.1, False),
          (ALT, False, 1.15, False)]
    assert run(ev) == ["start"]


def test_clean_tap_after_combo_still_starts():
    ev = [(ALT, True, 0, False), ("KEY_TAB", True, 0.05, False), ("KEY_TAB", False, 0.1, False),
          (ALT, False, 0.15, False),
          (ALT, True, 1.0, False), (ALT, False, 1.08, False)]
    assert run(ev) == ["start"]


def test_ctrl_held_before_alt_does_not_start():
    ev = [("KEY_LEFTCTRL", True, 0, False), (ALT, True, 0.1, False), (ALT, False, 0.2, False),
          ("KEY_LEFTCTRL", False, 0.3, False)]
    assert run(ev) == []


def test_repeat_does_not_extra_toggle():
    ev = [(ALT, True, 0.0, False), (ALT, True, 0.1, True), (ALT, False, 0.15, False)]
    assert run(ev) == ["start"]


def test_left_alt_is_not_the_hotkey():
    sm = PTTStateMachine("KEY_RIGHTALT")
    assert sm.feed("KEY_LEFTALT", True, t=0) is None
    sm.feed("KEY_LEFTALT", False, t=0.1)
    assert sm.feed("KEY_RIGHTALT", True, t=1) is None
    assert sm.feed("KEY_RIGHTALT", False, t=1.08) == "start"


def test_mouse_with_alt_is_combo():
    ev = [(ALT, True, 0, False), ("BTN_LEFT", True, 0.05, False), (ALT, False, 0.2, False)]
    assert run(ev) == []
