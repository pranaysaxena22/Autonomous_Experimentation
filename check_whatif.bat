@echo off
cd /d "%~dp0"
echo Checking 'try a recipe yourself': that a recipe typed on the Try it view is refused in plain words when it is not five numbers within the allowed ranges, that the virtual lab measures it and the reading is exactly what the lab gives,
echo that the engine says what it would try next and why, that the control needs the page's secret, that trying a recipe does not touch the run or the queue, and that the page shows the form (it drives Chrome invisibly).
echo This takes a minute or two. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.whatif_check
echo.
pause
