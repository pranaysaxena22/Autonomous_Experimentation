@echo off
cd /d "%~dp0"
echo Checking the rules 3/4 diagnosis tool: that its accounting is exactly right on made-up campaigns worked out by hand, that it reads only the stored 4-4R campaigns, and that it reproduces the 4-4R table first.
echo Nothing is run and nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.rules34_check
echo.
pause
