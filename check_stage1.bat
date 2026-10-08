@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m checks.stage1_check
echo.
echo Files to look at:
echo   docs\scenario.md                   (the scenario page)
echo   runs\stage1\lab_report.html        (charts - double-click to open in your browser)
echo   runs\stage1\lab_measurements.csv   (open in Excel)
pause
