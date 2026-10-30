@echo off
cd /d "%~dp0"
echo The development comparison (Stage 4-4): 40 paired campaigns of 30 trials on each of four synthetic scenarios, for three strategies. About 20 to 30 minutes.
echo Run make_dev_scenarios.bat first if you have not. Each campaign is saved as it finishes, so you can stop and run this again to carry on.
".venv\Scripts\python.exe" -B tools\run_dev_comparison.py
echo.
pause
