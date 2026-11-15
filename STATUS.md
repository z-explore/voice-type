# STATUS — v0.1.0（2026-11-13，UTC-4）

## 在开发机上实际验证过的

开发机是一台 Debian 13 服务器，Python 3.13，**没有麦克风、没有声卡、没有真实桌面、没有 /dev/input**。

| 项目 | 怎么验证的 | 结果 |
|---|---|---|
| 单元测试 | `python -m pytest -q tests` | 40 个全部通过（清理规则 30、热键状态机 7、evdev 监听器 1、云端接口 2） |
| 模型下载+校验 | 在空目录里跑 `scripts/download_model.sh` 两次 | 下载 163 MB、sha256 通过、解压 230 MB；第二次识别到已存在直接跳过 |
| `setup.sh --no-apt` | 在干净副本里从零跑 | 成功；这台机器缺 Python.h，evdev 编译失败，自动走了 evdev-binary 兜底，成功 |
| 本地识别 | `--transcribe-file` 模型自带 zh.wav / en.wav，以及一段 TTS 合成的带口头禅中文 | 正确；峰值 RSS 约 350 MiB，8.3 秒音频 2 线程 0.28 s / 1 线程 0.48 s（**这台服务器上的数字**） |
| 清理 | 上面那段 TTS：`呃，那个我觉得我觉得这个功能嗯明天可以上线，然后然后我们用pyython写一个demo。` | → `我觉得这个功能明天可以上线，然后我们用pyython写一个demo。` |
| X11 端到端（不含麦克风） | Xvfb 虚拟屏 + pynput 监听 + `--fake-audio` + 测试窗口接收按键 + 假的 xclip 记录剪贴板 | 按住左 Alt 1.2 s → 识别 → 剪贴板写入清理后的文字 → 测试窗口收到 Ctrl+V → 剪贴板恢复成原内容；**Alt+Tab 被放行、没有插入**；短按 Alt 被忽略 |
| evdev 监听（Wayland 路径） | 用管道假装 /dev/input 设备喂事件 | Alt+Tab → cancel，单独按住 → start/stop |
| 云端接口 | 本地假 HTTP 服务器 | 请求路径、Bearer 头、multipart wav 正确；默认关闭 |

## 在开发机上没法验证的（需要在你的 Ubuntu 上试）

- 真实麦克风录音（这里没有声卡，PortAudio 找不到设备）。
- 真实 GNOME Wayland 下 ydotool 粘贴、KDE/Sway 下 wtype 输入；真实 X11 下 xclip 剪贴板与中文粘贴到真实应用（这里只用了假的 xclip）。
- 真实键盘的 evdev 读取、input 组权限、键盘热插拔。
- 桌面通知 notify-send 和提示音。
- `setup.sh` 的 apt 部分（这里没有 sudo），以及 Ubuntu 22.04 的 Python 3.10 环境。
- systemd 用户服务 / 自启动。
- 真实人声（尤其口音、噪声环境、中英夹杂）的识别效果和你机器上的内存/速度。

## 已知问题 / 待办

- 热键已改为开关式右 Alt：按一下开始，再按一下结束。真实桌面上的语音条位置（跟鼠标 / Wayland 居中回退）尚未在用户机器上验证。
- X11 + pynput 模式下，如果系统给 Alt 开了按键连发，理论上可能出现“松开-按下”成对事件，未在真机验证。
- Alt+Tab 时如果 Tab 在按下 Alt 0.3 秒之后才按，会先闪一下“录音中”提示再取消（不会插入文字）。
- 清理规则是保守的规则表，必然漏掉一些口头禅；宁可漏删也不误删。
