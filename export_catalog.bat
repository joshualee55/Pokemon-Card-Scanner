@echo off
REM Makes data\catalog.db.gz - ONLY the card catalogue (no accounts, collections or photos) - for hosting.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
venv\Scripts\python.exe -m app.export_catalog
echo.
echo Next: upload data\catalog.db.gz to a GitHub Release (see HOSTING.md, Part A).
pause
