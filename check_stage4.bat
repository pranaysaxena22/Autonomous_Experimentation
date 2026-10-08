@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m checks.stage4_check
echo.
echo Files to look at:
echo   runs\stage4\closed_loop_summary.txt   (the run in words: attempts, alerts, what happened overnight)
echo   runs\stage4\timeline.html             (chart - double-click; works with no internet)
echo   runs\stage4\trials.csv                (every trial: recipe, status, result, why - open in Excel)
echo   runs\stage4\event_log.csv             (the full event log - open in Excel)
echo   runs\stage4\alerts.csv                (the alerts)
pause
