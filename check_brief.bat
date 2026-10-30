@echo off
cd /d "%~dp0"
echo Checking the decision engine's brief (Stage 4-1): that it matches what Stage 3 concluded, that only a carried result is ever usable, that the range factor is a median never below 1,
echo and that the engine can only reach the model classes, one direction only. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.brief_check
echo.
pause
