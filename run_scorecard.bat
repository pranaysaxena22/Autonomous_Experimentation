@echo off
cd /d "%~dp0"
echo Model scorecard (Stage 3b-4): one web page per table, from the saved Stage 3a answers. Nothing is refitted and nothing needs the internet.
echo If the saved answers are missing it first runs the full comparison (about 10 minutes).
".venv\Scripts\python.exe" -B tools\run_scorecard.py
if exist "runs\scorecard\index.html" start "" "runs\scorecard\index.html"
echo.
pause
