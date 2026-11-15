#!/usr/bin/env bash
# Start voice-type automatically after desktop login (systemd user service).
#   scripts/install_service.sh              install + enable + start now
#   scripts/install_service.sh --uninstall  stop + disable + remove
set -euo pipefail
cd "$(dirname "$0")/.."
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/voice-type.service"

if [[ "${1:-}" == "--uninstall" ]]; then
  systemctl --user disable --now voice-type.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl --user daemon-reload
  echo "[service] removed"
  exit 0
fi

[[ -x .venv/bin/python ]] || { echo "!! 先运行 ./setup.sh"; exit 1; }
mkdir -p "$UNIT_DIR"
sed "s|@PROJECT_DIR@|$PWD|" packaging/voice-type.service > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable voice-type.service
systemctl --user restart voice-type.service
echo "[service] installed: $UNIT"
echo "状态: systemctl --user status voice-type    日志: journalctl --user -u voice-type -f"
