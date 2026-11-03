@echo off
cd /d "%~dp0"
pwsh.exe -NoLogo -NoProfile -File "%~dp0serial_monitor.ps1"
if errorlevel 1 pause
