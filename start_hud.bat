@echo off
setlocal
REM ULTRON safe HUD server: serves only the app pages and generated outputs.
title ULTRON - HUD Launcher
cd /d "%~dp0"

where python >nul 2>nul || (
  echo [ULTRON] Python was not found. Install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)
if not exist "ultron_hud_server.py" (
  echo [ULTRON] ultron_hud_server.py is missing from this folder.
  pause
  exit /b 1
)
if not exist "ultron.html" (
  echo [ULTRON] ultron.html is missing. Extract the complete project ZIP first.
  pause
  exit /b 1
)

start "ULTRON HUD Server" /min python "%~dp0ultron_hud_server.py"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000/ultron.html"
echo.
echo [ULTRON] HUD opened. Use the CREATIVE STUDIO button on the HUD to open Studio separately.
echo [ULTRON] Keep the minimized HUD Server window running.
echo.
pause
