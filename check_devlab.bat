@echo off
cd /d "%~dp0"
echo Checking the development lab (Stage 4-2): that it is the mock generator's formula plus friability, a new supplier and a process step, that its histories shift the recipes where they should, and that the
echo engine can never see its truth. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.devlab_check
echo.
pause
