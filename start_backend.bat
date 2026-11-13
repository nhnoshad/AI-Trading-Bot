@echo off
title AI Trading Bot - ML Backend Server
cd /d "%~dp0ml-backend"
echo ===================================================
echo   Starting AI Trading Bot ML Backend Server
echo   Host: http://localhost:8000
echo   Dashboard: http://localhost:3000
echo ===================================================
if not exist "venv\Scripts\python.exe" (
    echo Error: Python virtual environment not found in ml-backend\venv
    pause
    exit /b 1
)
".\venv\Scripts\python.exe" run.py
pause
