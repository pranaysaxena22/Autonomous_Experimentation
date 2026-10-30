@echo off
cd /d "%~dp0"
echo Checking the development comparison (Stage 4-4): that scoring is against the truth, that the three strategies face the same lab day, that the statistics and the verdict rule are exact, that the report
echo tells the truth when the governed engine is worse, and that the engine files are locked while the comparison runs. Uses development seeds only. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.comparison_check
echo.
pause
