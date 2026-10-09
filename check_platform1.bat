@echo off
cd /d "%~dp0"
echo Checking the setup rules (Stage 1, shared logic): every rule has a test, 200 random breakages never crash it,
echo old and new setup versions are handled, saved files carry no personal names. Nothing is changed except
echo temporary files that are deleted again.
".venv\Scripts\python.exe" -B -m checks.platform1_check
echo.
echo The list of every message and its test is in docs\setup_messages.md
pause
