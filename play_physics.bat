@echo off
rem  play_physics.bat            -> opens MuJoCo's viewer and plays the first trial with a fault (a binder jam) of the run run_app.bat built (runs\platform), with the arm carrying the vials and bottles.
rem  play_physics.bat 12         -> plays trial 12 instead.
rem  play_physics.bat 8 gif      -> writes runs\physics\trial_8.gif (an animated picture you can send or put in a slide) instead of opening the viewer.
cd /d "%~dp0"
if not exist "runs\platform\layout.json" (
  echo No run to play yet. Double-click run_app.bat once to build one, close it, then try again.
  pause
  exit /b 1
)
if not exist "runs\physics" mkdir "runs\physics"
echo Illustrative: the layout's generic arm and made-up values. Nothing is changed in the run.
if /i "%~2"=="gif" goto gif
if "%~1"=="" (
  ".venv\Scripts\python.exe" -B -m cellpoc.physics.play
) else (
  ".venv\Scripts\python.exe" -B -m cellpoc.physics.play --trial %1
)
goto end
:gif
echo Making the animated picture (about half a minute)...
".venv\Scripts\python.exe" -B -m cellpoc.physics.play --trial %1 --gif "runs\physics\trial_%1.gif"
:end
echo.
pause
