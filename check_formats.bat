@echo off
cd /d "%~dp0"
echo Checking the example file formats, the schemas and the naming rules. Nothing is changed or written.
".venv\Scripts\python.exe" -m checks.formats_check
echo.
echo The files being checked are in docs\platform_formats\  (rules: docs\naming.md)
pause
