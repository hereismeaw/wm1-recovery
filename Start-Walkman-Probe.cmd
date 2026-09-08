@echo off
cd /d "%~dp0"
python -m walkman_recovery
if errorlevel 1 pause
