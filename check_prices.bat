@echo off
REM Shows how many of your cards are matched to TCGplayer prices (and which sets are not).
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
venv\Scripts\python.exe -m app.mapping
echo.
echo Copy everything above and send it to me if the numbers look low.
pause
