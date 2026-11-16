#!/usr/bin/env bash
# voice-type installer for Ubuntu 22.04 / 24.04.
#   ./setup.sh                 system packages + venv + Python deps + model
#   ./setup.sh --permissions   additionally: add you to group "input", /dev/uinput udev rule,
#                              and a ydotoold user service (needed on Wayland / GNOME)
#   ./setup.sh --no-apt        skip apt (if you installed packages yourself)
set -euo pipefail
cd "$(dirname "$0")"
DO_APT=1; DO_PERM=0
for a in "$@"; do
  case "$a" in
    --permissions) DO_PERM=1 ;;
    --no-apt) DO_APT=0 ;;
    -h|--help) sed -n 2,7p "$0"; exit 0 ;;
  esac
done

if [[ $DO_APT == 1 ]]; then
  echo "== apt packages (sudo) =="
  PKGS=(python3-venv python3-dev gcc curl bzip2 libportaudio2
        xdotool xclip wl-clipboard libnotify-bin python3-tk python3-gi gir1.2-gtk-3.0)
  # wtype / ydotool exist in Ubuntu universe; install if available
  for p in wtype ydotool; do apt-cache show "$p" >/dev/null 2>&1 && PKGS+=("$p"); done
  sudo apt-get update
  sudo apt-get install -y "${PKGS[@]}"
fi

echo "== python venv =="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel >/dev/null
if ! .venv/bin/pip install -r requirements.txt; then
  # Usually means python3-dev/gcc are missing so evdev could not compile.
  # Fallback: prebuilt evdev wheel (evdev-binary) + the rest without building evdev.
  echo "!! pip install failed, retrying with prebuilt evdev-binary"
  .venv/bin/pip install evdev-binary
  grep -vE '^(evdev|pynput)' requirements.txt > .venv/req-noevdev.txt
  .venv/bin/pip install -r .venv/req-noevdev.txt
  .venv/bin/pip install --no-deps "pynput>=1.7.6,<2" && .venv/bin/pip install python-xlib six
fi

echo "== model =="
python3 scripts/download_model.py || bash scripts/download_model.sh

[[ -f config.toml ]] || { cp config.example.toml config.toml; echo "created config.toml"; }
chmod +x voice-type

if [[ $DO_PERM == 1 ]]; then
  echo "== permissions (sudo) =="
  sudo usermod -aG input "$USER"
  echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
    | sudo tee /etc/udev/rules.d/80-voice-type-uinput.rules >/dev/null
  sudo udevadm control --reload-rules && sudo udevadm trigger || true
  echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null; sudo modprobe uinput || true
  if command -v ydotoold >/dev/null; then
    mkdir -p ~/.config/systemd/user
    cp packaging/ydotoold.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable ydotoold.service || true
    echo "ydotoold user service enabled (starts after you log in again)"
  fi
  echo ">> 请注销并重新登录一次，input 组权限才会生效。"
fi

echo
echo "== done =="
echo "检查环境:  ./voice-type --check"
echo "开始使用:  ./voice-type        (按一下右 Alt 开始说话，再按一下结束并输入)"
