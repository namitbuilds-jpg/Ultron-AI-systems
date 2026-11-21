@echo off
cd /d "%~dp0"
if not exist ".env" (
  echo [ULTRON] Missing .env file.
  echo Copy .env.example to .env and add your own keys.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if exist requirements-media.txt pip install -r requirements-media.txt
python ultron_media_service.py
pause
