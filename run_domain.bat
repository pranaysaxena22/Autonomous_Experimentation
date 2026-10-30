@echo off
cd /d "%~dp0"
echo Applicability-domain warning (Stage 3b-2): is a recipe far from the data the model learned from? Reads the saved Stage 3a answers and writes reports into runs\modelling\.
echo If the saved answers are missing it first runs the full comparison (about 10 minutes). Nothing else is changed.
".venv\Scripts\python.exe" -B tools\run_domain.py
pause
