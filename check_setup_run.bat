@echo off
cd /d "%~dp0"
echo Checking "Run this setup" in the setup app: that the setup you fill in really drives a simulated run, and that the button behaves.
echo This presses the button a few times in a test copy of the app (a minute or two). The test setup it saves is removed afterwards.
".venv\Scripts\python.exe" -B -m checks.setup_run_check
echo.
pause
