@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m voice_type %*
) else (
  echo Run scripts\setup-windows.ps1 first.
  exit /b 1
)
