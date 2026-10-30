@echo off
cd /d "%~dp0"
echo Checking the unified app (Stage A): the menu and every page, that the pages say what the dashboard says, that the illustrative sentence shows once per page, that the Overview's numbers match a separate recount of the run record (with planted wrong numbers to prove the comparison can fail), and that run_app.bat really answers THIS computer only.
echo This takes a few minutes (it starts the real app twice on spare ports and stops it again). Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.app_check
echo.
pause
