@echo off
REM Re-tests the card matcher on YOUR saved scan photos (the ones where you confirmed the right card).
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
venv\Scripts\python.exe -m app.eval_scans
echo.
venv\Scripts\python.exe -m app.eval_scans --no-rectify
echo.
echo Copy everything above and send it to me.
pause
