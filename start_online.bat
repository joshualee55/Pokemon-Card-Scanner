@echo off
REM Starts the app AND makes it reachable from your phone anywhere. Everyone signs in with their own account.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo Setup has not been completed. Double-click setup.bat first and wait for "Done!".
  pause
  exit /b 1
)
echo Friends need an INVITE CODE to create an account. Make one up (letters and numbers only).
set /p SIGNUP_CODE=Invite code: 
start "Card Tracker server - keep open" cmd /k "venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo Starting the app... please wait.
timeout /t 10 >nul
echo.
echo Look below for a line like  https://something-random.trycloudflare.com  and open it on your phone.
echo Share that address + your invite code with friends (max 10 accounts). Keep BOTH windows open.
cloudflared tunnel --url http://127.0.0.1:8000
pause
