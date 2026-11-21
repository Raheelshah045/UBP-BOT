@echo off
title UBP Bot - Enterprise Dashboard
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" main.py %*
) else (
    echo [WARN] Isolated virtual environment not found in .venv.
    echo Running with default python executable...
    start "" python main.py %*
)
exit /b 0
