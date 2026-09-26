@echo off
setlocal
cd /d "%~dp0"
if exist "SteamVRColourLab.exe" goto portable
if exist "dist\SteamVRColourLab\SteamVRColourLab.exe" goto portable_dist
if exist ".venv\Scripts\python.exe" goto installed_python
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -m venv .venv
if errorlevel 1 goto failure
goto installed_python
:try_python
python -m venv .venv
if errorlevel 1 goto no_python
:installed_python
".venv\Scripts\python.exe" -c "import sys,struct,tkinter; assert sys.version_info >= (3,11) and struct.calcsize('P') == 8, 'Use 64-bit Python 3.11 or newer'"
if errorlevel 1 goto no_python
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failure
if exist "SteamVRColourLab.pyz" (
    ".venv\Scripts\python.exe" SteamVRColourLab.pyz %*
) else (
    ".venv\Scripts\python.exe" app.py %*
)
if errorlevel 1 goto failure
exit /b 0
:portable
"%~dp0SteamVRColourLab.exe" %*
if errorlevel 1 goto failure
exit /b 0
:portable_dist
"%~dp0dist\SteamVRColourLab\SteamVRColourLab.exe" %*
if errorlevel 1 goto failure
exit /b 0
:no_python
echo This source checkout needs 64-bit Python 3.11 or newer with tkinter and pip.
echo To run without Python, use the built portable package in dist.
echo If .venv was made with the wrong Python installation, delete .venv first.
goto failure
:failure
echo.
echo The application could not start or encountered an error. Read the message above.
echo When available, detailed logs are in the runs folder.
pause
exit /b 1
