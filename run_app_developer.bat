@echo off
rem  run_app_developer.bat -> the same app as run_app.bat, in its DEVELOPER view: every page (the finished run moment by moment, the 3D and physics views, the data and models) and the technical detail.
rem  run_app.bat opens the CLIENT view: the pages and wording meant for the people the demo is for.
cd /d "%~dp0"
set "CELLPOC_DEVELOPER=1"
call "%~dp0run_app.bat" %*
