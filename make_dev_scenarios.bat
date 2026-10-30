@echo off
cd /d "%~dp0"
echo The development lab's four scenarios (Stage 4-2): writes each scenario's history and runs Stage 3 on it, to show what each was designed to show and what Stage 3 concluded.
echo This takes about 10 minutes the first time (the saved answers are reused after that). Everything is synthetic.
".venv\Scripts\python.exe" -B tools\make_dev_scenarios.py
echo.
pause
