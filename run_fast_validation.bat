@echo off
cd /d "%~dp0"
echo Fast mode: fitting every model on every fold of every test table and writing a model-comparison report for each into runs\modelling\.
echo This takes several minutes. Fast mode does less work than the full run, so the numbers are a first look. Nothing else is changed.
".venv\Scripts\python.exe" -B tools\run_validation.py --mode fast
pause
