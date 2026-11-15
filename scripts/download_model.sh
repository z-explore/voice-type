#!/usr/bin/env bash
# Download the SenseVoice-Small int8 model (official sherpa-onnx GitHub release) into ./models
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${NAME}.tar.bz2"
# SHA-256 of the archive as downloaded from the URL above on 2026-11-13 (recorded by us, not
# published by upstream). If upstream ever re-uploads, verify the new file yourself and update.
SHA256="7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e"

mkdir -p models
if [[ -f "models/${NAME}/model.int8.onnx" && -f "models/${NAME}/tokens.txt" ]]; then
  echo "[model] already present: models/${NAME}"; exit 0
fi
ARCHIVE="models/${NAME}.tar.bz2"
if [[ ! -f "$ARCHIVE" ]]; then
  echo "[model] downloading ~163 MB from $URL"
  curl -fL --retry 3 -o "${ARCHIVE}.part" "$URL"
  mv "${ARCHIVE}.part" "$ARCHIVE"
fi
echo "[model] verifying sha256"
echo "${SHA256}  ${ARCHIVE}" | sha256sum -c - || { echo "!! checksum mismatch, deleting $ARCHIVE"; rm -f "$ARCHIVE"; exit 1; }
if command -v bzip2 >/dev/null; then
  tar -xjf "$ARCHIVE" -C models
else  # no bzip2 binary: use Python's tarfile
  python3 -c "import sys,tarfile; tarfile.open(sys.argv[1]).extractall(sys.argv[2])" "$ARCHIVE" models
fi
rm -f "$ARCHIVE"
echo "[model] ok: models/${NAME} ($(du -sh "models/${NAME}" | cut -f1))"
