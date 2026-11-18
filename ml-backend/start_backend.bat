@echo off
echo ===================================================
echo   AI Trading Signal Bot - ML Backend Launcher
echo ===================================================
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [1/4] Creating Python virtual environment...
    python -m venv venv
)

echo [2/4] Ensuring dependencies are installed...
.\venv\Scripts\python.exe -m pip install --prefer-binary -r requirements.txt

if not exist "models\ensemble_model.pkl" (
    echo [3/4] Bootstrapping 35-day learning memory and training initial ML models...
    .\venv\Scripts\python.exe scripts/training/bootstrap_initial_models.py
)

echo [4/4] Starting FastAPI ML Server on http://localhost:8000 ...
.\venv\Scripts\python.exe run.py
pause
