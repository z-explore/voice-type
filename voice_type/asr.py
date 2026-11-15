"""Speech-to-text engines.

LocalSenseVoice  - default, fully offline (sherpa-onnx + SenseVoice-Small int8).
CloudWhisper     - optional, DISABLED by default; any OpenAI-compatible
                   /audio/transcriptions endpoint (Groq, OpenAI, self-hosted).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("voice_type.asr")


class LocalSenseVoice:
    def __init__(self, model_dir: str, language: str = "zh", num_threads: int = 2, use_itn: bool = True):
        import sherpa_onnx  # imported lazily so tests / --help do not need it

        md = Path(model_dir)
        model = md / "model.int8.onnx"
        if not model.exists():
            model = md / "model.onnx"
        tokens = md / "tokens.txt"
        if not model.exists() or not tokens.exists():
            raise FileNotFoundError(
                f"找不到模型文件: {md}\n请先运行 ./setup.sh (或 ./scripts/download_model.sh) 下载模型。"
            )
        lang = "" if language in ("auto", "", None) else language
        self.rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model), tokens=str(tokens), num_threads=int(num_threads),
            language=lang, use_itn=bool(use_itn),
        )
        log.info("local model loaded: %s (language=%s)", model.name, language or "auto")

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        s = self.rec.create_stream()
        s.accept_waveform(sample_rate, samples.astype(np.float32))
        self.rec.decode_stream(s)
        text = s.result.text or ""
        return re.sub(r"<\|[^|]*\|>", "", text).strip()


def _to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class CloudWhisper:
    """OpenAI-compatible transcription endpoint. Only used if [cloud].enabled = true."""

    def __init__(self, base_url: str, model: str, api_key_env: str, language: str = "zh", timeout_s: int = 30):
        self.url = base_url.rstrip("/") + "/audio/transcriptions"
        self.model = model
        self.key = os.environ.get(api_key_env, "")
        if not self.key:
            raise RuntimeError(f"云端识别已启用，但环境变量 {api_key_env} 为空")
        self.language = "" if language in ("auto", "", None) else language
        self.timeout = timeout_s

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        boundary = uuid.uuid4().hex
        fields = {"model": self.model, "response_format": "json"}
        if self.language:
            fields["language"] = self.language
        parts = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n".encode()
            + _to_wav_bytes(samples, sample_rate) + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            self.url, data=b"".join(parts), method="POST",
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("text", "").strip()


class FallbackASR:
    def __init__(self, primary, fallback_factory):
        self.primary, self._factory, self._fb = primary, fallback_factory, None

    def transcribe(self, samples, sr):
        try:
            return self.primary.transcribe(samples, sr)
        except Exception as e:  # network down, quota, ...
            log.warning("cloud ASR failed (%s), falling back to local model", e)
            if self._fb is None:
                self._fb = self._factory()
            return self._fb.transcribe(samples, sr)


def build_asr(cfg: dict):
    a, c = cfg["asr"], cfg["cloud"]
    local = lambda: LocalSenseVoice(a["model_dir"], a["language"], a["num_threads"], a["use_itn"])  # noqa: E731
    if a.get("engine") == "cloud" and c.get("enabled"):
        cloud = CloudWhisper(c["base_url"], c["model"], c["api_key_env"], a["language"], c["timeout_s"])
        log.warning("using CLOUD ASR: audio is sent to %s", c["base_url"])
        return FallbackASR(cloud, local) if c.get("fallback_to_local") else cloud
    return local()


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    if sw != 2:
        raise ValueError("only 16-bit PCM wav supported")
    x = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr
