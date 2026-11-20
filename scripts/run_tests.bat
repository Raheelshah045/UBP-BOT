@echo off
title UBP Bot - Automated Test Runner
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m pytest %*
) else (
    python -m pytest %*
)

echo.
pause
