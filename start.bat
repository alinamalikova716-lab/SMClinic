@echo off
chcp 65001 >nul
title SM-Clinic - coordinator
cd /d "%~dp0"

echo.
echo   SM-Clinic / coordinator of patient routing
echo   ------------------------------------------
echo   Open in browser:  http://127.0.0.1:8000
echo   To stop:          press Ctrl+C
echo.

python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
pause
