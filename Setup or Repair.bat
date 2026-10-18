@echo off
rem First-time setup and repair for OsuMapGen. No administrator rights needed.
setlocal
cd /d "%~dp0"
set "MODE=%~1"
set "PYCMD="

rem Prefer the Python launcher with a known-good version, then any python on PATH.
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PYCMD (
    py -%%V -c "import sys" >nul 2>&1 && set "PYCMD=py -%%V"
  )
)
if not defined PYCMD (
  python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && set "PYCMD=python"
)

if not defined PYCMD (
  echo Python 3.10 - 3.13 was not found.
  where winget >nul 2>&1
  if errorlevel 1 goto :nopython
  echo.
  choice /c YN /m "Install Python 3.12 for your user account now with winget (official Microsoft package manager)"
  if errorlevel 2 goto :nopython
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PYCMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if not defined PYCMD goto :nopython
)

if /i "%MODE%"=="/auto" (
  %PYCMD% "%~dp0setup_env.py"
) else (
  %PYCMD% "%~dp0setup_env.py" --repair
)
if errorlevel 1 (
  echo.
  echo Setup did not finish. Read the messages above for the reason.
  pause
  exit /b 1
)
if /i not "%MODE%"=="/auto" pause
exit /b 0

:nopython
echo.
echo Please install Python 3.12 from https://www.python.org/downloads/
echo (during installation tick "Add python.exe to PATH"), then run this file again.
pause
exit /b 1
