# Cell POC

A simulated autonomous formulation cell (tablet recipes), with a Streamlit dashboard.
**Simulation with illustrative values** - nothing here is real client data.

## Run the dashboard

Double-click `run.bat`. If the run record does not exist yet it is built first (about a minute); then the
dashboard opens at http://localhost:8501. It works fully offline. Stop it with Ctrl+C.
`build_demo.bat` rebuilds the record after you change `config\settings.yaml`. See `docs\dashboard.md`.

All tunable numbers are in `config\settings.yaml`. The plain-English description of the scenario is
`docs\scenario.md` (generated from the settings by the checks).

## Check a stage

Each stage has a health check you can double-click. It prints a PASS/FAIL list in plain words.

| Stage | Double-click | What it covers | Time |
|---|---|---|---|
| 1 | `check_stage1.bat` | settings, scenario page, virtual lab | seconds |
| 2 | `check_stage2.bat` | the cell simulator on a fixed list | seconds |
| 3 | `check_stage3.bat` | adaptive engine, 40-campaign comparison, difficulty table | a few minutes |
| 4 | `check_stage4.bat` | closed-loop run with scripted faults, alerts, overnight summaries | under a minute |
| 5 | `check_stage5.bat` | the dashboard | a few minutes |

Run them in order the first time: Stage 4 also confirms every generated chart page works with no internet.
Outputs are written under `runs\` (not saved in git).

## Add a library

    .venv\Scripts\python.exe -m pip install <package>
    .venv\Scripts\python.exe -m pip freeze > requirements.txt

## Rebuild the environment (e.g. on a new machine)

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
