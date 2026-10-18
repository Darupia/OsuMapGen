@echo off
rem Runs the automated test suite (synthetic, copyright-free audio fixtures).
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\OsuMapGen\venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Run "Setup or Repair.bat" first.
  pause
  exit /b 1
)
"%VENV%\Scripts\python.exe" -m pytest tests -q %*
pause
