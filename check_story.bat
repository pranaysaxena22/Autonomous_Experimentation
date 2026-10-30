@echo off
cd /d "%~dp0"
echo Checking the client story: the Results page and the Overview's headline cards, with every number recounted from the raw run record.
echo This takes a few minutes. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.client_story_check
echo.
pause
