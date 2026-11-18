@echo off
title AI Trading Bot - ML Backend Server
setlocal enabledelayedexpansion

echo ===================================================
echo   AI Trading Bot - ML Backend Server Launcher
echo ===================================================

:: 1. Search for ml-backend in multiple possible locations
set "TARGET_DIR="

if exist "%~dp0ml-backend\venv\Scripts\python.exe" (
    set "TARGET_DIR=%~dp0ml-backend"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "TARGET_DIR=%~dp0"
) else if exist "%~dp0AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
    set "TARGET_DIR=%~dp0AI-Trading-Bot\ml-backend"
) else if exist "C:\Users\ASUS\OneDrive\Documents\AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
    set "TARGET_DIR=C:\Users\ASUS\OneDrive\Documents\AI-Trading-Bot\ml-backend"
) else if exist "%USERPROFILE%\OneDrive\Documents\AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
    set "TARGET_DIR=%USERPROFILE%\OneDrive\Documents\AI-Trading-Bot\ml-backend"
) else if exist "%USERPROFILE%\Documents\AI-Trading-Bot\ml-backend\venv\Scripts\python.exe" (
    set "TARGET_DIR=%USERPROFILE%\Documents\AI-Trading-Bot\ml-backend"
)

if not defined TARGET_DIR (
    echo [ERROR] Could not locate AI-Trading-Bot\ml-backend directory!
    echo Please make sure the AI-Trading-Bot repository exists in your Documents folder.
    pause
    exit /b 1
)

echo [*] Target Directory: !TARGET_DIR!
cd /d "!TARGET_DIR!"

echo [*] Python Venv Found: !TARGET_DIR!\venv\Scripts\python.exe
echo [*] ML Server: http://localhost:8000
echo [*] Dashboard: http://localhost:8000/dashboard (and http://localhost:3000)
echo ===================================================
echo [*] Starting server... Please wait a few seconds for ML models to load...
echo ===================================================

set PYTHONUNBUFFERED=1
".\venv\Scripts\python.exe" run.py

pause
