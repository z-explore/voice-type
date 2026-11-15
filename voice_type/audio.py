"""Microphone capture (PortAudio via sounddevice). The stream is only open while recording."""
from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger("voice_type.audio")

# Waveform analysis, same as Handy's AudioVisualiser: 512-sample Hann FFT, 16 bands with
# quadratic spacing, dB window calibrated on real mic audio (room tone stays at the floor).
VIS_WINDOW = 512
VIS_BUCKETS = 16
VIS_FREQ = (400.0, 4000.0)
VIS_DB_MIN, VIS_DB_MAX, VIS_GAIN, VIS_CURVE = -68.0, -30.0, 1.3, 0.7


def spectrum_levels(samples: np.ndarray, sr: int, n: int = VIS_BUCKETS) -> list[float]:
    """First n of VIS_BUCKETS band levels in 0..1 for the last VIS_WINDOW samples."""
    if samples.size < VIS_WINDOW:
        return [0.0] * n
    x = samples[-VIS_WINDOW:].astype(np.float32)
    x = (x - x.mean()) * np.hanning(VIS_WINDOW).astype(np.float32)
    mag = np.abs(np.fft.rfft(x))
    fmin, fmax = VIS_FREQ
    out = []
    for b in range(VIS_BUCKETS):
        lo = fmin + (fmax - fmin) * (b / VIS_BUCKETS) ** 2
        hi = fmin + (fmax - fmin) * ((b + 1) / VIS_BUCKETS) ** 2
        s = min(int(lo * VIS_WINDOW / sr), VIS_WINDOW // 2)
        e = min(max(int(hi * VIS_WINDOW / sr), s + 1), VIS_WINDOW // 2)
        power = float(np.mean(mag[s:e] ** 2)) if e > s else 0.0
        db = 20 * np.log10(np.sqrt(power) / VIS_WINDOW) if power > 1e-12 else -80.0
        v = min(1.0, max(0.0, (db - VIS_DB_MIN) / (VIS_DB_MAX - VIS_DB_MIN)))
        out.append(min(1.0, (v * VIS_GAIN) ** VIS_CURVE))
    smooth = out[:]
    for i in range(1, len(out) - 1):
        smooth[i] = out[i] * 0.7 + out[i - 1] * 0.15 + out[i + 1] * 0.15
    return smooth[:n]


class Recorder:
    def __init__(self, sample_rate: int = 16000, device: str | int | None = None, max_seconds: int = 120):
        self.sr = sample_rate
        self.device = None if device in ("", None) else (int(device) if str(device).isdigit() else device)
        self.max_frames = int(max_seconds * sample_rate)
        self._chunks: list[np.ndarray] = []
        self._n = 0
        self._stream = None
        self._lock = threading.Lock()
        self._tail = np.zeros(0, np.float32)   # last VIS_WINDOW samples, for the waveform

    def levels(self, n: int = 9) -> list[float]:
        return spectrum_levels(self._tail, self.sr, n)

    def _cb(self, indata, frames, time_info, status):
        if status:
            log.debug("audio status: %s", status)
        self._tail = np.concatenate((self._tail, indata[:, 0]))[-VIS_WINDOW:]
        with self._lock:
            if self._n < self.max_frames:
                self._chunks.append(indata[:, 0].copy())
                self._n += frames

    def start(self) -> None:
        import sounddevice as sd
        with self._lock:
            self._chunks, self._n = [], 0
        self._stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                      device=self.device, callback=self._cb, blocksize=0)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        self._tail = np.zeros(0, np.float32)
        with self._lock:
            out = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks, self._n = [], 0
        return out

    @property
    def active(self) -> bool:
        return self._stream is not None


class FakeRecorder:
    """Dry-run stand-in for Recorder: every "recording" returns the same wav file.
    Lets you exercise hotkey -> ASR -> cleanup -> insert without a microphone."""

    def __init__(self, wav_path: str, sample_rate: int = 16000):
        from .asr import read_wav
        self.samples, sr = read_wav(wav_path)
        if sr != sample_rate:  # cheap linear resample, test path only
            n = int(len(self.samples) * sample_rate / sr)
            self.samples = np.interp(np.linspace(0, len(self.samples) - 1, n),
                                     np.arange(len(self.samples)), self.samples).astype(np.float32)
        self._on = False

    def levels(self, n: int = 9) -> list[float]:
        return [0.0] * n

    def start(self) -> None:
        self._on = True

    def stop(self) -> np.ndarray:
        self._on = False
        return self.samples

    @property
    def active(self) -> bool:
        return self._on


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def beep(freq: float = 880.0, ms: int = 70, volume: float = 0.15) -> None:
    """Short non-blocking cue tone. Silently does nothing if there is no output device."""
    try:
        import sounddevice as sd
        sr = 22050
        t = np.arange(int(sr * ms / 1000)) / sr
        env = np.minimum(1.0, np.minimum(t, t[::-1]) * 200)  # 5 ms fade in/out, no clicks
        sd.play((np.sin(2 * np.pi * freq * t) * env * volume).astype(np.float32), sr)
    except Exception:
        pass
