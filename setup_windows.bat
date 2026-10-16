@echo off
setlocal
cd /d "%~dp0"
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  py -3.12 scripts\windows_launcher.py setup %*
  goto :done
)
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  py -3 scripts\windows_launcher.py setup %*
  goto :done
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  python scripts\windows_launcher.py setup %*
  goto :done
)
echo Python not found. Install Python 3.12 64-bit from https://www.python.org/downloads/windows/
echo Select "Add python.exe to PATH" during installation.
exit /b 1
:done
set "PCB_EXIT=%errorlevel%"
if not "%PCB_EXIT%"=="0" echo Setup failed. See the error above and README.md.
pause
exit /b %PCB_EXIT%
