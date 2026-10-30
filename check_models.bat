@echo off
cd /d "%~dp0"
echo Checking the modelling preparation (Stage 3a): every message has a test, the five test tables are prepared with row counts an independent
echo recount agrees with, a result hiding among the inputs is blocked, and the grouped splitters never leak (no random rows, no group on both
echo sides, every test date later than every training date). Nothing is changed except temporary files that are deleted again.
".venv\Scripts\python.exe" -B -m checks.models_check
echo.
echo The list of every message and its test is in docs\modelling_messages.md
echo To see exactly how each table is divided into training and test rows, double-click make_fold_maps.bat
pause
