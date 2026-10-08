@echo off
cd /d "%~dp0"
echo This rebuilds the run record and drives the dashboard through every page. It takes a few minutes.
".venv\Scripts\python.exe" -m checks.stage5_check
echo.
echo Then start the dashboard itself with run.bat
pause
