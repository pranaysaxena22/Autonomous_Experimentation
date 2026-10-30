@echo off
rem  run_platform.bat            -> builds a platform run from the example setup (a few seconds) and opens the dashboard on it at http://localhost:8503:
rem                                 the six usual pages plus "3D replay", "Data and model" and "Reports".
rem  run_platform.bat connected  -> the same with THE LOOP CONNECTED, at http://localhost:8505 (so both can be open together): the experiment table is read and judged,
rem                                 its conclusions become the engine's brief, and the adopted decision engine chooses every recipe from it (about a minute; the first time
rem                                 it may take a few minutes to judge the models). Add a scenario if you like: baseline (default), new_supplier, period_shift or unpredictable_dissolution.
rem  Everything is illustrative or synthetic; nothing leaves this computer, and the dashboard can only be opened from this computer.
rem  To run one of your own saved setups instead, drag its file from the setups folder onto this file.
cd /d "%~dp0"
rem  CELLPOC_PORT chooses another port (the health check uses it); without it the ports are 8503 and 8505.
set "PORT=%CELLPOC_PORT%"
if not defined PORT (
  set "PORT=8503"
  if /i "%~1"=="connected" set "PORT=8505"
)
netstat -an | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo   The platform dashboard cannot start: port %PORT% is already in use. It is probably already running in another black window.
  echo   Close that window, or open http://localhost:%PORT% in your browser.
  pause
  exit /b 1
)
if /i "%~1"=="connected" goto connected
echo Building the platform run (a few seconds)...
".venv\Scripts\python.exe" -B -m cellpoc.platform_runner %*
if errorlevel 1 goto failed
set "CELLPOC_RECORD=%~dp0runs\platform"
goto start

:connected
echo Connecting the loop: data, then models, then the engine, then the cell. The first time this can take a few minutes...
".venv\Scripts\python.exe" -B -m cellpoc.connected %2
if errorlevel 1 goto failed
set "CELLPOC_RECORD=%~dp0runs\connected_run"
goto start

:failed
echo.
echo The run could not be built. The message above says why. If it is not clear, double-click check_cellsim.bat (or check_connected.bat for the connected loop).
pause
exit /b 1

:start
echo Starting the dashboard. Your browser should open; if not, go to http://localhost:%PORT%
echo Look for the three extra pages after "What this shows": "3D replay", "Data and model" and "Reports". Stop it with Ctrl+C in this window.
rem  --server.address localhost: the dashboard answers THIS computer only. Without it Streamlit listens on every network address and other computers on the network could open it.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port %PORT% --server.address localhost
