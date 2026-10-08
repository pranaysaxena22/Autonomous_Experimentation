# Cell POC

A Streamlit app.

## Run it

Double-click `run.bat`, or in a terminal in this folder:

    .venv\Scripts\python.exe -m streamlit run app.py

Then open http://localhost:8501 (it usually opens automatically). Stop with Ctrl+C.

## Add a library

    .venv\Scripts\python.exe -m pip install <package>
    .venv\Scripts\python.exe -m pip freeze > requirements.txt

## Rebuild the environment (e.g. on a new machine)

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
