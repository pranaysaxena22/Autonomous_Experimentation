@echo off
cd /d "%~dp0"
echo Rebuilding the run record the dashboard shows (about two minutes)...
".venv\Scripts\python.exe" -m cellpoc.runner
echo.
echo Done. Start the dashboard with run.bat
pause
