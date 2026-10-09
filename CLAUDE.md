# CLAUDE.md - standing rules for this project

This project is a **simulated autonomous formulation cell** (tablet recipes): a proof of concept with a Streamlit
dashboard. No physical robot. Read this file at the start of every session. If a rule here conflicts with a request,
say so and ask before acting.

## How to work with me (the user)

- **I am not a coder.** Explain everything in plain language. No unexplained jargon. Say what you did and why.
- **Ask one question at a time.** Never a list of questions. Pick the question whose answer changes what you do next.
- **Plan first, then wait.** Before writing any code, propose a plan and wait for my approval. This includes small
  changes. Exception: I have explicitly told you to do something.
- **Never change existing behaviour or delete an existing check without asking me first.** If a change would alter what
  a run produces, what a page shows, or what a check asserts, stop and ask, even when it looks like a fix.
- **Don't add features I didn't ask for.** No databases, logins, cloud services, accounts, new dependencies or extra pages
  without first explaining why and asking. Prefer the simplest thing that does the job.
- Report results honestly. If a check fails, say so with the output. If something was not verified, say that.
- Give me a way to verify every change that needs no code reading (a double-click, a file to open, a page to look at).

## Labelling: nothing here is real

- Every output (pages, charts, files, reports, docs, messages) must be labelled **"illustrative"** or **"synthetic"**
  until real client data and expert review exist. The dashboard banner says "Simulation with illustrative values".
- Never present a result as a prediction or a claim about real tablets. Say what the simulation does **not** show
  (see `cellpoc/about_text.py`, the single source for the Limitations text).
- Trial counts are written as a range ("about 29 to 30 trials"), never a bare number, because the count hangs on a
  small timing margin.

## The five parts, kept separate

| Part | Folder | Its one job |
|---|---|---|
| Settings | `config/settings.yaml`, `cellpoc/settings/` | Every number you might change. Values only. |
| Virtual lab | `cellpoc/virtual_lab/` | Plays reality: hidden true behaviour plus noise. |
| Cell simulator | `cellpoc/cell_simulator/` | Clock, steps, faults, event log, run record. |
| Decision engine | `cellpoc/decision_engine/` | Chooses the next recipe from measurements. |
| Dashboard | `cellpoc/dashboard/` | Displays the run record. Calculates nothing. |

- **The decision engine never sees the virtual lab's hidden truth.** It sees only measurements and the specifications.
  Only the virtual lab itself and `cellpoc/scoring.py` (scores results after the fact) may touch the hidden truth
  (`virtual_lab/_truth.py`, `virtual_lab/oracle.py`).
- **The dashboard shows results and calculates nothing**, with one exception: autonomous trials per week divided by the
  manual baseline (default 9), the single division in `cellpoc/dashboard/throughput.py`. Everything else it shows is
  worked out in advance and stored in the run record.
- Supporting pieces (not a sixth part): `contracts/` (shared data shapes), `run_store/` (reads and writes the run
  record), `comparison/` (multi-campaign comparison), `runner.py` (wires the parts together), `about_text.py`.
- An automated check (`checks/architecture.py`) enforces which part may import which, and scans the dashboard for
  arithmetic, sorting, min/max/sum, filtering, calculation libraries and web addresses. Do not loosen it without asking.

## Stages, health checks and git

- Work is built in **stages**. **Every stage ends with (1) a plain-language health check I can double-click and
  (2) a git commit.** A stage is not finished without both.
- Health checks live in `checks/` and are launched by `check_stageN.bat` (1 to 5). Each prints PASS/FAIL lines in plain
  words and ends with "ALL GOOD" or "SOMETHING NEEDS ATTENTION". Write new checks the same way.
- Before any commit, run all existing checks. They must all pass. Report the counts. Never delete or weaken a check to
  make it pass.
- **Branches:** `main` holds the working proof of concept and must stay safe. All new work goes on `platform-build`
  (or another branch I name). Never merge into `main`, force-push or rewrite history without asking.
- Commit messages: short, plain, say what changed. Don't skip hooks. Never commit generated `runs/` output (it is
  ignored) or secrets.

## Data and safety

- **Mock data in `data/mock/` is synthetic** (made by `tools/make_mock_data.py`). **Never tune models to it.** Test on
  freshly generated seeds, not on the files already in the folder.
- **No client data in the repository. No uploads to external services.** Don't send project files, data or results
  anywhere. Nothing in the dashboard may need the internet: it must work fully offline.
- Seed policy: never change a seed after seeing outcomes. The 40-campaign comparison uses the default seed (2026) plus
  the 39 after it. Engine changes are judged on separate development seeds (10000 and up), never on those 40.
- Don't tune anything to hit a particular headline number (for example 30 trials). Report what the run produces.

## How to run things (Windows)

- Python is in `.venv`. Use `.venv\Scripts\python.exe`; don't install into the system Python.
- `run.bat` starts the dashboard (builds the run record first if missing). `build_demo.bat` rebuilds
  `runs/demo/record.json` (about a minute). Rebuild after changing settings or code that affects the record.
- `check_stage1.bat` to `check_stage5.bat` run the health checks (stage 3 and 5 take a few minutes).
- Shell is PowerShell: no `&&`; use `;` or `if ($?)`. Use the dedicated file tools rather than shell for reading/editing.
- Add a library only with my approval, then update `requirements.txt` (`pip freeze`) and say why it is needed.

## Where things are

- `docs/scenario.md` - the scenario in plain English (generated from the settings by `check_stage1`; edit the settings).
- `docs/dashboard.md` - what the dashboard does and its one exception. `README.md` - how to run, check and demo.
- `runs/` - generated output, not in git. `static/` - bundled Open Sans font (licence alongside).
- `reference/robot_cell_viewer_reference.html` - a reference viewer to look at, not part of the running app.
- `tools/make_mock_data.py` - synthetic data generator. Don't run it to overwrite `data/mock/`; write to a new file.

## Conventions worth keeping

- The run record (`cellpoc/contracts/run_record.py`) is the contract between the simulator and the dashboard. Changing
  its shape means rebuilding `runs/demo/record.json`; the dashboard shows a plain "out of date" message for old records.
- What the dashboard shows at a moment must not reveal what is not yet known (a result before its test finishes, a
  fault before it happens). The Stage 5 check guards this; keep it that way.
- Look and feel follows the Deloitte brand: Deloitte Green #86BC25 first, Open Sans with Arial fallback, colours only
  from the palette (a check enforces it). Green is not used for small text on white.
- Charts in generated HTML files must bundle their library (work offline). Use `checks/common.write_chart_page`.
- Plain-language error messages in settings checks: say which setting is wrong and what to write instead.
- Keep code simple and consistent with the surrounding style. Comment the why, not the what.
