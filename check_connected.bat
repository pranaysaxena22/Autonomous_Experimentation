@echo off
cd /d "%~dp0"
echo Checking the connected loop: that the engine really chooses the recipes from the data file and what Stage 3 concluded, and that everything else is unchanged.
echo This runs a few connected simulations (a few minutes). Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.connected_check
echo.
pause
