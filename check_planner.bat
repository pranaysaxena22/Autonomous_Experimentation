@echo off
cd /d "%~dp0"
echo Checking the motion planner: that every plan it generates obeys every rule (steps add up to the setup, every wait has a reason, friability only when needed, picks match places),
echo that it refuses what it cannot plan in plain words, and that it imports no other part of the platform. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.planner_check
echo.
pause
