@echo off
title AI Trading Bot - ML Backend Server
setlocal enabledelayedexpansion

echo ===================================================
echo   Starting AI Trading Bot ML Backend Server
echo ===================================================

set "PROJ_DIR="

if exist "%~dp0venv\Scripts\python.exe" (
    set "PROJ_DIR=%~dp0"
)
if not defined PROJ_DIR (
    if exist "%~dp0ml-backend\venv\Scripts\python.exe" (
        set "PROJ_DIR=%~dp0ml-backend"
    )
)
if not defined PROJ_DIR (
    if exist "C:\Users\ASUS\OneDrive\Documents\AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
        set "PROJ_DIR=C:\Users\ASUS\OneDrive\Documents\AI-Trading-Bot\ml-backend"
    )
)
if not defined PROJ_DIR (
    if exist "%USERPROFILE%\OneDrive\Documents\AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
        set "PROJ_DIR=%USERPROFILE%\OneDrive\Documents\AI-Trading-Bot\ml-backend"
    )
)
if not defined PROJ_DIR (
    if exist "%USERPROFILE%\Documents\AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
        set "PROJ_DIR=%USERPROFILE%\Documents\AI-Trading-Bot\ml-backend"
    )
)

if not defined PROJ_DIR (
    echo [ERROR] Could not find python virtual environment.
    echo Please make sure AI-Trading-Bot is in your Documents folder.
    pause
    exit /b 1
)

cd /d "!PROJ_DIR!"
echo [*] Working Directory: !PROJ_DIR!
echo [*] ML Server: http://localhost:8000
echo [*] Dashboard: http://localhost:8000/dashboard
echo ===================================================
echo [*] Launching server... Opening dashboard in browser...
echo ===================================================

set PYTHONUNBUFFERED=1
".\venv\Scripts\python.exe" run.py
if errorlevel 1 (
    echo.
    echo [ERROR] Server exited with code %errorlevel%.
    pause
)
pause
