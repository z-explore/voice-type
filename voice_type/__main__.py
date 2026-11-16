"""Entry point:  python -m voice_type [options]   (or the ./voice-type wrapper)."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__
from .config import load_config


def _rss_mb() -> float:
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return rss / (1024.0 * 1024.0)
        return rss / 1024.0  # Linux: KiB -> MiB
    except Exception:
        return 0.0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="voice-type", description="离线语音输入 (Linux / Windows)")
    p.add_argument("-c", "--config", help="config.toml 路径")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--transcribe-file", metavar="WAV", help="识别一个 16-bit wav 文件并打印 (测试用)")
    p.add_argument("--insert", action="store_true", help="与 --transcribe-file 一起用: 把结果插入当前窗口")
    p.add_argument("--clean", metavar="TEXT", help="只跑清理规则并打印结果")
    p.add_argument("--check", action="store_true", help="检查环境 (按键权限/麦克风/插入工具/模型)")
    p.add_argument("--fake-audio", metavar="WAV", help="试运行: 不用麦克风，每次按键都用这个 wav 当录音")
    p.add_argument("--list-devices", action="store_true", help="列出音频输入设备")
    p.add_argument(
        "--foreground", "-f",
        action="store_true",
        help="前台运行（默认在终端启动时会进后台，关终端不影响）",
    )
    p.add_argument("--version", action="version", version=__version__)
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(a.config)
    log = logging.getLogger("voice_type")
    log.info("config: %s", cfg["_path"] or "(built-in defaults)")

    if a.clean is not None:
        from .app import postprocess
        print(postprocess(a.clean, cfg))
        return 0

    if a.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        return 0

    if a.check:
        return _check(cfg)

    if not a.transcribe_file and not _single_instance():
        log.error("voice-type 已经在运行（可能是开机自启的服务: systemctl --user status voice-type）")
        return 3

    from .asr import build_asr
    t0 = time.monotonic()
    asr = build_asr(cfg)
    log.info("ASR ready in %.1fs, peak RSS %.0f MiB", time.monotonic() - t0, _rss_mb())

    if a.transcribe_file:
        from .app import postprocess
        from .asr import read_wav
        x, sr = read_wav(a.transcribe_file)
        t0 = time.monotonic()
        raw = asr.transcribe(x, sr)
        dt = time.monotonic() - t0
        clean = postprocess(raw, cfg)
        print(f"raw:   {raw}\nclean: {clean}")
        log.info("audio %.1fs, decode %.2fs (RTF %.2f), peak RSS %.0f MiB",
                 x.size / sr, dt, dt / max(x.size / sr, 1e-6), _rss_mb())
        if a.insert:
            from .inserter import Inserter
            print("inserted via:", Inserter(cfg).insert(clean))
        return 0

    from .platform_util import daemonize, log_file_path, should_daemonize

    if should_daemonize(foreground=a.foreground):
        log_path = log_file_path()
        print(
            f"voice-type 已在后台运行（关闭此终端不会退出）。日志: {log_path}",
            flush=True,
        )
        log.info("detaching from terminal; further logs → %s", log_path)
        daemonize(log_path)
        # Re-bind logging to the daemon's stdout (now the log file).
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        logging.basicConfig(
            level=logging.DEBUG if a.verbose else logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )
        log = logging.getLogger("voice_type")
        log.info("daemon ready (pid %s)", __import__("os").getpid())

    from .app import App
    App(cfg, asr, fake_audio=a.fake_audio).run()
    return 0


_lock_file = None


def _single_instance() -> bool:
    """Two instances would insert every sentence twice. Exit code 3 = already running
    (the systemd unit uses RestartPreventExitStatus=3 so it does not retry)."""
    import os
    global _lock_file
    if sys.platform == "win32":
        from .platform_util import user_data_dir
        path = user_data_dir() / "voice-type.lock"
        _lock_file = open(path, "a+b")
        try:
            import msvcrt
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl
    run_dir = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    _lock_file = open(os.path.join(run_dir, "voice-type.lock"), "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _check(cfg) -> int:
    import os
    import shutil
    from pathlib import Path
    from .hotkey import evdev_available
    from .inserter import Inserter, is_gnome, session_type

    ok_all = True

    def line(ok, name, msg):
        nonlocal ok_all
        ok_all &= bool(ok)
        print(f"[{'OK ' if ok else '!! '}] {name}: {msg}")

    st = session_type()
    line(st != "none", "会话", f"{st} desktop={os.environ.get('XDG_CURRENT_DESKTOP', '?')}")
    ok, why = evdev_available()
    line(ok or st == "x11", "按键监听(evdev)", why + ("" if ok else " (X11 下会退回 pynput)"))
    md = Path(cfg["asr"]["model_dir"])
    line((md / "model.int8.onnx").exists(), "模型", str(md))
    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        line(True, "麦克风", dev["name"])
    except Exception as e:
        line(False, "麦克风", f"找不到输入设备: {e}")
    tools = {t: bool(shutil.which(t)) for t in ("xdotool", "xclip", "wl-copy", "wtype", "ydotool", "notify-send")}
    line(True, "工具", " ".join(f"{k}={'有' if v else '无'}" for k, v in tools.items()))
    from .overlay import gtk_pill_available
    if gtk_pill_available():
        line(True, "语音条(GTK)", "可用，录音时在屏幕底部居中显示黑色胶囊语音条")
    else:
        try:
            import tkinter  # noqa: F401
            line(True, "语音条(tkinter)", "简易版，在鼠标附近显示（装 python3-gi 可用底部圆角语音条）")
        except Exception as e:
            line(False, "语音条", f"不可用（sudo apt install python3-gi 或 python3-tk）: {e}")
    ins = Inserter(cfg)
    b = ins.pick_backend()
    line(b not in ("clipboard", "print"), "插入方式", b + (" (GNOME Wayland 需 ydotool)" if st == "wayland" and is_gnome() else ""))
    if b == "ydotool" and ins._ydotool_legacy():
        line(True, "ydotoold", "旧版 ydotool (0.1.x)，直接写 /dev/uinput，不需要 ydotoold")
    elif b == "ydotool":
        cands = [os.environ.get("YDOTOOL_SOCKET", ""), "/tmp/.ydotool_socket",
                 os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()), ".ydotool_socket")]
        found = [c for c in cands if c and os.path.exists(c)]
        line(bool(found), "ydotoold", found[0] if found else "没找到 socket，ydotoold 没在运行? (Ubuntu 22.04 的旧版 ydotool 不需要)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
