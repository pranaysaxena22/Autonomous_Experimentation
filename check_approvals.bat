@echo off
cd /d "%~dp0"
echo Checking high-risk findings: that a wrong vial can be marked high risk, that the cell then stops until a person accepts or rejects it (reject skips the batch and the cell moves on by itself, accept goes on and is logged),
echo that the clock stands still while it waits, that the old jams on trials 8 and 19 behave as they did, and that the page shows the card (it drives Chrome invisibly).
echo This takes a few minutes. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.approvals_check
echo.
pause
