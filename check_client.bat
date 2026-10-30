@echo off
cd /d "%~dp0"
echo Checking the client view of the app: the pages a client sees, that no developer wording is on them, and that the illustrative labelling is still there.
echo This takes a minute or two. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.client_view_check
echo.
pause
