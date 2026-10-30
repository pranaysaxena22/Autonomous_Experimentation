@echo off
cd /d "%~dp0"
echo Setting up the Autonomous Formulation Cell demo.
echo This only needs to run once. It takes a few minutes.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python is not installed on this computer.
  echo Please install Python from https://www.python.org/downloads/
  echo Make sure to tick "Add Python to PATH" during installation.
  echo Then run this script again.
  pause
  exit /b 1
)

echo Step 1 of 2: Creating the Python environment...
python -m venv .venv
if errorlevel 1 (
  echo ERROR: Could not create the Python environment.
  echo Please check that Python is installed correctly and try again.
  pause
  exit /b 1
)

echo Step 2 of 2: Installing the required packages (this takes a few minutes)...
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo ERROR: Could not install the required packages.
  echo Please check your internet connection and try again.
  pause
  exit /b 1
)

echo.
echo Setup complete. You can now double-click run.bat to open the dashboard.
echo You do not need to run this script again.
pause
