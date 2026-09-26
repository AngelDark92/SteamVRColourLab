@echo off
call "%~dp0start_windows.bat" --self-test %*
if not errorlevel 1 pause
