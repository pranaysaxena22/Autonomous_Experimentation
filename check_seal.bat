@echo off
cd /d "%~dp0"
echo Checking the sealed acceptance lab: that its files have not changed by one byte, that nothing outside its folder uses it, and that the ledger shows it was never opened. It reads files only and never runs the lab.
".venv\Scripts\python.exe" -B -m checks.seal_check
echo.
pause
