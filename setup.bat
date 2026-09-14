@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   Oracle AI Assistant - Windows setup
echo ==========================================
echo.

set "PYTHON_CMD="
where py >nul 2>&1
if %errorlevel%==0 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>&1
  if %errorlevel%==0 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo [ERROR] Python 3.11 or newer was not found.
  echo Install Python from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating the local Python environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :failed
) else (
  echo [1/4] Existing Python environment found.
)

call ".venv\Scripts\activate.bat"
echo [2/4] Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/4] Installing application dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed

if not exist ".env" copy /Y ".env.example" ".env" >nul
if not exist "data" mkdir "data"

echo [4/4] Initialising the local database...
python -c "from app.database import init_db; init_db(); print('Local database ready.')"
if errorlevel 1 goto :failed

echo.
echo Setup completed successfully.
echo Make sure Ollama is running and at least one model is installed.
echo Example: ollama pull qwen3:8b
echo Then run: start.bat
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] Setup did not complete. Review the message above.
pause
exit /b 1
