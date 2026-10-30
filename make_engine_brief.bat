@echo off
cd /d "%~dp0"
echo The decision engine's brief (Stage 4-1): what Stage 3 concluded about each result, one page per table, from the saved Stage 3 answers. Nothing is refitted and no lab is touched.
echo If the saved answers are missing it first runs the full comparison (about 10 minutes).
".venv\Scripts\python.exe" -B tools\make_engine_brief.py
echo.
pause
