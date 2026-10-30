@echo off
cd /d "%~dp0"
echo Checking the physics part: the MuJoCo model of the cell built from the layout, gravity, repeatability, and the reach test asked of MuJoCo.
echo This takes a minute. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.physics_check
echo.
pause
