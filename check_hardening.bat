@echo off
cd /d "%~dp0"
echo Trying to break the platform on purpose (Stage 10): bad files, odd folder names, no network, a clean copy of the project, time limits and the documentation.
echo This takes a few minutes. It works in temporary folders; nothing in the project is changed.
".venv\Scripts\python.exe" -B -m checks.hardening_check
echo.
pause
