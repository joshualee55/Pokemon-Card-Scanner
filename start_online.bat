@echo off
REM Starts the app AND makes it reachable from your phone anywhere (password protected).
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo Setup has not been completed. Double-click setup.bat first and wait for "Done!".
  pause
  exit /b 1
)
set /p APP_PASSWORD=Choose a password (letters and numbers only): 
start "Card Tracker server - keep open" cmd /k "venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo Starting the app... please wait.
timeout /t 10 >nul
echo.
echo Look below for a line like  https://something-random.trycloudflare.com  and open it on your phone.
echo Username: anything.  Password: what you just chose.
cloudflared tunnel --url http://127.0.0.1:8000
pause
