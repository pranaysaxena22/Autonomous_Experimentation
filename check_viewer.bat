@echo off
cd /d "%~dp0"
echo Checking the 3D replay viewer: that it is one self-contained file that replays exactly the executed timelines it was given, with no logic of its own,
echo that it works with no internet, and that a fault shows. This opens Google Chrome invisibly (a minute or two). Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.viewer_check
echo.
pause
