"""Main loop: hotkey -> record -> ASR -> cleanup -> insert."""
from __future__ import annotations

import logging
import queue
import threading
import time

from .audio import FakeRecorder, Recorder, rms
from .cleanup import clean_text
from .hotkey import PTTStateMachine, make_listener
from .inserter import Inserter
from .notify import Status

log = logging.getLogger("voice_type")


def postprocess(text: str, cfg: dict) -> str:
    c = cfg["cleanup"]
    if not c.get("enabled", True):
        return text.strip()
    return clean_text(text, c.get("remove_fillers", True), c.get("remove_repeats", True))


class App:
    def __init__(self, cfg: dict, asr, fake_audio: str | None = None):
        self.cfg, self.asr = cfg, asr
        a = cfg["audio"]
        self.rec = (FakeRecorder(fake_audio, a["sample_rate"]) if fake_audio
                    else Recorder(a["sample_rate"], a.get("device"), a["max_seconds"]))
        self.sm = PTTStateMachine(cfg["hotkey"]["key"], cfg["hotkey"]["min_hold_ms"])
        self.ins = Inserter(cfg)
        self.status = Status(cfg, level_fn=lambda: self.rec.levels(7))
        self.jobs: queue.Queue = queue.Queue()
        self._session = 0
        self._lock = threading.Lock()

    # called from the listener thread; must be fast
    def on_action(self, act: str) -> None:
        with self._lock:
            if act == "start":
                self._session += 1
                try:
                    self.rec.start()
                except Exception as e:
                    self.status("error", f"麦克风打开失败: {e}")
                    return
                self.status("recording", "再按一次结束")
            elif act == "cancel":
                self._session += 1
                if self.rec.active:
                    self.rec.stop()
                self.status("cancelled", "已取消")
                log.debug("cancelled")
            elif act == "stop":
                self._session += 1
                audio = self.rec.stop() if self.rec.active else None
                if audio is not None:
                    self.jobs.put(audio)

    def _worker(self) -> None:
        sr = self.cfg["audio"]["sample_rate"]
        while True:
            audio = self.jobs.get()
            try:
                dur = audio.size / sr
                if dur < 0.25 or rms(audio) < self.cfg["audio"]["min_rms"]:
                    self.status("cancelled", f"没有检测到声音 ({dur:.1f}s)")
                    continue
                self.status("transcribing", f"{dur:.1f}s 音频")
                t0 = time.monotonic()
                raw = self.asr.transcribe(audio, sr)
                text = postprocess(raw, self.cfg)
                log.info("raw=%r clean=%r (%.2fs)", raw, text, time.monotonic() - t0)
                if not text:
                    self.status("cancelled", "未识别到文字")
                    continue
                how = self.ins.insert(text)
                self.status("done", f"{text}  [{how}]")
            except Exception as e:
                log.exception("job failed")
                self.status("error", str(e))

    def run(self) -> None:
        threading.Thread(target=self._worker, daemon=True, name="asr-worker").start()
        listener = make_listener(self.cfg, self.sm, self.on_action)
        listener.start()
        key = self.cfg["hotkey"]["key"]
        self.status("ready", f"按一下 {key} 开始说话，再按一下结束并输入 "
                             f"(插入方式: {self.ins.pick_backend()})")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            log.info("bye")
            listener.stop()
