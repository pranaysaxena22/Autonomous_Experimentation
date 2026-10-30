@echo off
cd /d "%~dp0"
echo Checking the configurable cell simulator: that with no faults it is the proof of concept's own run, that faults come from the setup and cost what the executor says,
echo and that changing a timing or a fault moves the trial count exactly as a separate recount predicts. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.cellsim_check
echo.
pause
