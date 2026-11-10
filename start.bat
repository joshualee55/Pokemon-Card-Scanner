@echo off
REM Starts the app on this computer only. Open http://localhost:8000 in your browser.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo Setup has not been completed. Double-click setup.bat first and wait for "Done!".
  pause
  exit /b 1
)
echo App running at http://localhost:8000  (close this window to stop it)
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
