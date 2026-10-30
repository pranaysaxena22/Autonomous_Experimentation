@echo off
cd /d "%~dp0"
echo Running every health check in order: the five proof-of-concept checks, the format check, the platform check and the data-reader check.
echo It changes nothing and ends with one summary table. It takes several minutes.
echo.
".venv\Scripts\python.exe" -B -m checks.check_all
echo.
pause
