@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-win\Scripts\python.exe" (
  ".venv-win\Scripts\python.exe" scripts\windows_launcher.py start %*
  goto :done
)
echo Windows environment not found. Run setup_windows.bat first.
echo Then run this file again and open http://127.0.0.1:8765
pause
exit /b 1
:done
set "PCB_EXIT=%errorlevel%"
if not "%PCB_EXIT%"=="0" echo Startup failed. Run setup_windows.bat or read README.md.
pause
exit /b %PCB_EXIT%
