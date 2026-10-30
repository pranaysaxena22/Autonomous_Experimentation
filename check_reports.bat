@echo off
cd /d "%~dp0"
echo Checking the report and export files (Stage 9): that they say exactly what the run record says, are labelled illustrative or synthetic, and use the Deloitte look.
echo This writes the files into a temporary folder (a minute or two; it opens a browser invisibly to make the PDF). Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.reports_check
echo.
pause
