@echo off
cd /d "%~dp0"
echo Checking the model scorecard (Stage 3b-4): that each reading and each result status has its own look, that the reading for a kind of shift is worked out per result and never averaged,
echo that every label, the unifying statement and the fixed sentences are on the pages, and that the pages need no internet. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.scorecard_check
echo.
pause
