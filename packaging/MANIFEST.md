# Release package contents (what users download)

One git repo, **two Release assets**. Cross-platform files stay in git for developers;
each downloadable archive only includes that OS’s files.

## Included in both packages

- Frozen `voice-type` binary (and `_internal/` runtime)
- `models/sherpa-onnx-sense-voice-…/` (offline ASR)
- `config.toml` (from `config.example.toml`)
- Platform README

## Windows zip only

- `voice-type.exe`, `Install.ps1`, `README.txt`
- **Not included:** `setup.sh`, `*.desktop`, `*.service`, `scripts/*.sh`, Linux packaging

## Linux tarball only

- `voice-type` launcher, `install.sh`, `README.txt`
- **Not included:** `*.ps1`, `*.bat`, `packaging/windows/`, Windows requirements

## Kept in git but excluded from Release archives

| Path | Why |
|------|-----|
| `tests/` | Developer only |
| `requirements-dev.txt` | Developer only |
| `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/` | Local / generated |
| `STATUS.md` | Removed — stale internal notes |
| Source tree / other OS packaging scripts | Users get the frozen package instead |

## Not discarded (still useful in repo)

- `setup.sh` / `scripts/setup-windows.ps1` — source installs for developers
- `packaging/voice-type.service` + `scripts/install_service.sh` — Linux source autostart
- `packaging/ydotoold.service` — Wayland paste helper for source installs
