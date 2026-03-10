@echo off
setlocal EnableDelayedExpansion
title Cellhub Scanner — Setup and Launch

echo.
echo  ============================================
echo   Cellhub Scanner — First-Time Setup
echo  ============================================
echo.

REM ── Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python was not found.
    echo.
    echo  Please install Python 3.11 or later from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During install, tick "Add Python to PATH"
    echo.
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER% found.

REM ── Create virtual environment if missing ─────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo  Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo  [!] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)

REM ── Activate venv ─────────────────────────────────────────────────────────
call .venv\Scripts\activate.bat

REM ── Install / update dependencies ─────────────────────────────────────────
echo.
echo  Installing dependencies (this may take a minute on first run)...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [!] Dependency installation failed. Check your internet connection.
    pause
    exit /b 1
)
echo  [OK] Dependencies ready.

REM ── Launch the app ────────────────────────────────────────────────────────
echo.
echo  Starting Cellhub Scanner...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo  [!] The application exited with an error.
    echo  Please send this window's contents to your IT administrator.
    pause
)
