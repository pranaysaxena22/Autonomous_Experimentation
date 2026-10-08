# Cell POC

A Streamlit app.

## Run it

Double-click `run.bat`, or in a terminal in this folder:

    .venv\Scripts\python.exe -m streamlit run app.py

Then open http://localhost:8501 (it usually opens automatically). Stop with Ctrl+C.

## Check a stage

Double-click `check_stage1.bat`. It prints a PASS/FAIL list in plain words and writes
`docs\scenario.md`, `runs\stage1\lab_report.html` and `runs\stage1\lab_measurements.csv`.
All tunable numbers are in `config\settings.yaml`.

## Add a library

    .venv\Scripts\python.exe -m pip install <package>
    .venv\Scripts\python.exe -m pip freeze > requirements.txt

## Rebuild the environment (e.g. on a new machine)

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
