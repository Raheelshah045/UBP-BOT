@echo off
title UBP Bot - Pre-flight Environment Diagnostics
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py --diagnostics
) else (
    python main.py --diagnostics
)

echo.
pause
