@echo off
setlocal enabledelayedexpansion
title UBP Bot - Windows Installation and Setup
echo ===============================================================================
echo   UBP Bot - Enterprise Windows Automated Setup (Phase 1)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

:: 1. Verify Python Installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in system PATH.
    echo Please install Python 3.10.x 64-bit and ensure 'Add Python to PATH' is selected.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [1/6] Detected Python runtime: %PY_VER%

:: 2. Initialize Virtual Environment
if not exist ".venv" (
    echo [2/6] Creating isolated virtual environment in .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [2/6] Existing virtual environment found in .venv.
)

:: 3. Activate Virtual Environment
call .\.venv\Scripts\activate.bat
echo [3/6] Virtual environment activated.

:: 4. Upgrade pip and install pinned dependencies
echo [4/6] Installing dependencies from requirements.txt ...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

:: 5. Install Playwright Chromium Browser
echo [5/6] Checking/Installing Playwright Chromium browser ...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [WARN] Playwright browser installation encountered a warning.
    echo If offline or using IT-managed Edge, set "channel": "msedge" in config/config.json.
)

:: 6. Workspace Structure and Configuration Template
echo [6/6] Initializing runtime directories ...
for %%d in (input output logs checkpoints processing completed failed config) do (
    if not exist "%%d" mkdir "%%d"
)

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [INFO] Created .env template from .env.example. Please populate with required URLs/credentials.
    )
)

echo.
echo ===============================================================================
echo   Setup Completed Successfully!
echo   To launch the application: scripts\launch_desktop.bat
echo   To verify diagnostics:     scripts\verify_environment.bat
echo ===============================================================================
echo.
pause
