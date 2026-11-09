@echo off
title AI Trading Bot - ML Backend Server
cd /d "%~dp0ml-backend"
echo ===================================================
echo   Starting AI Trading Bot ML Backend Server
echo   Host: http://127.0.0.1:8000
echo ===================================================
if not exist "venv\Scripts\python.exe" (
    echo Error: Python virtual environment not found in ml-backend\venv
    pause
    exit /b 1
)
".\venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000
pause
