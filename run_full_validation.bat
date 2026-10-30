@echo off
cd /d "%~dp0"
echo FULL comparison (Stage 3a-4): fitting every model on every fold of every test table at full effort, then writing a report for each table and a summary into runs\modelling\.
echo This takes a while (about 10 to 30 minutes). It saves each fold as it finishes, so if you stop it, running this file again carries on where it stopped.
echo Nothing else is changed.
".venv\Scripts\python.exe" -B tools\run_validation.py --mode full
pause
