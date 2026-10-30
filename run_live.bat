@echo off
rem  run_live.bat -> starts the LIVE run: the simulated cell runs while you watch it in the browser (3D arm, clock, results, faults),
rem  at http://localhost:8504. Simulated time runs faster than real time; choose the speed on the page. Illustrative; nothing leaves this computer.
rem  run_live.bat connected  -> the same live run with THE LOOP CONNECTED: the adopted decision engine chooses every recipe from the experiment table and
rem  what Stage 3 concluded about it (add a scenario if you like: baseline (default), new_supplier, period_shift, unpredictable_dissolution).
rem  On the page, the Setup list at the top chooses which setup runs: the three illustrative examples, your saved setups, or the loop connected.
rem  To start with one of your saved setups, drag its file from the setups folder onto this file.
cd /d "%~dp0"
netstat -an | findstr /R /C:":8504 .*LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo   The live page cannot start: port 8504 is already in use. It is probably already running in another black window.
  echo   Close that window, or open http://localhost:8504 in your browser.
  pause
  exit /b 1
)
echo Starting the live run. Your browser opens at http://localhost:8504 : press "Start the run". Keep this window open; close it to stop.
".venv\Scripts\python.exe" -B -m cellpoc.live %*
if errorlevel 1 pause
