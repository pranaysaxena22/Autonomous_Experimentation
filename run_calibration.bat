@echo off
cd /d "%~dp0"
echo Calibration (Stage 3b-1): is the uncertainty each model states honest? Reads the saved Stage 3a answers and writes reports into runs\modelling\.
echo If the saved answers are missing it first runs the full comparison (about 10 minutes). Nothing else is changed.
".venv\Scripts\python.exe" -B tools\run_calibration.py
pause
