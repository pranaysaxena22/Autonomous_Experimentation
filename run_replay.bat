@echo off
cd /d "%~dp0"
echo Decision-usefulness replay (Stage 3b-3), on the SYNTHETIC mock data only: would ranking recipes by a model's probability of meeting the targets have chosen better than chance?
echo It reads the saved Stage 3a answers (it never refits a model) and writes reports into runs\modelling\. Start with replay_summary.md.
".venv\Scripts\python.exe" -B tools\run_replay.py
echo.
pause
