@echo off
cd /d "%~dp0"
python -m pip install -q pyinstaller
python -m PyInstaller --noconfirm --clean pack.spec
if exist dist\WM1Recovery-portable.zip del /f dist\WM1Recovery-portable.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\WM1Recovery' -DestinationPath 'dist\WM1Recovery-portable.zip' -Force"
echo.
echo Portable folder: dist\WM1Recovery\WM1Recovery.exe
echo Zip: dist\WM1Recovery-portable.zip
pause
