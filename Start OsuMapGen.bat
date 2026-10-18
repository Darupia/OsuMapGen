@echo off
rem Double-click to start OsuMapGen. Runs setup automatically the first time.
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\OsuMapGen\venv"
if not exist "%VENV%\osumapgen-ready.txt" (
  echo First run: preparing OsuMapGen. This downloads about 150 MB of packages once.
  call "%~dp0Setup or Repair.bat" /auto
  if errorlevel 1 exit /b 1
)
start "" "%VENV%\Scripts\pythonw.exe" -m osumapgen
exit /b 0
