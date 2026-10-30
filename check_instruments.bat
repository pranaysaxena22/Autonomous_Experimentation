@echo off
cd /d "%~dp0"
echo Checking the instruments: the barcode scanner and balance drivers (against a pretend scanner and balance), the barcode fault through the cell, and that normal runs are unchanged.
echo This takes a few minutes. Nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.instruments_check
echo.
pause
