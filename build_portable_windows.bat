@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Build-Portable.ps1" %*
set "build_exit=%errorlevel%"
if not "%build_exit%"=="0" echo Build failed. Read the errors above.
pause
exit /b %build_exit%
