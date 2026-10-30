@echo off
cd /d "%~dp0"
echo Writing the report files (a branded report page and PDF, an Excel workbook and CSV tables) for the latest run.
echo It uses the platform run if there is one (runs\platform), otherwise the proof-of-concept demo run (runs\demo). Everything is labelled illustrative or synthetic.
echo Nothing leaves this computer. The files go in a folder called "reports" next to the run record.
".venv\Scripts\python.exe" -B -m cellpoc.reports %*
echo.
pause
