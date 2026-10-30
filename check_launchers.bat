@echo off
cd /d "%~dp0"
echo Checking the launchers that start a dashboard: that run_platform.bat really leaves a dashboard that answers THIS computer only (it runs the launcher for real on another port and looks at the addresses the computer is listening on).
echo This takes about a minute. It stops everything it starts. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.launchers_check
echo.
pause
