@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run start_windows.bat once to install dependencies, then close the app.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -v
set result=%errorlevel%
pause
exit /b %result%
