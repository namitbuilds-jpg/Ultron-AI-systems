@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  ULTRON 5.1 - LAPTOP AUTHORITY AGENT
REM  Creates a local venv, installs dependencies, then starts the agent
REM ==========================================================================
title Ultron - Laptop Authority Agent
cd /d "%~dp0"

REM --- Resolve a real python.exe (not the py launcher shim) -----------------
set "REAL_PY="

where py >nul 2>nul && (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "REAL_PY=%%P"
)

if not defined REAL_PY (
    where python >nul 2>nul && (
        for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "REAL_PY=%%P"
    )
)

if not defined REAL_PY (
    echo.
    echo   [!] Python 3.10+ not found.
    echo.
    echo       1. Download Python from https://www.python.org/downloads/
    echo       2. During install, TICK "Add python.exe to PATH"
    echo       3. Close this window and run the batch file again.
    echo.
    pause
    exit /b 1
)

echo.
echo   [*] Using: %REAL_PY%
"%REAL_PY%" --version
echo.

REM --- Drop a broken venv from a previous failed install --------------------
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo   [*] Removing broken virtual environment...
        rmdir /s /q .venv
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo   [*] Creating virtual environment...
    "%REAL_PY%" -m venv .venv
    if errorlevel 1 (
        echo.
        echo   [!] Failed to create virtual environment.
        echo       Delete the .venv folder if it exists, then run again.
        echo.
        pause
        exit /b 1
    )
)

set "VENV_PY=.venv\Scripts\python.exe"

echo   [*] Installing core packages...
"%VENV_PY%" -m pip install --upgrade pip --disable-pip-version-check
"%VENV_PY%" -m pip install --prefer-binary "websockets>=13,<18" "psutil>=6.1,<8" "pillow>=11,<13"
if errorlevel 1 (
    echo.
    echo   [!] Core install failed. Check your internet connection,
    echo       then delete the .venv folder and run this file again.
    echo.
    pause
    exit /b 1
)

echo.
echo   [*] Installing Windows extras (volume, windows, mouse)...
"%VENV_PY%" -m pip install --prefer-binary "pywin32>=311" "comtypes>=1.4.0" "pycaw>=20240210" "pygetwindow>=0.0.9" "pyautogui>=0.9.54"
if errorlevel 1 (
    echo.
    echo   [!] Some Windows extras failed. Chat and basic commands will
    echo       still work. Volume or window control may be limited.
    echo.
)

"%VENV_PY%" -c "import websockets; print('  [*] websockets', websockets.__version__)"
if errorlevel 1 (
    echo   [!] websockets did not import. Delete .venv and run again.
    pause
    exit /b 1
)

echo.
echo   ==========================================================
echo     ULTRON AGENT - ws://127.0.0.1:8765
echo     Ctrl+C to stop
echo   ==========================================================
echo.

"%VENV_PY%" ultron_agent.py

echo.
echo   [!] Agent stopped.
pause
