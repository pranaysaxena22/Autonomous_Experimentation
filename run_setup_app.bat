@echo off
cd /d "%~dp0"
echo Starting the setup app. Your browser should open; if not, go to http://localhost:8502
echo Everything stays on this computer. Stop it with Ctrl+C in this window.
".venv\Scripts\python.exe" -m streamlit run setup_app.py --server.port 8502
