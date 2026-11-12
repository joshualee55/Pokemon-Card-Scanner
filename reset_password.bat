@echo off
REM For when someone forgets their password. Run this, type their username, then a new password for them.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
echo Current accounts:
venv\Scripts\python.exe -m app.admin list
echo.
set /p WHO=Username to reset: 
venv\Scripts\python.exe -m app.admin reset %WHO%
echo.
echo Tell them the new password. They can sign in right away (they were signed out everywhere).
pause
