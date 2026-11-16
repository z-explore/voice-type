# Source install on Windows (developers). End users should prefer the Release zip.
param([switch]$NoAutostart)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "!! Install Python 3.10+ from https://www.python.org/ and tick Add to PATH" -ForegroundColor Red
    exit 1
}

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip wheel
.\.venv\Scripts\pip install -r requirements-windows.txt
.\.venv\Scripts\python scripts\download_model.py

if (-not (Test-Path config.toml)) {
    Copy-Item config.example.toml config.toml
}

$Wsh = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$Launcher = Join-Path (Get-Location) "voice-type.bat"
@"
@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m voice_type %*
"@ | Set-Content -Encoding ASCII $Launcher

$s = $Wsh.CreateShortcut((Join-Path $Desktop "voice-type.lnk"))
$s.TargetPath = $Launcher
$s.WorkingDirectory = (Get-Location).Path
$s.WindowStyle = 7
$s.Save()

if (-not $NoAutostart) {
    $Startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\voice-type.lnk"
    $s2 = $Wsh.CreateShortcut($Startup)
    $s2.TargetPath = $Launcher
    $s2.WorkingDirectory = (Get-Location).Path
    $s2.WindowStyle = 7
    $s2.Save()
    Write-Host "autostart: ENABLED"
} else {
    Write-Host "autostart: skipped"
}

Write-Host "done. Double-click desktop voice-type or run voice-type.bat"
