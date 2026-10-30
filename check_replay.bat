@echo off
cd /d "%~dp0"
echo Checking the decision-usefulness replay (Stage 3b-3): that a perfect predictor scores perfectly and a useless one scores like chance, that a window which could see the future is refused,
echo that nothing measured in a window reaches the ranking, that it only ever runs on the synthetic mocks, and that the reports keep their labels. Nothing is changed.
".venv\Scripts\python.exe" -B -m checks.replay_check
echo.
pause
