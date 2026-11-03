@echo off
cd /d "%~dp0"
python robot_sim.py
if errorlevel 1 pause
