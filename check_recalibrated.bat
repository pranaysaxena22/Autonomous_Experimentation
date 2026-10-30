@echo off
cd /d "%~dp0"
echo Checking the recalibrated response to a stale target (a test arm for the rule-5 proposal): that its evidence classes and correction are exact, that it behaves exactly like the current engine until the watch fires,
echo that its safeguards route decisions as written, and that it still refuses the future and sealed seeds. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.recalibrated_check
echo.
pause
