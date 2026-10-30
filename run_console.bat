@echo off
rem  run_console.bat -> the operations console in your browser (http://localhost:8504/console): a welcome, a guided tour and three views (Overview, Operator, Lab manager) of the simulated cell at work.
rem  Everything is illustrative: a simulation with made-up values. The page answers this computer only. Close this window to stop it.
cd /d "%~dp0"
".venv\Scripts\python.exe" -B -m cellpoc.live console %*
echo.
pause
