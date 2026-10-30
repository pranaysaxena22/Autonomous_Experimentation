@echo off
cd /d "%~dp0"
echo Writing a fold map for each test table: exactly how it is divided into training and test rows (never random rows).
echo The maps go to runs\modelling\ ; nothing else is changed.
".venv\Scripts\python.exe" -B tools\make_fold_maps.py
pause
