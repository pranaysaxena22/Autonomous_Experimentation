@echo off
cd /d "%~dp0"
echo Rules 3 and 4 diagnosis: reads only the stored 4-4R campaigns (seeds 11500 to 11539), runs no campaign, changes nothing in the engine. SYNTHETIC data.
echo It writes runs\rules34\summary.md (not saved in git) and prints it.
".venv\Scripts\python.exe" -B tools\analyse_rules34.py
echo.
pause
