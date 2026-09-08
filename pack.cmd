@echo off
cd /d "%~dp0"
python -m pip install -q pyinstaller
python -m PyInstaller --noconfirm --clean pack.spec
echo.
echo Built: dist\WM1Recovery.exe
pause
