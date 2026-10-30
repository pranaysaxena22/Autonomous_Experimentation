@echo off
cd /d "%~dp0"
echo Building a platform run from the example setup (a few seconds), then opening its 3D replay.
echo Everything here is illustrative: a simulated cell, a generic arm, made-up values. Nothing leaves this computer.
".venv\Scripts\python.exe" -B -m cellpoc.platform_runner
if errorlevel 1 goto failed
start "" "runs\platform\replay.html?trial=8"
goto done
:failed
echo Something went wrong. Double-click check_cellsim.bat to see what is failing.
:done
pause
