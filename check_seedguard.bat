@echo off
cd /d "%~dp0"
echo Checking the seed guard: that the code itself refuses any sealed acceptance seed (the live block 7,000,101 to 7,000,140 or the retired block 7,000,001 to 7,000,040) at every place a development seed
echo can enter, that ordinary development seeds still work, and that the guard matches the seal. It never runs the sealed lab. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.seedguard_check
echo.
pause
