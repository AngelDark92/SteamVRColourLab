@echo off
setlocal
cd /d "%~dp0"
if not defined COLOURLAB_OUTPUT_ROOT set "COLOURLAB_OUTPUT_ROOT=%~dp0..\builds\SteamVRColourLab"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%COLOURLAB_OUTPUT_ROOT%\.venv\Scripts\python.exe" (
    echo Run start_windows.bat once to install dependencies, then close the app.
    pause
    exit /b 1
)
"%COLOURLAB_OUTPUT_ROOT%\.venv\Scripts\python.exe" -m unittest discover -v
set result=%errorlevel%
pause
exit /b %result%
