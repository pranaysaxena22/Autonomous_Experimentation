# The autonomous formulation cell explained

> **Start with the unified app (2026-10-16).** Double-click `run_app.bat` and press Enter: one app at http://localhost:8510 holds every screen below (Overview, Results at a glance, Setup, The run, Live run, 3D replay, Physics (MuJoCo), Data and model, Reports, About and limits). The ports and launchers named below (8501 to 8506, `run.bat`, `run_platform.bat`, `run_live.bat`) still work on their own. For a client, use the **client demo script** (`client_demo_script`).

**Illustrative. Everything in this project is a simulation with made-up (illustrative or synthetic) values. Nothing here is real client data, and nothing says anything about real tablets.**

## 1. What is it, in one minute

Imagine a small robotic laboratory that makes tablets. A person describes what they want (a tablet that dissolves fast enough and is hard enough). The cell then works **on its own, including nights and weekends**: it chooses a recipe, makes the tablets, measures them, learns from the measurement and chooses a better recipe, over and over. When something goes wrong (a bottle jams) it tries to recover by itself, and if it cannot, it skips that recipe and leaves a message for the people who come in next.

This project is **a simulation of that cell, plus the software platform around it**. There is no physical robot. A computer program plays the cell, another program plays "reality" (the tablets and the measuring instruments), and a dashboard shows what happened. The point of building it first as a simulation is to prove the ideas, and to design the software so that a real robot, or a robot simulator such as Gazebo, can be connected later without rebuilding everything.

## 2. The idea behind it: a loop of four words

Every trial the cell does goes round the same loop. The dashboard shows these four boxes.

| Word | What it means here |
|---|---|
| **Act** | Make the tablets: dispense the ingredients, mix, press. |
| **Sense** | Measure them: dissolution (how fast the drug is released) and hardness. |
| **Reason** | Decide what to try next, from all the results so far, and write down why. |
| **Adapt** | Clean up and get ready for the next recipe. |

The cell repeats this about 30 times in a 5-day window (Friday evening to Wednesday evening in the example), with nobody in the lab most of the time. The people are only in on Monday and Tuesday, 08:00 to 18:00, so what happens overnight is summarised for them as a **handover**.

## 3. What is real and what is pretend

| Real (the software is genuinely built and tested) | Pretend (a stand-in) |
|---|---|
| Reading a client's data file safely (CSV or Excel), cleaning it, and reporting every problem in plain words | The tablets, the instruments and the robot arm: they are simulated |
| Checking models honestly (always on groups of recipes the model has never seen) | The numbers: the example values are made up (labelled **illustrative** or **synthetic**) |
| Planning every arm movement for a trial and running it through an "executor" | The executor itself today is a Python stand-in that behaves like a robot would, including faults |
| The dashboard, the 3D replay, the reports | Any claim about real tablets: none is made |

Every page and file says so: **illustrative**, **synthetic**, or **real public data, not client data**. There is also a standing rule that nothing is ever sent over the internet and everything works offline.

## 4. The pieces, and how they connect

Think of a factory line. Each piece has one job, and the project has an automatic check that stops a piece from reaching into another one's business (for example, the decision engine may never see the hidden truth of the simulated lab, and the dashboard may only display).

| Piece | Its one job |
|---|---|
| **Setup app** (ten screens) | A person describes the study: ingredients, limits, targets, equipment, calendar, faults. It checks everything in plain words and saves a setup file. |
| **Data reader** | Takes the client's past experiments (CSV or Excel), cleans them, and writes a data quality report that accounts for every row. |
| **Modelling** | Builds prediction models from that data and tests them only on whole groups they have not seen (whole batches, suppliers, later dates), never on random rows. |
| **Calibration and warnings** | Checks whether a model's stated uncertainty is honest, and warns when a recipe is far from anything the model learned from. |
| **Decision engine** | Chooses the next recipe from the measurements so far and gives a reason. It sees only measurements and the specification, never the hidden truth. |
| **Virtual lab** | Plays reality: a hidden true behaviour of tablets plus measurement noise. |
| **Motion planner** | Turns a recipe, the setup and the equipment layout into a plan: a timed list of arm actions (move, pick, place, pour, shake, press, stir, scan, read, wait) in five steps (dispense, mix, press, test, clean). |
| **Executor** | Runs the plan action by action and reports what really happened: actual times, instrument readings, faults and the recovery actions it took. |
| **Cell simulator** | Keeps the clock, the staff calendar and the event log, and turns what the executor reported into the run record. |
| **Dashboard** | Displays the run record. It calculates nothing (with one documented exception: trials per week divided by the manual baseline). |
| **3D replay** | Replays the executed timeline as a picture of the cell. It has no logic of its own. |
| **Reports** | Writes a branded report page, a PDF, an Excel workbook and CSV tables from the run record. |

**The connected loop** is the same flow with the front of the chain attached: the data file is read (Stage 2), the models are judged on it (Stage 3), the conclusions become the engine's brief (Stage 4-1), and the engine then chooses each recipe from that data and the measurements so far. In the default run the engine is the proof of concept's simpler strategy instead.

**The flow of one platform run:** setup file and layout, then the decision engine picks a recipe, the planner makes a plan, the executor runs it (asking the virtual lab for the instrument readings), the cell simulator turns that into the run record, and finally the dashboard, the 3D replay and the reports all read the same record or the same executed timelines. That is why the numbers agree everywhere.

## 5. How it was built: stages

The work was done in stages. Every stage ended with a plain-language **health check** you can double-click, and a saved version (a git commit) on the branch called `platform-build`. The original proof of concept lives safely on the branch called `main` and was never changed.

| Stage | What it added |
|---|---|
| Proof of concept | The simulated cell, the virtual lab, an adaptive recipe chooser, and the six-page dashboard. |
| 1. Setup app | The ten-screen setup with a plain message beside each field and every rule tested. |
| 2. Data ingestion | Safe reading and cleaning of CSV and Excel files, with row accounting and labelled quality reports. |
| 3a. Modelling | Prediction models and a strict, group-based comparison. Nine candidates including two simple baselines. |
| 3b. Calibration and warnings | Honest uncertainty, the "is this recipe far from the data" warning, a replay of decision usefulness and scorecard pages. |
| 4. Decision engine upgrade | A governed engine with five rules, a recalibration response, a richer development lab, and a sealed acceptance lab kept locked. See section 9 for what was found. |
| 6. Planner and executor | Plans every movement; runs it through a stand-in executor that includes faults and recovery. |
| 5. Configurable cell simulator | Timings, calendar and faults now come from the setup file, and a fault costs what its recovery actually costs. |
| 7. 3D replay viewer | One self-contained page that replays every trial in 3D, offline. |
| 8. Dashboard integration | The dashboard shows a platform run's results, 3D replay and data page, and the original pages are unchanged. |
| 9. Reports and exports | Report page, PDF, Excel and CSV, all labelled. |
| 10. Hardening | Tests that try to break it, a clean-copy test, a no-network test, odd folder names, time limits, documentation. |

(Stage 6 was built before Stage 5, because the simulator's fault timing has to come from the executor.)

## 6. How to operate it

Everything is started by **double-clicking a file** in the project folder. You never need to type a command.

### The ones you will use most

| Double-click | What happens |
|---|---|
| `run_platform.bat` | Builds a platform run from the example setup (a few seconds) and opens the dashboard on it at http://localhost:8503, with three extra pages: **3D replay**, **Data and model** and **Reports**. Drag one of your saved setup files onto it to run that setup instead. |
| `run.bat` | A small menu. **1** the original results dashboard (port 8501), **2** the setup app (port 8502), **3** both. |
| `run_platform.bat connected` | **The loop connected** (opens at http://localhost:8505). The data file is read and judged, what Stage 3 concluded becomes the engine's brief, and the adopted decision engine chooses every recipe, compression force and blend time included, from that data and the measurements so far. Add a scenario if you like: `new_supplier`, `period_shift`, `unpredictable_dissolution`. All synthetic. |
| `run_live.bat connected` | The same, live. |
| `run_live.bat` | **The live run.** Opens http://localhost:8504, where the simulated cell runs while you watch: the 3D arm moves, the simulated clock advances, results appear when their tests finish, faults when they strike. Press **Start the run** and pick a speed (300x is one simulated hour per 12 real seconds). |
| `make_platform_demo.bat` | Builds a platform run and opens the 3D replay directly, at the trial with the jam. |
| `make_reports.bat` | Writes the report page, PDF, Excel and CSV files for the latest run into a `reports` folder next to the run record. |
| `make_guides.bat` | Writes this guide, the demo script, the work report and the acceptance-run design as branded pages and PDFs into `runs\guides`. |
| `build_demo.bat` | Rebuilds the original proof-of-concept run record (about a minute). Needed after changing `config\settings.yaml`. |
| `check_all.bat` | Runs every health check and prints one table. About 15 to 20 minutes. Each stage also has its own `check_...bat`, which is much quicker. |

**To stop an app:** close its black window (or click it and press Ctrl+C). If a window says a port is already in use, that app is already running in another black window.

### Live run or replay?

- **Live run (`run_live.bat`):** you choose which setup to run from the list at the top of the page (the three illustrative examples, your saved setups, or the loop connected); the simulation advances while you watch and publishes each thing at its simulated moment. You can pause it, change the speed and the camera. It is the same simulation as a normal run (a check proves a live run gives exactly the same trials), only paced, and it saves the finished run so the dashboard can open it.
- **Replay (the dashboard's 3D replay page, or `make_platform_demo.bat`):** plays back a run that has already finished. It is the safest choice for a demo because it is repeatable and instant.

### Running your own study

1. Double-click `run.bat`, choose **2**, and describe the study in the setup app. **Save setup** is greyed out while any error remains.
2. On the last screen press **Save and run it**: it saves the file in the `setups` folder and simulates a run of that saved file in a few seconds. Then press **Open the dashboard on this run** or **Watch this setup run live**. (You can also drag a saved file onto `run_platform.bat` or `run_live.bat`.)
3. If it cannot be simulated yet (for example it has a sixth ingredient, which the stand-in lab cannot represent), you get a plain message saying what to change.

### Reading the dashboard

- **The run:** a slider and Next/Previous event buttons. At any moment it shows each station's status, who is in the lab, the recipe and why it was chosen, and the result only once the test has finished.
- **Timeline:** every trial across the run, nights and weekends shaded, faults and skips marked.
- **Overnight handovers:** what happened while nobody was in.
- **Does learning help?:** the adaptive strategy against a fixed list and random recipes.
- **Throughput:** autonomous against a manual baseline you can edit. This is the one place the dashboard does a calculation.
- **What this shows:** states what the simulation does and does not show.
- **3D replay** (platform runs): press **Play**. Choose a trial from the numbered chips (green is good, grey not good, red skipped, amber underline recovered from a fault). Pick a **Camera** (overview, top, rack, balance, press, gauge, friabilator, vessel). Click an action in the list to jump to it. A red banner appears at a fault, and an amber **RECOVERY ACTION** badge on recovery actions.
- **Data and model** (platform runs): how the pieces connected, what the data reader found in the data file, what the modelling step made of it, and what the run does not show.
- **Reports** (platform runs): download buttons for the files from `make_reports.bat`.

## 7. How to read a result honestly

- A **trial with a result** was measured; a **skipped** trial has no result and no number.
- **Good** means it met the specification (dissolution at least 85% at 30 minutes, hardness 6 to 10 kP in the example). The **margin** says how comfortably.
- The number of trials that fit in the run is always written as a range ("about 29 to 30"), because it hangs on a small timing margin. In the platform run the figure is whatever that setup produces, and it is **not a target**.
- "Trials per week" is the trials with results, scaled to a 168-hour week, compared with a manual baseline of 9 per week that is **an assumption you can edit**.

## 8. The safety rules built into the project

1. **Labels everywhere:** every page, file and report says illustrative, synthetic, or real public data (never client data).
2. **Nothing leaves the computer** and nothing needs the internet. The project's checks look for web addresses and network use.
3. **Separate pieces:** an automatic check reads the code and fails if a piece imports something it should not (for example the dashboard calculating things, or the decision engine seeing the lab's hidden truth).
4. **Locked and sealed things:** three engine files are locked by fingerprint, and a second, sealed laboratory for a final acceptance test is locked and has never been run. Seeds that were used for a test are never reused to judge a later change.
5. **Every stage ends with a health check and a saved version.** Nothing is merged into `main` without you.

## 9. What it does not do, and what was honestly found

- **It is a simulation.** There is no real robot, the arm is generic, and nothing says anything about real tablets or a client.
- **The Stage 4 engine drives only the connected run.** The default platform run (`run_platform.bat`) uses the proof of concept's adaptive strategy; `run_platform.bat connected` closes the loop, so the adopted Stage 4 engine chooses every recipe from the data file and what Stage 3 concluded about it. The measured finding about that engine, from a full comparison on a development lab, is that **it loses to simply ignoring the alarm in all four tested scenarios** (it beats random recipes by a wide margin in all four, but the same models without governance do better). Most of that cost is in the deliberate caution of its rules 3 and 4. That is recorded, not hidden.
- **The sealed acceptance run (Stage 4-5) has not been run.** It is the one step that cannot be undone, so it needs your written approval of a design. The design is written for your review (see the guide "The sealed acceptance run").
- **On real batch data**, dissolution is barely predictable from the available columns, and the warnings are weak for a new supplier or period. Nothing has been run on client data.
- **The reshaping question:** the recalibration response was never tested against a shift that changes the ranking of recipes.

## 10. What comes next

| Next step | Who decides |
|---|---|
| Review the acceptance-run design and approve or change it | You |
| Decide whether to diagnose or change rules 3 and 4 of the engine before that run | You |
| Connect an executor for a robot simulator (such as Gazebo) or real hardware: it must implement the same executor interface (plan in, executed timeline out), and the dashboard, replay and reports need no change | A later stage |
| Try the platform on a client's real data file | A later stage, with the client's agreement |

## 11. Glossary

- **Run record:** one file with everything a finished run produced, already worked out; the dashboard and the reports read it.
- **Setup:** the file that describes a study (ingredients, limits, targets, equipment, calendar, faults).
- **Plan / executed timeline:** the intended list of actions for a trial, and the list of what really happened (with actual times, readings and faults).
- **Fault and recovery:** something goes wrong (a bottle jams); the cell taps and shakes, puts the bottle back, purges and retries. If the retry fails the candidate is skipped.
- **Handover:** a plain-language summary of what happened while nobody was in the lab.
- **Calibration:** whether a model's stated 90% range really contains the truth about 90% of the time.
- **Applicability-domain warning:** a warning that a recipe is far from what the model has seen.
- **Governed engine:** the Stage 4 decision engine with five rules that stop it trusting a model where the model should not be trusted.
- **Sealed lab:** a second simulated lab kept locked until a final, one-time acceptance run.
- **Illustrative / synthetic:** made-up values, or values made by a program; never real client data.
