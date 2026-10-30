@echo off
rem  run.bat            -> a small menu: 1 Results dashboard, 2 Setup app, 3 Both (each in its own window)
rem  run.bat dashboard  -> starts the results dashboard directly (what run.bat used to do)
rem  run.bat setup      -> starts the setup app directly
rem  Works from any folder, including folders with spaces in the name.
cd /d "%~dp0"
set "MODE=%~1"
if /i "%MODE%"=="dashboard" goto dashboard
if /i "%MODE%"=="setup" goto setup
if not "%MODE%"=="" goto unknown

:menu
echo.
echo   What would you like to open?
echo.
echo     1   Results dashboard    (opens at http://localhost:8501)
echo     2   Setup app            (opens at http://localhost:8502)
echo     3   Both, each in its own window
echo.
set "CHOICE="
set /p "CHOICE=  Type 1, 2 or 3 and press Enter: "
if "%CHOICE%"=="1" goto open_dashboard
if "%CHOICE%"=="2" goto open_setup
if "%CHOICE%"=="3" goto open_both
echo.
echo   That was not 1, 2 or 3. Close this window and double-click run.bat to try again.
pause
exit /b 1

:open_dashboard
start "Results dashboard" cmd /k call "%~dp0run.bat" dashboard
exit /b 0

:open_setup
start "Setup app" cmd /k call "%~dp0run.bat" setup
exit /b 0

:open_both
start "Results dashboard" cmd /k call "%~dp0run.bat" dashboard
start "Setup app" cmd /k call "%~dp0run.bat" setup
exit /b 0

:unknown
echo.
echo   run.bat does not know "%MODE%". Use:  run.bat   or   run.bat dashboard   or   run.bat setup
pause
exit /b 1

:dashboard
call :check_port 8501 "The results dashboard"
if errorlevel 1 goto port_busy
if not exist "runs\demo\record.json" (
  echo No run record yet - building it first. This takes about two minutes...
  ".venv\Scripts\python.exe" -m cellpoc.runner
)
echo Starting the dashboard. Your browser should open; if not, go to http://localhost:8501
echo Stop it with Ctrl+C in this window.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
exit /b %errorlevel%

:setup
call :check_port 8502 "The setup app"
if errorlevel 1 goto port_busy
echo Starting the setup app. Your browser should open; if not, go to http://localhost:8502
echo Everything stays on this computer (no other computer on the network can open it). Stop it with Ctrl+C in this window.
".venv\Scripts\python.exe" -m streamlit run setup_app.py --server.port 8502 --server.address localhost
exit /b %errorlevel%

:port_busy
pause
exit /b 1

:check_port
rem  %1 = port number, %2 = what wants to start. Returns 1 (after explaining) when something is already using the port.
netstat -an | findstr /R /C:":%~1 .*LISTENING" >nul
if errorlevel 1 exit /b 0
echo.
echo   %~2 cannot start: port %~1 is already in use.
echo.
echo   This usually means it is already running in another black window.
echo   What to do:
echo     1. Look for that other black window and close it (or click it and press Ctrl+C), then run this again.
echo     2. Or just open http://localhost:%~1 in your browser: if the page appears, it is already running and you can use it.
echo     3. If neither helps, another program is using that port: restart the computer, then try again.
echo   Nothing is wrong with your files.
echo.
exit /b 1
