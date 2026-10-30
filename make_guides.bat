@echo off
cd /d "%~dp0"
echo Writing the guides as branded pages and PDFs: the demo script, the system explained in plain language, the work report and the design for the sealed acceptance run.
echo They go in the folder runs\guides (not saved in git). Open the .html files in any browser, or the .pdf files. Nothing leaves this computer.
".venv\Scripts\python.exe" -B tools\make_guides.py --pdf
echo.
start "" "runs\guides"
pause
