@echo off
setlocal EnableDelayedExpansion
title Cellhub Scanner — Build Windows EXE

echo.
echo  ============================================
echo   Cellhub Scanner — Build Executable
echo  ============================================
echo.

REM ── Activate venv ─────────────────────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo  [!] Virtual environment not found. Run install_and_run.bat first.
    pause
    exit /b 1
)

REM ── Install PyInstaller if missing ────────────────────────────────────────
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo  Installing PyInstaller...
    pip install pyinstaller==6.7.0 --quiet
)

REM ── Clean previous build ──────────────────────────────────────────────────
if exist "dist\CellhubScanner" rmdir /s /q "dist\CellhubScanner"
if exist "dist\CellhubScanner.exe" del /q "dist\CellhubScanner.exe"
if exist "build" rmdir /s /q "build"

REM ── Run PyInstaller ───────────────────────────────────────────────────────
echo.
echo  Building executable (this takes 2-5 minutes)...
echo.
pyinstaller cellhub_scanner.spec --noconfirm

if errorlevel 1 (
    echo.
    echo  [!] Build failed. See output above for details.
    pause
    exit /b 1
)

REM ── Verify output ─────────────────────────────────────────────────────────
if exist "dist\CellhubScanner.exe" (
    echo.
    echo  ============================================
    echo   Build complete!
    echo   Output: dist\CellhubScanner.exe
    echo  ============================================
    echo.
    echo  You can now distribute dist\CellhubScanner.exe
    echo  No Python installation required on target machine.
    echo.
) else (
    echo  [!] Build seemed to succeed but EXE not found in dist\.
)

pause
