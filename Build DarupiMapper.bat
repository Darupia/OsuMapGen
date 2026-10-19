@echo off
rem Builds dist\DarupiMapper.exe (one file, no console window) from this folder.
rem Needs the private environment made by "Setup or Repair.bat". Installs PyInstaller into it (build tool only).
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\OsuMapGen\venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Run "Setup or Repair.bat" first.
  pause
  exit /b 1
)
"%VENV%\Scripts\python.exe" -m pip install --quiet pyinstaller==6.22.3
if errorlevel 1 ( echo Could not install PyInstaller. & pause & exit /b 1 )
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm DarupiMapper.spec
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
echo.
echo Built: %~dp0dist\DarupiMapper.exe
pause
