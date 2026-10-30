@echo off
cd /d "%~dp0"
echo Checking the vision: drawn bench scenes with a known answer (levels, colours, positions for the arm, reach, odd pictures) and the Vision page.
echo This takes a few minutes. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.vision_check
echo.
pause
