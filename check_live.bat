@echo off
cd /d "%~dp0"
echo Checking the live run: that it is exactly the same simulation as a normal run, only paced; that nothing appears before its moment; and that its page shows it as it happens (it drives Chrome invisibly).
echo This takes a minute or two. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.live_check
echo.
pause
