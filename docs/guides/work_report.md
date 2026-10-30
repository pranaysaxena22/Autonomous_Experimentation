# Work report: Stages 5 to 10

**Illustrative. Written for the project owner, to be read on waking.** Everything described is a simulation with made-up (illustrative or synthetic) values. Nothing was run on client data and nothing says anything about real tablets.

## 1. The short version

- **Done and saved (each stage has its health check and its own saved version on the branch `platform-build`):** Stage 6 (motion planner and executor), Stage 5 (configurable cell simulator), Stage 7 (3D replay viewer), Stage 8 (dashboard integration), Stage 9 (reports and exports) and Stage 10 (hardening). The requested demo script, the plain-language explanation of the whole system and the design for the sealed acceptance run are written, in the Deloitte look.
- **All health checks pass.** The final full run is in section 6.
- **Not done, on purpose:** the sealed acceptance run (4-5) was **not built and not run**; only its design was written for your review. Rules 3 and 4 of the decision engine, the three locked engine files, the sealed lab and every seed were left exactly as they were. Nothing was merged into `main`.
- **Where to start:** double-click `make_guides.bat` and open the demo script and the system explanation in `runs\guides`. Then double-click `run_platform.bat`.

## 2. What you asked for, and how it was read

| Your instruction | What was done |
|---|---|
| "Complete everything till stage 8" while you sleep, taking the best decisions | Stages 6, 5, 7 and 8 built, checked and saved |
| "After stage 8, also draft the design of the sealed acceptance run, do not run it without my written confirmation" | A design document for review was written (section 5). Nothing was built or run |
| "Also do stage 9 and 10 and all other checks or tests required for the whole project" | Stage 9 (reports) and Stage 10 (hardening) built with their own checks; the whole suite was run |
| "A simple script on how I can demo the whole project, and explain the whole system in simple language, how it is built, how to operate it" | `demo_script` and `system_explained` guides |
| "Remember everything should be with the Deloitte template or branding" | Reports, Excel files, guides and pages all use the Deloitte palette and Open Sans (a check enforces this) |
| "Why 7 after 5, where is stage 6" | Stage 6 was built first, because the simulator takes fault timing from the executor. The numbers did not change |

## 3. What was built, stage by stage

| Stage | What it is | Its check |
|---|---|---|
| **6. Planner and executor** | The planner turns a recipe, the setup and the layout into a motion plan (ten kinds of action, five steps). The executor runs a plan and reports what really happened, including faults and recovery. It reproduces the hand-authored example timeline action by action | `check_planner.bat`, `check_executor.bat` |
| **5. Configurable cell simulator** | The proof of concept's simulator, driven by the setup: its plan, its executor, its faults (scripted and random). A fault now costs what its recovery costs (about 64 minutes for the jam of trial 8, not the proof of concept's 90). Recounted independently on several setups | `check_cellsim.bat` |
| **7. 3D replay viewer** | One self-contained page that replays every action of every trial in 3D, offline, with fault banners and recovery badges. Checked in real headless Chrome, including with all network blocked and with 3D switched off | `check_viewer.bat` |
| **8. Dashboard integration** | The dashboard shows a platform run: the six usual pages plus **3D replay** and **Data and model**. The original proof-of-concept record still shows exactly its six pages, proved by comparing with a recording made before the change | `check_dashboard.bat` |
| **9. Reports and exports** | A branded report page, a PDF, an Excel workbook and three CSV tables from the run record, every file labelled. The dashboard's **Reports** page offers them as downloads | `check_reports.bat` |
| **10. Hardening** | Ten deliberately bad setups, rubbish data and record files, long accented non-Latin names in folders with spaces and accents, the whole chain agreeing on one set of numbers, identical files from identical runs, a run with every network call blocked, a clean copy of the project, time limits, documentation | `check_hardening.bat` |

### Added afterwards: the live run

You asked to watch the simulation run live rather than replay it. After your "go ahead", I built **`run_live.bat`** (page at http://localhost:8504): the simulation runs on its own while you watch, with the 3D arm, the simulated clock, results that appear when their tests finish, faults when they strike, a chart of good recipes and Start, Pause, speed, camera and Restart controls. It is a separate part, so the dashboard and the replay are unchanged. A check proves a live run gives **exactly** the same trials as a normal run, that nothing appears before its moment, and that the page listens only on this computer (`check_live.bat`). It is still a simulation, faster than real time. Not built: injecting a fault from the page during a run.

## 4. Decisions taken without asking, and why

Each is recorded in `docs\decisions.md` ("Stages 5 to 8 as built" and below). Say if you want any changed.

1. **Platform pages appear only for a platform record.** The original dashboard is untouched for the original record.
2. **The default platform run uses the proof of concept's adaptive strategy; the Stage 4 engine drives only the connected run** (added later at your request: `run_platform.bat connected`). Keeping the default unchanged leaves existing behaviour alone. The Data and model page says which engine chose the recipes.
3. **The planner can rescale the proof of concept's recipes to a full batch** (they add up to about 77%), and writes that into the plan.
4. **The PDF is made by an installed browser (Chrome or Edge), not a new library.** Excel uses the library already in the project. If no browser is found, the report page says to open it and print to PDF. No new library was added.
5. **The guides are generated into `runs\guides`** (not saved in git), so they can never be out of date. The Markdown sources are in `docs\guides`.
6. **Report files carry no clock time**, so the same run always gives identical files.
7. **A format check (E2) flagged the new `platform` section of the run record.** The right fix was to add the section to the format's schema and example, not to weaken the check. Done.
8. **`check_cellsim` no longer lists the whole dashboard folder as untouched.** The eight proof-of-concept page files and the root launcher are still listed; `check_dashboard` proves the proof of concept renders as before. No check was removed or weakened.

## 5. What was deliberately not done

- **The sealed acceptance run (4-5).** It is the one step that cannot be undone. I wrote a design for your review (guide "The sealed acceptance run: a design for review") with seven decisions for you (D1 to D7). **No runner was built and the sealed lab was not opened, imported or run.**
- **Rules 3 and 4 of the engine.** Not diagnosed, not changed. The design asks you (D4) whether to revisit them before the acceptance run, because after it they are frozen for good.
- **A second acceptance run in Stage 10.** The sealed lab has one block of 40 live seeds; a second run on the same seeds would not be blind. The design proposes a new lab version if one is wanted (D6).

## 6. Health-check results

**The final full run of `check_all.bat` (31 checks, 17 minutes 36 seconds): 1,253 passed, 0 failed, 1 old design warning (the robot's reach margin).** Before this work the count was 948. The checks added in this work: planner 21, executor 20, cell simulator 21, 3D viewer 24, dashboard integration 31, reports 42, live run 48, connected loop 26, run this setup 31, rules 3/4 tool 10, hardening 30.

| Check | Passed | Check | Passed |
|---|---|---|---|
| PoC stages 1 to 5 | 38, 35, 52, 58, 67 | Engine | 42 |
| Formats | 71 (1 old warning) | Comparison | 29 |
| Platform 1 (setup) | 82 | Seed guard | 10 |
| Ingest | 111 | Recalibrated | 20 |
| Models | 91 | Planner | 21 |
| Calibration | 32 | Executor | 20 |
| Domain | 43 | Cell simulator | 21 |
| Replay | 48 | 3D viewer | 24 |
| Scorecard | 44 | Dashboard | 31 |
| Seal | 16 | Reports | 42 |
| Brief | 31 | Hardening | 30 |
| Dev lab | 28 | Live run | 48 |
| Connected loop | 26 | Run this setup | 31 |
| Rules 3/4 tool | 10 | | |
| | | **Total** | **1,253** |

(These totals were written into this guide after the final run; the guide is a text file and nothing else changed after that run.)

## 7. Things to know, said plainly

1. **I could not take a picture of the 3D replay page inside the finished dashboard automatically.** Streamlit loads its content over a live connection that headless Chrome did not wait for. What was verified: the page embeds exactly the saved replay file, character for character; the replay file itself is verified in real Chrome. **By-eye step:** double-click `run_platform.bat`, open the **3D replay** page and press Play (the demo script does this).
2. **The example setup has no "validation" section**, so the Data and model page says no modelling table was built for it. That is accurate, and the run is not affected. Model results live in the scorecards.
3. **The platform run fits more trials per week (40.6) than the original dashboard**, because a recovered fault now costs what its recovery costs. It is not a target and nothing was tuned to it.
4. **One old design warning remains** (the robot's tightest spot has less than 0.10 m of spare reach). It is the same warning the setup app shows, a known one.
5. **Platform runs are limited to what the stand-in lab can represent**: the proof of concept's five ingredients and two targets. Anything else is refused in plain words.
6. **Everything on the dashboard and the 3D replay is a replay of a simulation.** Nothing here is evidence about real tablets.

## 8. What I need from you

1. Read the demo script and try `run_platform.bat` (about 15 minutes).
2. Read the acceptance-run design and answer D1 to D7, or tell me what to change. **Nothing will run until you approve it in writing.**
3. Decide whether rules 3 and 4 are to be revisited before that run (D4).
4. Say whether you want the Stage 4 engine wired into the platform run later.

## 8b. Does the whole system meet the core requirement?

The plan's goal (`docs/platform_plan.md`, section 1) is a platform a client can use **end to end**: fill in a setup, load their experiment table, let the platform model the data and say how far to trust it, run an unattended cell simulation with a decision engine, watch a 3D replay, and export reports, as one product.

**Update: the setup app now runs your setup, with three illustrative examples to start from, and the live page lets you choose which setup to run** (see "Run this setup" and "Three illustrative example setups" in `docs/decisions.md`).

**Update: the loop is now connected** (`run_platform.bat connected`, `run_live.bat connected`; see "The connected loop" in `docs/decisions.md`). The data file is read and cleaned, the models are judged on it, what Stage 3 concluded becomes the engine's brief, and the adopted Stage 4 engine chooses every recipe, process settings included, from that data and the measurements so far. The chain reproduces the Stage 4-2 brief byte for byte and the first recipe equals the engine's own (`check_connected.bat`). The default platform run is unchanged.

| Part of the goal | Status | What is missing |
|---|---|---|
| Fill in a setup | **Met, and it now drives a run:** ten screens, plain messages, and **Save and run it** on the last screen simulates the saved file (a 240-hour window gives 60 trials, not 30) | It covers the proof of concept's five ingredients and two targets only |
| Load the experiment table | **Met.** Safe reading and cleaning of CSV and Excel, row accounting, labelled quality reports | Tested on synthetic and public data only, never on a client's file |
| Model the data and say how far to trust it | **Met, and now part of the run** in the connected loop: the Data and model page shows what Stage 3 concluded for each result | The connected setup uses the development lab's synthetic history; a setup of your own needs a `validation` section |
| Unattended cell simulation with a decision engine | **Met.** In the connected loop the adopted Stage 4 engine chooses the recipes from the data | In the default run the simpler original strategy is used; the setup app's run uses it too, and does not yet start a connected run for your own data |
| 3D replay | **Met**, recorded and live | A generic arm, not a real robot |
| Export reports | **Met**: page, PDF, Excel, CSV | The report carries the data and model text but not the full model scorecard |
| One product, one launcher | **Partly met.** `run.bat` opens the original dashboard and the setup app; the platform, connected, live and report launchers are separate | `run.bat` does not yet offer them in its menu |
| A result they can trust | **Not yet.** Every result is synthetic, the Stage 4 engine's acceptance run has not been done, and the engine loses to ignoring the alarm in all four tested scenarios | Needs the acceptance decision (D1 to D7), a decision on rules 3 and 4, and real data with expert review |

**In one sentence:** the chain from data to models to engine to cell now runs as one connected loop and every piece is checked and honestly labelled, but it is still a synthetic, simulated platform: the data and the lab are the same synthetic world, no real data or expert review exists, and the engine's acceptance run and the questions about rules 3 and 4 are still open.

**What would come next:** let the setup app start a connected run on the user's own saved setup (it needs the `validation` section and a lab that matches its ranges; the plain **Save and run it** already runs it with the default strategy), add the platform and live options to the `run.bat` menu, and carry the model scorecard into the reports.
## 9. Files added or changed

- **New parts:** `cellpoc\planner`, `executor`, `platform_cell`, `viewer`, `reports`, `platform_info.py`, `platform_runner.py` and three dashboard pages (`platform_replay`, `platform_data`, `platform_reports`).
- **Changed:** `cellpoc\dashboard\app.py` (conditional pages), the run record (one optional `platform` section) and its reader, the architecture guard (new parts only), the run-record schema and example, the README and the decision record.
- **New launchers:** `run_platform.bat`, `make_platform_demo.bat`, `make_reports.bat`, `make_guides.bat`, `check_planner.bat`, `check_executor.bat`, `check_cellsim.bat`, `check_viewer.bat`, `check_dashboard.bat`, `check_reports.bat`, `check_hardening.bat`.
- **Not touched:** `main`, `config\settings.yaml`, the sealed lab, the three locked engine files, the seeds and every proof-of-concept page file.
