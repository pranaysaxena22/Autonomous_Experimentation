@echo off
cd /d "%~dp0"
echo Checking the data reader (Stage 2): every message has a test, the same table comes out of many file formats,
echo 200 random file damages never crash it or lose a row, and the real public files are read as expected.
echo Nothing is changed except temporary files that are deleted again.
".venv\Scripts\python.exe" -B -m checks.ingest_check
echo.
echo The list of every message and its test is in docs\ingest_messages.md
pause
