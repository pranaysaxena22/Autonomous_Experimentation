@echo off
rem  make_physics_view.bat              -> draws the MuJoCo view of the platform run (runs\platform) for the app's Physics page.
rem  make_physics_view.bat <run folder> -> the same for another saved run (for example runs\setup_run, made by the Setup page's "Save and run it").
rem  run_app.bat does this for you; use this one for a run you made some other way. A view that is already up to date is not drawn again.
cd /d "%~dp0"
set "RUN=%~1"
if "%RUN%"=="" set "RUN=%~dp0runs\platform"
echo Drawing the MuJoCo view of %RUN% (the first time about two minutes). Illustrative: the layout's generic arm, made-up values.
".venv\Scripts\python.exe" -B -m cellpoc.physics.view --run "%RUN%"
echo.
pause
