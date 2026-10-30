@echo off
cd /d "%~dp0"
echo Writing a data quality report for each mock data file and, if the real public data files are on this computer, for each of those too.
echo Reading only: nothing is changed except the report files. They go in the folder runs\ingest (not saved in git).
echo.
".venv\Scripts\python.exe" -B tools\make_quality_report.py all
echo.
echo Open the .md files in runs\ingest with any text editor (for example VS Code or Notepad).
echo Each report starts with its data label and a row-accounting block; assumptions are written out in the section after "What needs your attention".
pause
