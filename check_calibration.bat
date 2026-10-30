@echo off
cd /d "%~dp0"
echo Checking calibration (Stage 3b-1): the carry-forward rule, hit rates and verdicts on made-up errors with a known answer, the recalibration guard
echo (a fold's scale factor never uses its own answers), and the calibration reports on the saved Stage 3a answers. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.calibration_check
echo.
pause
