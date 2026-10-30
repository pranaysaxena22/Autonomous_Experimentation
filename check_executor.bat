@echo off
cd /d "%~dp0"
echo Checking the cell executor: that it reproduces the hand-authored executed timeline, that a fault costs exactly what its recovery actions cost, that a failed retry skips the candidate,
echo and that it refuses what it cannot run in plain words. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.executor_check
echo.
pause
