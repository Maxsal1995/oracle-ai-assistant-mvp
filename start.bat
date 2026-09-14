@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Local environment is missing. Starting setup...
  call setup.bat
  if errorlevel 1 exit /b 1
)

set "PYTHONUTF8=1"
echo.
echo ==========================================
echo   Oracle AI Assistant
echo   http://127.0.0.1:8000
echo ==========================================
echo.
echo This application does not connect to Oracle.
echo Press Ctrl+C to stop it.
echo.

start "" /B powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
