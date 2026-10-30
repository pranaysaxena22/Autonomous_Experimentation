@echo off
cd /d "%~dp0"
echo Checking the dashboard with the platform wired in (Stage 8): the platform run's results, 3D replay and data page, and that the proof-of-concept run looks exactly as before.
echo This runs a platform simulation and the dashboard test harness (a few minutes). Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.stage8_check
echo.
pause
