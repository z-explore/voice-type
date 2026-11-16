#!/usr/bin/env bash
# Finish Linux portable install: system libs + permissions + easy re-launch.
# Run from the extracted voice-type-linux folder.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"

if [[ ! -x "$ROOT/voice-type" ]]; then
  echo "!! voice-type binary not found in $ROOT"
  exit 1
fi

if [[ ! -f "$ROOT/config.toml" && -f "$ROOT/config.example.toml" ]]; then
  cp "$ROOT/config.example.toml" "$ROOT/config.toml"
fi

MODEL="$ROOT/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx"
if [[ ! -f "$MODEL" ]]; then
  echo "!! model missing under models/ — re-download the full Release tarball"
  exit 1
fi

echo "== apt runtime packages (sudo) =="
PKGS=(libportaudio2 xdotool xclip wl-clipboard libnotify-bin python3-gi gir1.2-gtk-3.0 desktop-file-utils)
for p in wtype ydotool; do apt-cache show "$p" >/dev/null 2>&1 && PKGS+=("$p"); done
sudo apt-get update
sudo apt-get install -y "${PKGS[@]}"

echo "== permissions (sudo) =="
sudo usermod -aG input "$USER"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/80-voice-type-uinput.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger || true
echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
sudo modprobe uinput || true
if command -v ydotoold >/dev/null; then
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/ydotoold.service <<'EOF'
[Unit]
Description=ydotool daemon
[Service]
ExecStart=/usr/bin/ydotoold
Restart=on-failure
[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now ydotoold.service || true
fi

echo "== launchers (app menu + voice-type 命令) =="
# Portable zip has no scripts/; embed the same installer logic here.
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTO_DIR="$HOME/.config/autostart"
mkdir -p "$BIN_DIR" "$APP_DIR" "$AUTO_DIR"
ln -sfn "$ROOT/voice-type" "$BIN_DIR/voice-type"
cat > "$APP_DIR/voice-type.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-type
GenericName=Voice typing
Comment=离线语音输入（右 Alt 开始/结束）
Exec=$ROOT/voice-type
TryExec=$ROOT/voice-type
Icon=audio-input-microphone
Terminal=false
Categories=Utility;AudioVideo;
Keywords=voice;dictation;asr;语音;
StartupNotify=false
EOF
cat > "$AUTO_DIR/voice-type.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-type
Comment=Offline push-to-talk dictation
Exec=$ROOT/voice-type
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
update-desktop-database "$APP_DIR" 2>/dev/null || true

echo
echo "== done =="
echo "请注销并重新登录一次（input 组生效）。"
echo "启动 / 退出后再开："
echo "  · 应用菜单 / Activities 搜索：voice-type"
echo "  · 终端：voice-type   （命令在 $BIN_DIR）"
echo "热键：右 Alt 按一下开始，再按一下结束并输入。"
