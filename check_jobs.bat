@echo off
cd /d "%~dp0"
echo Checking the job queue: that jobs for several drugs start one at a time or run one after another by themselves, that a job that runs out of an ingredient is blocked with the reason and the queue moves on,
echo that a restock lets it be started again, that the real simulation stops a job cleanly between trials, and that the Jobs view shows the queue and the shelf (it drives Chrome invisibly).
echo This takes a few minutes. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.jobs_check
echo.
pause
