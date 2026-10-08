@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m checks.stage3_check
echo.
echo Files to look at:
echo   runs\stage3\comparison_summary.txt   (the comparison in words and numbers)
echo   runs\stage3\comparison.html          (chart - double-click to open in your browser)
echo   runs\stage3\campaigns.csv            (every campaign, open in Excel)
echo   runs\stage3\demo_event_log.csv       (the adaptive run, with the "why" behind every decision)
pause
