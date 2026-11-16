# Install from the portable zip (run inside the extracted folder).
# Default: enable login autostart. Use -NoAutostart to skip.
param([switch]$NoAutostart)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Exe = Join-Path $Root "voice-type.exe"
if (-not (Test-Path $Exe)) {
    Write-Host "!! voice-type.exe not found in $Root" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Root "config.toml"))) {
    if (Test-Path (Join-Path $Root "config.example.toml")) {
        Copy-Item (Join-Path $Root "config.example.toml") (Join-Path $Root "config.toml")
    }
}

$model = Join-Path $Root "models\sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17\model.int8.onnx"
if (-not (Test-Path $model)) {
    Write-Host "!! model missing under models\ — re-download the full Release zip" -ForegroundColor Red
    exit 1
}

$Wsh = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$s = $Wsh.CreateShortcut((Join-Path $Desktop "voice-type.lnk"))
$s.TargetPath = $Exe
$s.WorkingDirectory = $Root
$s.WindowStyle = 7
$s.Save()

$Startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\voice-type.lnk"
if ($NoAutostart) {
    if (Test-Path $Startup) { Remove-Item $Startup -Force }
    Write-Host "autostart: disabled"
} else {
    $s2 = $Wsh.CreateShortcut($Startup)
    $s2.TargetPath = $Exe
    $s2.WorkingDirectory = $Root
    $s2.WindowStyle = 7
    $s2.Save()
    Write-Host "autostart: ENABLED (remove Startup shortcut to disable)" -ForegroundColor Green
}

Write-Host "Installed. Desktop shortcut created. Launching…"
Write-Host "Allow microphone access if Windows asks. Hotkey: Right Alt (press to start, press again to stop)."
Start-Process $Exe
