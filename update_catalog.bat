@echo off
REM Downloads more cards / refreshes prices. Safe to stop and re-run any time (it picks up where it left off).
cd /d "%~dp0"
call venv\Scripts\activate.bat
:again
python -m app.ingest
if errorlevel 1 (echo The card website is being flaky, retrying in 20 seconds... & timeout /t 20 >nul & goto again)
echo Catalogue complete!
pause
