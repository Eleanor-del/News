@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo    News Hotspots v4.0 - Build
echo ==========================================
python build.py %*
echo.
pause
