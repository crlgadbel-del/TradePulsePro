@echo off
title Antigravity TradeAI — Starting...
color 0A
cls

echo.
echo  ============================================================
echo   ***   Antigravity TradeAI — Hybrid Expert System   ***
echo  ============================================================
echo.
echo   [*] Initializing launcher...
echo.

:: ── Locate folders ───────────────────────────────────────────────────────────
set "ROOT=%~dp0"
for %%I in ("%ROOT%..") do set "APPROOT=%%~fI"
set "BACKEND=%ROOT%backend"

:: ── Try to find Python (venv first, then system) ─────────────────────────────
set "PYTHON="

if exist "%APPROOT%\.venv\Scripts\python.exe" (
    set "PYTHON=%APPROOT%\.venv\Scripts\python.exe"
    echo   [+] Dashboard virtual environment found: %APPROOT%\.venv
) else if exist "%APPROOT%\venv\Scripts\python.exe" (
    set "PYTHON=%APPROOT%\venv\Scripts\python.exe"
    echo   [+] Dashboard virtual environment found: %APPROOT%\venv
) else if exist "%ROOT%venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%venv\Scripts\python.exe"
    echo   [+] Virtual environment found: %ROOT%venv
) else if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%.venv\Scripts\python.exe"
    echo   [+] Virtual environment found: %ROOT%.venv
) else if exist "%ROOT%env\Scripts\python.exe" (
    set "PYTHON=%ROOT%env\Scripts\python.exe"
    echo   [+] Virtual environment found: %ROOT%env
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        for /f "tokens=*" %%i in ('where python') do (
            if not defined PYTHON set "PYTHON=%%i"
        )
        echo   [+] System Python found: %PYTHON%
    ) else (
        color 0C
        echo   [!] ERROR: Python not found on this system.
        echo       Please install Python 3.10+ from https://python.org
        echo.
        pause
        exit /b 1
    )
)

:: ── Check if dependencies are installed ──────────────────────────────────────
"%PYTHON%" -c "import flask, yfinance, sklearn, fastapi, uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   [*] First run detected — installing dependencies...
    echo       (This only happens once. Please wait.)
    echo.
    if exist "%APPROOT%\requirements.txt" (
        "%PYTHON%" -m pip install -r "%APPROOT%\requirements.txt" --quiet
    ) else (
        "%PYTHON%" -m pip install -r "%ROOT%requirements.txt" --quiet
    )
    if %errorlevel% neq 0 (
        color 0C
        echo   [!] ERROR: Failed to install dependencies.
        echo       Run this manually from the project root: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo   [+] Dependencies installed successfully.
    echo.
)

:: ── All good — launch the server ─────────────────────────────────────────────
cls
echo.
echo  ============================================================
echo   ***   Antigravity TradeAI — Hybrid Expert System   ***
echo  ============================================================
echo.
echo   Status  : RUNNING
echo   Dashboard      : http://localhost:5000
echo   Stock Research : open the Stock Research tab inside the dashboard
echo   If port 5000 is busy, the app will print the next available port.
echo.
echo   Close this window to STOP the server.
echo.
echo  ============================================================
echo.

cd /d "%APPROOT%"
"%PYTHON%" app.py

:: ── If server exits, pause so user sees any error message ────────────────────
echo.
echo   [!] Server stopped.
pause
