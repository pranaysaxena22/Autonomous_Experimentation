@echo off
rem  run_app.bat            -> a short menu: 1 = the platform run (http://localhost:8510), 2 = the loop connected (http://localhost:8511), 3 = both, each in its own window. Press Enter for 1.
rem  run_app.bat connected  -> the connected loop straight away (so both can be open together; the first time it can take a few minutes).
rem  run_app.bat <setup file> -> the platform run built from that saved setup file, straight away.
rem  Each opens THE UNIFIED APP: one address with a left menu: Overview, Setup, The run, Live run, 3D replay, Physics (MuJoCo), Data and model, Reports, About and limits.
rem  The Setup page is the setup app's ten screens inside this app, and the Live run page starts and stops the live view (a separate program on port 8514 / 8515, this computer only) from the page.
rem  The Physics page shows the run played by an arm in a MuJoCo model of the cell. It is drawn the first time (about two minutes) and kept; a run that has not changed is not drawn again.
rem  Everything is illustrative or synthetic; nothing leaves this computer, and the app can only be opened from this computer.
cd /d "%~dp0"
rem  CELLPOC_PORT chooses another port (the health check uses it); without it the ports are 8510 and 8511.
set "PORT=%CELLPOC_PORT%"
if not "%~1"=="" goto havechoice
if defined CELLPOC_PORT goto havechoice
echo.
echo   Autonomous formulation cell - which one do you want to open?
echo     1  The platform run          (http://localhost:8510)
echo     2  The loop connected        (http://localhost:8511, the first time it can take a few minutes)
echo     3  Both, each in its own window
echo.
set "CHOICE=1"
set /p "CHOICE=  Type 1, 2 or 3 and press Enter (Enter alone = 1): "
if "%CHOICE%"=="2" (
  call "%~f0" connected
  exit /b
)
if "%CHOICE%"=="3" (
  start "Autonomous formulation cell - connected loop (8511)" cmd /c ""%~f0" connected"
)
:havechoice
if not defined PORT (
  set "PORT=8510"
  if /i "%~1"=="connected" set "PORT=8511"
)
netstat -an | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo   The app cannot start: port %PORT% is already in use. It is probably already running in another black window.
  echo   Close that window, or open http://localhost:%PORT% in your browser.
  pause
  exit /b 1
)
if /i "%~1"=="connected" goto connected
echo Building the platform run (a few seconds)...
".venv\Scripts\python.exe" -B -m cellpoc.platform_runner %*
if errorlevel 1 goto failed
set "CELLPOC_RECORD=%~dp0runs\platform"
goto physics

:connected
echo Connecting the loop: data, then models, then the engine, then the cell. The first time this can take a few minutes...
".venv\Scripts\python.exe" -B -m cellpoc.connected %2
if errorlevel 1 goto failed
set "CELLPOC_RECORD=%~dp0runs\connected_run"
goto physics

:failed
echo.
echo The run could not be built. The message above says why. If it is not clear, double-click check_cellsim.bat (or check_connected.bat for the connected loop).
pause
exit /b 1

:physics
rem  The MuJoCo view of this run for the Physics page: about two minutes the first time, a second after that. If it cannot be drawn the app still starts and that page says so.
echo Preparing the MuJoCo view for the Physics page (the first time about two minutes; after that a second)...
".venv\Scripts\python.exe" -B -m cellpoc.physics.view --run "%CELLPOC_RECORD%"
if errorlevel 1 echo   (The MuJoCo view could not be drawn; everything else works. The Physics page will say so.)

:start
echo Starting the app. Your browser should open; if not, go to http://localhost:%PORT%
echo Stop it with Ctrl+C in this window.
rem  --server.address localhost: the app answers THIS computer only. Without it Streamlit listens on every network address and other computers on the network could open it.
rem  --logger.hideWelcomeMessage true keeps Streamlit's own "install skills for AI coding agents" pop-up off the screen (it is Streamlit's, not part of this project, and would show in front of an audience).
rem  The --theme flags give the app its dark Deloitte look (Black page, Dark Gray panels, Deloitte Green); the other dashboards keep the light theme from .streamlit\config.toml.
".venv\Scripts\python.exe" -m streamlit run unified_app.py --server.port %PORT% --server.address localhost --logger.hideWelcomeMessage true --theme.base dark --theme.backgroundColor "#000000" --theme.secondaryBackgroundColor "#282728" --theme.textColor "#FFFFFF" --theme.primaryColor "#86BC25" --theme.linkColor "#00A3E0" --theme.borderColor "#555555" --theme.dataframeBorderColor "#555555" --theme.dataframeHeaderBackgroundColor "#282728"
