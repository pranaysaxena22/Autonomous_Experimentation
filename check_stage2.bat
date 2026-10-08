@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m checks.stage2_check
echo.
echo Files to look at:
echo   runs\stage2\timeline.html    (chart - double-click to open in your browser)
echo   runs\stage2\event_log.csv    (open in Excel)
echo   runs\stage2\trials.csv       (open in Excel)
pause
