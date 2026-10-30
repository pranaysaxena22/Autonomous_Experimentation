@echo off
cd /d "%~dp0"
echo Checking the operations console: it is served to this computer only, says what the rest of the app says, has no developer wording, and in real Chrome draws its three views, the camera verdicts, the welcome and the tour.
echo This takes a few minutes. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.console_check
echo.
pause
