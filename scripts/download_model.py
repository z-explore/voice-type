#!/usr/bin/env python3
"""Download SenseVoice int8 model into ./models (Linux / Windows / CI)."""
from __future__ import annotations

import hashlib
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{NAME}.tar.bz2"
SHA256 = "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e"


def ensure_model(project_dir: Path | None = None, progress: bool = True) -> Path:
    root = Path(project_dir) if project_dir else ROOT
    models = root / "models"
    dest = models / NAME
    if (dest / "model.int8.onnx").exists() and (dest / "tokens.txt").exists():
        if progress:
            print(f"[model] already present: {dest}")
        return dest

    models.mkdir(parents=True, exist_ok=True)
    archive = models / f"{NAME}.tar.bz2"
    if not archive.exists():
        if progress:
            print(f"[model] downloading ~163 MB from {URL}")
        part = archive.with_suffix(archive.suffix + ".part")

        def _hook(count, block, total):
            if not progress or total <= 0:
                return
            done = min(count * block, total)
            pct = done * 100 // total
            print(f"\r[model] {pct}% ({done // (1024 * 1024)} / {total // (1024 * 1024)} MiB)", end="", flush=True)

        urllib.request.urlretrieve(URL, part, reporthook=_hook if progress else None)
        if progress:
            print()
        part.replace(archive)

    if progress:
        print("[model] verifying sha256")
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if digest != SHA256:
        archive.unlink(missing_ok=True)
        raise SystemExit(f"!! checksum mismatch: got {digest}, expected {SHA256}")

    if progress:
        print(f"[model] extracting into {models}")
    with tarfile.open(archive, "r:bz2") as tar:
        tar.extractall(models)
    archive.unlink(missing_ok=True)
    if not (dest / "model.int8.onnx").exists():
        raise SystemExit(f"!! extract failed, missing {dest / 'model.int8.onnx'}")
    if progress:
        print(f"[model] ok: {dest}")
    return dest


def main() -> int:
    ensure_model()
    return 0


if __name__ == "__main__":
    sys.exit(main())
