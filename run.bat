@echo off
cd /d "%~dp0"
if not exist "runs\demo\record.json" (
  echo No run record yet - building it first. This takes about two minutes...
  ".venv\Scripts\python.exe" -m cellpoc.runner
)
echo Starting the dashboard. Your browser should open; if not, go to http://localhost:8501
echo Stop it with Ctrl+C in this window.
".venv\Scripts\python.exe" -m streamlit run app.py
