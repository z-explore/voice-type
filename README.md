# voice-type：Ubuntu 离线语音输入（按一下右 Alt 说话）

一个轻量的系统级语音输入工具，思路类似 Typeless，但专为内存不大的 Ubuntu 电脑设计：

- **按一下右 Alt 开始说话，再按一下结束，并把文字打到当前光标处**（任意软件：浏览器、微信网页版、编辑器、终端……）。
- **录音时屏幕底部居中会出现一个黑色小胶囊**（参考 Typeless）：浅色竖条跟着声音跳动，安静时是一排静止的小点；之后显示“识别中…”，文字输入后自动消失。语音条没有按钮，鼠标可以直接穿过。系统没有 `python3-gi` 时退回到鼠标旁的简易语音条。
- **完全离线**：第一次安装时下载一个小模型（约 163 MB 下载、解压后约 230 MB），之后不联网也能用。
- **中文优先**，中英夹杂（比如“用 Python 写个 demo”）也能识别；自动加标点。
- **只做保守清理**：去掉“呃、嗯、啊”这类口头禅和“我觉得我觉得”这类重复，**不改写、不润色你的原话**。
- 没有账号、没有遥测、不上传任何数据（云端识别默认关闭，见最后一节）。

## 1. 用的是什么模型，为什么

识别引擎：[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) + **SenseVoice-Small（int8 量化版）**，模型来自 sherpa-onnx 官方 GitHub Release。

选它的理由（和其它候选比较）：

| 候选 | 结论 |
|---|---|
| **SenseVoice-Small int8（选用）** | 中文准确度在小模型里很好，支持中/英/粤/日/韩，中英混说不用切换；非自回归，CPU 上很快；自带标点和数字规整。 |
| Vosk small-cn | 更小、更省内存，但中文准确度明显差一截，且没有标点。 |
| Whisper tiny / base（faster-whisper、whisper.cpp） | tiny/base 的中文效果偏弱，常出繁体或在静音时“编”句子；更大的型号又太吃内存。 |
| Paraformer-zh | 中文也很好，但 SenseVoice 对中英混说更友好。 |

### 硬件预期

下面的数字是**在开发用的服务器上实测**的（8 核虚拟机），**不是你电脑上的数据**，你的机器上请自己用 `./voice-type --transcribe-file` 看日志里的数字：

- 进程峰值内存约 **350 MiB**（加载模型 + 识别一段 8 秒的话）。
- 识别 8 秒音频约 0.3 秒（2 线程）/ 0.5 秒（1 线程）。

经验上：2 GB 以上可用内存、任意近十年的 x86-64 CPU 应该够用；CPU 很弱就把 `num_threads` 设为 1。

## 2. 安装（Ubuntu 22.04 / 24.04）

```bash
# 把项目放到 ~/voice-type（后面的开机自启默认用这个路径）
cd ~/voice-type
./setup.sh --permissions
```

`setup.sh` 会做这些事（需要输入 sudo 密码）：

1. 用 apt 安装：`libportaudio2`（录音）、`xdotool xclip`（X11 插字）、`wl-clipboard wtype ydotool`（Wayland 插字）、`libnotify-bin`（桌面提示）、`python3-gi gir1.2-gtk-3.0`（底部圆角语音条）、`python3-tk`（简易语音条）、`python3-venv python3-dev gcc bzip2` 等；
2. 建虚拟环境 `.venv`，安装 Python 依赖（`requirements.txt`）；
3. 下载模型到 `models/`，并做 SHA-256 校验；
4. 生成 `config.toml`；
5. 加上 `--permissions` 时还会：把你加入 `input` 组、给 `/dev/uinput` 加 udev 规则、启用 `ydotoold` 用户服务。

**装完后请注销并重新登录一次**（`input` 组要重新登录才生效）。

然后检查环境：

```bash
./voice-type --check
```

每一行 `[OK ]` 表示没问题，`[!! ]` 的那一行会告诉你缺什么。

## 3. 使用

```bash
./voice-type          # 前台运行，终端里能看到状态日志
```

- **按一下右 Alt** → 听到“嘀”一声，屏幕底部出现带声音波动的语音条 → 开始说话；
- **再按一下右 Alt** → 语音条变为“识别中”→ 文字出现在光标处，语音条短暂显示“已输入”后消失。
- **右 Alt 和其他键一起按（例如 Alt+Tab，或用 AltGr 输入特殊字符）不会启动或结束录音**，组合键照常工作。
- 程序不会“吞掉” Alt 键，其它软件照样能收到它。

### 想改成别的键？只改一行

打开 `config.toml`，例如改回左 Alt：

```toml
key = "KEY_LEFTALT"
```

也可以用 `KEY_RIGHTCTRL`、`KEY_SCROLLLOCK`、`KEY_F8` 等，改完后重启程序。

### 其它常用命令

```bash
./voice-type --list-devices                 # 列出麦克风，选错了可在 [audio].device 指定
./voice-type --transcribe-file 录音.wav     # 识别一个 wav 文件（测试模型效果）
./voice-type --clean "呃，我我觉得可以"      # 只测试清理规则
./voice-type --fake-audio 录音.wav          # 不用麦克风试运行：每次按 Alt 都当作说了这段话
./voice-type -v                              # 详细日志
```

### 开机自动运行（可选）

方法一，systemd 用户服务（登录桌面后自动启动，崩溃会自动重启）：

```bash
scripts/install_service.sh                   # 安装并立即启动（自动填好项目路径）
systemctl --user status voice-type           # 看状态
journalctl --user -u voice-type -f           # 看日志
systemctl --user restart voice-type          # 改了 config.toml 后重启
scripts/install_service.sh --uninstall       # 取消开机自启
```

服务运行时再手动执行 `./voice-type` 会提示“已经在运行”并退出，避免同一句话被输入两次。

方法二，桌面自启：把 `packaging/voice-type.desktop` 复制到 `~/.config/autostart/`，改掉里面的路径。
如果用 systemd 方式时插字没反应，多半是服务拿不到 `DISPLAY` / `WAYLAND_DISPLAY`，换方法二即可。

## 4. 文字是怎么打进去的

中文如果一个字一个字“模拟按键”很容易乱码，所以默认用 **剪贴板 + 粘贴快捷键**，粘贴完会把你原来的剪贴板文字恢复回去：

| 桌面环境 | 方式 |
|---|---|
| X11（Ubuntu 选“Ubuntu on Xorg”登录） | `xclip` 写剪贴板 + `xdotool` 按 Ctrl+V；检测到终端窗口时自动改按 Ctrl+Shift+V |
| Wayland（GNOME，Ubuntu 默认） | `wl-copy` 写剪贴板 + `ydotool` 按 Ctrl+V（需要 `ydotoold` 在运行） |
| Wayland（KDE、Sway 等） | `wtype` 直接输入 Unicode 文字 |
| 以上都不行 | 只复制到剪贴板，提示你自己按 Ctrl+V |

可以在 `[insert].backend` 里强制指定。

## 5. 权限说明

- **麦克风**：Ubuntu 桌面一般不用额外授权；如果录不到声音，到“设置 → 声音 → 输入”确认选对了麦克风、音量不是 0，或用 `--list-devices` 指定设备。
- **input 组**（读取按键）：Wayland 下普通程序拿不到全局按键，所以本程序直接读 `/dev/input`，需要 `sudo usermod -aG input $USER` 后重新登录。
  ⚠️ 注意：加入 input 组后，你这个账户下的任何程序理论上都能读到键盘输入。这是 Linux 上所有同类工具（包括 ydotool）的共同代价。本程序只判断热键，**不记录、不保存任何按键内容**。
- **ydotool**（GNOME Wayland 下发送 Ctrl+V）：需要能写 `/dev/uinput`（`--permissions` 已加 udev 规则）并运行 `ydotoold`：`systemctl --user status ydotoold`。Ubuntu 22.04 自带的是旧版 ydotool 0.1.x，不需要守护进程。
- X11 下如果不想加 input 组，程序会自动退回 `pynput` 监听按键，无需额外权限。

## 6. 清理规则（只删不改）

会删掉的：

- 口头禅：呃、嗯、唔；句首或标点后的 啊 / 哦 / 哟 / 额 / 诶；单独成句的“那个，”“就是说，”；“那个”后面紧跟“我/你/他”时（如“那个我觉得”）；英文 um / uh / er。
- 重复：`我觉得我觉得` → `我觉得`，`然后然后` → `然后`，`我我我` → `我`，`the the` → `the`。
- 停顿号 `……` 换成逗号，多余的连续标点合并。

不会动的（举例）：`那个文件`、`这个我不知道`、`好啊`、`谢谢`、`看看`、`研究研究`、`金额`、`very very`。
拿不准的一律保留。不想要任何清理：`[cleanup] enabled = false`。

## 7. 已知限制

- 在部分欧洲键盘布局里，右 Alt 等于 AltGr，用来输入特殊字符。本程序把“右 Alt + 其他键”当成组合键，不会误开或误关录音；如果这个键对你来说很常用，可改成 ScrollLock 或 F8。
- 底部语音条通过 XWayland 显示（GNOME Wayland 不允许普通窗口自己定位）；多显示器时显示在主显示器上。
- 识别是“说完再识别”，不是边说边出字；一次最长 120 秒（可改）。
- 小模型对专有名词、英文拼写会出错（实测中把 “Python” 识别成了 “pyython”）。
- GNOME Wayland 下必须有 ydotool；没有的话只能复制到剪贴板、你手动粘贴。
- 只在 x86-64 上测过安装路径；ARM 理论上可用（sherpa-onnx 有 ARM 包），未验证。

## 8. 以后可以加云端识别

小模型不够准时，可以换成云端的 Whisper 级别模型（Groq、OpenAI 或任何 OpenAI 兼容接口）。代码已经留好接口，**默认关闭**，打开后录音会上传给你选的服务商：

```toml
[asr]
engine = "cloud"

[cloud]
enabled = true
base_url = "https://api.groq.com/openai/v1"
model = "whisper-large-v3-turbo"
api_key_env = "VOICE_TYPE_API_KEY"
fallback_to_local = true     # 断网时自动回到本地模型
```

API Key 只从环境变量读：`export VOICE_TYPE_API_KEY=...`，不要写进配置文件。

## 9. 项目结构

```
voice_type/
  __main__.py   命令行入口 (--check / --transcribe-file / --fake-audio ...)
  app.py        主流程：热键 → 录音 → 识别 → 清理 → 插入
  hotkey.py     右 Alt 开关式热键（按一下开始、再按一下结束）+ evdev / pynput 监听
  overlay.py    语音条控制（底部黑色胶囊 / 简易语音条回退）
  overlay_gtk.py 底部圆角语音条的绘制（用系统 python3 + GTK 运行）
  audio.py      录音（只在按住时打开麦克风）、提示音
  asr.py        本地 SenseVoice / 可选云端接口
  cleanup.py    保守清理规则
  inserter.py   X11 / Wayland 插入文字
  notify.py     桌面提示
tests/          单元测试：.venv/bin/pip install pytest && .venv/bin/python -m pytest -q
scripts/download_model.sh   下载并校验模型
packaging/      systemd 服务、ydotoold 服务、自启 .desktop
```

模型许可：SenseVoice 模型遵循 [FunASR 的模型许可](https://github.com/modelscope/FunASR?tab=readme-ov-file#license)（见 `models/<模型目录>/LICENSE`）；sherpa-onnx 为 Apache-2.0。
