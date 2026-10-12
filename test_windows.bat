@echo off
setlocal
cd /d "%~dp0"
if not defined COLOURLAB_OUTPUT_ROOT set "COLOURLAB_OUTPUT_ROOT=%~dp0..\builds\SteamVRColourLab"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%COLOURLAB_OUTPUT_ROOT%\.venv\Scripts\python.exe" (
    echo No test environment at %COLOURLAB_OUTPUT_ROOT%\.venv. Run start_windows.bat once to install dependencies.
    exit /b 1
)
"%COLOURLAB_OUTPUT_ROOT%\.venv\Scripts\python.exe" -B -m unittest discover -v
set result=%errorlevel%
if not "%result%"=="0" echo Full test suite FAILED with exit code %result%.
exit /b %result%
