@echo off
cd /d "%~dp0"
echo Checking the applicability-domain warning (Stage 3b-2): that it warns about far-away recipes, that warned rows have bigger errors when they should, that its threshold uses only training rows
echo and stays steady across folds, and that the reports keep their labels. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.domain_check
echo.
pause
