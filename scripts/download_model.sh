#!/usr/bin/env bash
# Thin wrapper around the cross-platform downloader.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/download_model.py
