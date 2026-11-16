#!/usr/bin/env bash
# Install convenient Linux re-launch entries (app menu + ~/.local/bin).
# Usage (from repo or portable root):
#   scripts/install_linux_launchers.sh
#   scripts/install_linux_launchers.sh /path/to/voice-type-linux
set -euo pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
ROOT="$(cd "$ROOT" && pwd)"
LAUNCHER="$ROOT/voice-type"
if [[ ! -x "$LAUNCHER" ]]; then
  echo "!! not executable: $LAUNCHER"
  exit 1
fi

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTO_DIR="$HOME/.config/autostart"
mkdir -p "$BIN_DIR" "$APP_DIR" "$AUTO_DIR"

ln -sfn "$LAUNCHER" "$BIN_DIR/voice-type"
chmod +x "$LAUNCHER"

# Visible in the app menu / Activities search — after Quit, open again from here.
cat > "$APP_DIR/voice-type.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-type
GenericName=Voice typing
Comment=离线语音输入（右 Alt 开始/结束）
Exec=$LAUNCHER
TryExec=$LAUNCHER
Icon=audio-input-microphone
Terminal=false
Categories=Utility;AudioVideo;
Keywords=voice;dictation;asr;语音;
StartupNotify=false
EOF

# Login autostart (hidden from menu clutter).
cat > "$AUTO_DIR/voice-type.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-type
Comment=Offline push-to-talk dictation
Exec=$LAUNCHER
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

# Hint if ~/.local/bin is not on PATH in this shell.
case ":$PATH:" in
  *":$BIN_DIR:"*) PATH_OK=1 ;;
  *) PATH_OK=0 ;;
esac

echo "[launchers] app menu: $APP_DIR/voice-type.desktop"
echo "[launchers] command:  $BIN_DIR/voice-type -> $LAUNCHER"
if [[ $PATH_OK -eq 0 ]]; then
  echo "[launchers] 提示: 当前 shell 的 PATH 没有 $BIN_DIR"
  echo "           新开一个终端，或把下面这行加进 ~/.bashrc："
  echo "           export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo "[launchers] 退出后再开：应用菜单搜 voice-type，或终端执行 voice-type"
