import numpy as np

from voice_type.audio import spectrum_levels
from voice_type.overlay import WAVE_H, bar_position, level_to_height, parse_xdotool_location


def test_wave_height_grows_with_level_and_is_clamped():
    assert level_to_height(0.0) == 3
    assert level_to_height(-1.0) == 3
    assert level_to_height(0.2) < level_to_height(0.5) < level_to_height(0.9)
    assert level_to_height(10.0) == WAVE_H


def test_spectrum_levels_silent_vs_speech_like():
    sr = 16000
    t = np.arange(sr // 4) / sr
    quiet = (np.random.default_rng(0).standard_normal(t.size) * 1e-4).astype(np.float32)
    voice = (0.1 * np.sin(2 * np.pi * 600 * t) + 0.05 * np.sin(2 * np.pi * 1200 * t)).astype(np.float32)
    assert max(spectrum_levels(quiet, sr, 9)) < 0.2
    assert max(spectrum_levels(voice, sr, 9)) > 0.6
    assert spectrum_levels(voice[:100], sr, 9) == [0.0] * 9
    assert all(0.0 <= v <= 1.0 for v in spectrum_levels(voice * 50, sr, 16))


def test_parse_xdotool_location():
    text = "X=120\nY=340\nSCREEN=0\nWINDOW=123\n"
    assert parse_xdotool_location(text) == (120, 340)
    assert parse_xdotool_location("nope") is None


def test_bar_near_pointer_below_right():
    assert bar_position((100, 80), 160, 48, 1920, 1080) == (116, 104)


def test_bar_flips_near_screen_edge():
    x, y = bar_position((1900, 1060), 160, 48, 1920, 1080)
    assert x + 160 <= 1920 - 8
    assert y + 48 <= 1080 - 8


def test_bar_falls_back_to_bottom_center_without_pointer():
    x, y = bar_position(None, 160, 48, 1920, 1080)
    assert x == (1920 - 160) // 2
    assert y == 1080 - 48 - 80
