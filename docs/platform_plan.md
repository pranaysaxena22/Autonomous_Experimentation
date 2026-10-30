# Platform plan (approved)

> **Everything in this plan is for an ILLUSTRATIVE / SYNTHETIC build.** No real client data or expert review exists yet.
> Branch: all work happens on `platform-build`; `main` keeps the working proof of concept (PoC) safe.
> Example files for every format are in `docs/platform_formats/`. Decisions and reasons are in `docs/decisions.md`.

## 1. Goal
Turn the proof of concept into a platform a client can use end to end, with a result they can trust and understand:
fill in a **setup** (ingredients, ranges, constraints, targets, equipment, timings, faults, manual baseline), load their
**experiment table**, let the platform **model** the data and say how far to trust it, run an **unattended cell simulation**
with a decision engine, watch a **3D replay** of the robot, and export **reports**. One launcher (`run.bat`) offers both the
setup app and the results dashboard, so it feels like one product.

## 2. Findings that shape the plan

**Libraries on Python 3.14.6 (as built through `stage3b-complete`).** Installers were first checked by dry run, then each library was added only with
your approval: `openpyxl` and `pandas` in Stage 2 (Excel and tables), and in Stage 3a only `scikit-learn` 1.9.1 (it brings scipy, joblib and threadpoolctl; the lock
file went from 41 to 46 packages). **statsmodels, PyTorch, LightGBM, XGBoost and MAPIE were tested and stay out: none is needed** (an earlier version of this plan
expected to use statsmodels). `reportlab` (PDF) is not installed yet; it is for Stage 9. No torch or tensorflow (not needed for a few thousand tabular rows).

**The mock data (synthetic, made by `tools/make_mock_data.py`).**
- Ingredients sum to 100% (filler is the balance, 55 to 87%). Extra controllable settings: compression force (5 to 20 kN),
  blend time (5 to 30 min). Batch-level factors: binder supplier (A/B/C), filler grade, which of two dissolution instruments
  (one drifts over time). Replicates, failed runs, missing values, hardness in newtons, friability "<0.05".
- Sizes: easy 3,672 rows (3,000 experiments, 60 batches); hard 3,692 rows; small 114 rows (90 experiments, 4 batches).

**Corrected: how common is a passing recipe?** Passing = dissolution at least 85% **and** hardness 6 to 10 kP.
The earlier "18% of rows" (18.4% easy, 19.3% hard) is the share of **historical rows**, which cluster near good recipes.
The share of **random** recipes that pass in the mock lab, measured with fresh seeds (400,000 random recipes for the formula
rows; 12,000 random experiments for the full generator with clustering switched off):

| Mock setting | Formula only, no noise | Formula plus measurement noise | Full generator (batch, supplier, instrument drift, noise), measured | Same, true value without noise |
|---|---|---|---|---|
| easy | 6.6% | 6.7% | 8.2% | 6.5% |
| hard | 9.7% | 10.0% | 11.2% | 10.0% |

**"Hard" means harder to model, not rarer to pass.** The hard setting has stronger interactions and non-linearity, more noise,
bigger batch and supplier effects, larger drift with a recalibration step, poorer coverage (85% of historical experiments
clustered), more failed runs, more missing values, more mixed units and occasional wild outliers. A random recipe is, if
anything, slightly more likely to pass. The PoC's own lab is much rarer (about 3%).

**The reference viewer (`reference/robot_cell_viewer_reference.html`).** One generic arm on a circular table with six stations
(rack and scanner, balance with five bottles, hand press, hardness gauge, dissolution vessel, discard bin). Actions: scan,
pick, pour, shake, press, stir, read instruments; a jam is cleared by tap-and-shake and a retry. It also contains its own
made-up lab, engine and run builder in JavaScript, and loads its 3D library and font from the internet. The platform viewer
must contain no logic, only replay a plan, and must bundle everything it needs (offline).

**Screenshot testing.** Microsoft Edge headless mode is blocked by the company's admin policy. **Google Chrome headless works**
with software rendering (`--headless=new --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader --screenshot=...`):
a test run rendered the reference viewer's 3D scene. Remote scripting (DevTools) is blocked, so the viewer must accept the
moment to show as a URL parameter. Streamlit pages DO render in a headless Chrome screenshot of a running local app when given a long virtual wait (`--virtual-time-budget=600000`; 60 seconds was too short and gave blank or half-drawn pictures), so the setup screens can be photographed (`tools/take_setup_screenshots.py`). The dashboard and setup app are still checked by Streamlit's test harness plus a checklist by eye, because the harness cannot judge appearance.

## 3. Architecture and rules
- **Parts:** settings/setup, virtual lab, cell simulator, decision engine, dashboard (the five from the PoC), plus new
  pieces: setup app, data ingestion, modelling (inside the decision-engine side), motion planner and cell executor,
  3D replay viewer, reports. The import guard in `checks/architecture.py` is extended for each new piece; it is never loosened
  without asking.
- **The setup screens are a separate small Streamlit app** from the results dashboard, because setup must validate input and the
  dashboard calculates nothing (its one exception stays: trials per week divided by the manual baseline).
  A single launcher, `run.bat`, offers both. The checks (validation rules) live in one shared module used by the screens and
  the health checks.
- **The decision engine never sees the virtual lab's hidden truth.** Models are trained only on measurements or client data.
- **The PoC keeps working.** Its settings file, runs, dashboard pages and all five existing health checks stay unchanged; every
  platform stage re-runs them. The new setup file is a superset, with a converter to the PoC settings.
- **Nothing leaves the computer.** No uploads, no accounts, no internet needed at run time. The 3D library and fonts are bundled.
- **Labelling:** every page, chart, file and report says "illustrative" or "synthetic" until real client data and expert review exist.

## 4. Data formats (examples and schemas in `docs/platform_formats/`; naming rules in `docs/naming.md`)

| File | Format | Content |
|---|---|---|
| `experiments_example.csv` + `.meta.json`; `experiments_messy_example.csv` + `.meta.json` | CSV + JSON | client experiments, the same 21 columns as `data/mock/`, with a companion file carrying the version and the synthetic label; a deliberately messy example from the hard data |
| `setup_example.yaml` | YAML | ingredients (filler as balance, `batch_size_g`), recipe rules (sum to 100), process and context factors, targets split into **constraints** (at least, at most, between) and **objectives** (maximise, minimise), equipment and step timings, calendar, faults with a structured `where`, baseline, comparison, engine, virtual-lab noise, seed, and a `data:` section for reading the experiment table |
| `cell_layout_example.json` | JSON | stations, slots, tool holders with positions, an object list, shoulder height and link lengths (3D reach is checked), camera presets (metres and degrees) |
| `motion_plan_example.json` | JSON | **intent only**: a full trial as a timed list of actions from ten names: move, pick, place, pour, shake (style mix or tap), press, stir, scan, read, wait; every action has a step; every wait has a reason naming the real process |
| `executed_timeline_example.json` | JSON | what the executor returns: the same actions plus actual times, outcomes, faults and recovery actions, each tagged origin `planned` or `recovery`; **the 3D viewer replays this file** |
| `trial8_story.md` | Markdown | plain-language table of the executed timeline, generated by `tools/make_trial_story.py` and checked against it |
| `run_record_v2_example.json` | JSON | today's run record plus data, model and motion-plan sections; every other section is marked `unchanged_from_poc`; model numbers are null until a model exists |
| `cellpoc/formats/schemas/*.schema.json` | JSON Schema | required and optional fields and allowed values for the setup, layout, plan, executed timeline, run record, experiment row and table companion. They live in the package; the four example files the setup app loads (setup, layout, experiment table and its companion) have their master copies in `cellpoc/formats/examples/`, with identical copies in `docs/platform_formats/` |

The example files are **hand-authored until Stage 6**, when the real planner will generate plans that must pass the same format checks.
`check_formats.bat` checks every file, the schemas and the naming rules (and includes self-tests that prove the checks can fail).

## 5. Setup screens (separate app)
A short wizard: Project (with the data-status label), Ingredients and constraints, Process settings, Targets, Equipment and
timings, Calendar, Faults, Baseline and comparison, Data upload and column mapping, Review and save.
Every field has a rule and a plain-English message that says which field is wrong and what to write instead
(for example: "Binder: the lowest value (9) must be below the highest (6)."; "With these ranges the filler would need to be
22%, below its lowest allowed 50%."). The detailed field list is proposed stage by stage, starting with Stage 1.

## 6. Cell executor interface
The motion plan is data. A **planner** turns a recipe, the setup and the layout into a plan. An **executor** runs the plan and
returns a report (timings, instrument readings, faults). Three implementations of the same interface:
a Python stand-in now (computes timings, applies the fault rules, takes readings from the virtual lab), a Gazebo adapter later,
real hardware later. Each executor declares which actions it supports; an unsupported plan is refused with a plain message.
The simulator and the decision engine never know which executor ran. Plan times must add up to the setup's step times (within 1 second).
**The plan is intent only; the executed timeline is what the executor returns** (actual times, outcomes, faults, recovery actions).
**Platform fault timing comes from the executor and will not match the PoC's rule** (the PoC charges a whole step plus a purge plus a
whole step; the platform charges what the recovery actions cost). The PoC and `main` keep the PoC's rule. The planner includes
friability steps only when the setup needs them (an objective on friability, or a required constraint on it).

## 7. 3D replay viewer
One self-contained HTML file with the layout and the **executed timelines** embedded and the 3D library and font bundled. Each of the
ten action types maps to a stock animation; the timeline's actual times drive the clock and its readings supply the numbers, so the
viewer never computes a result. Recovery actions are drawn like any other action and marked. It accepts URL parameters (trial, moment) so a headless Chrome screenshot can check it. If WebGL is unavailable it says so.

## 8. How models are validated (applies to every modelling stage)
- **Validation leaves out whole batches, whole suppliers and later dates. It never leaves out random rows.** Random rows would
  leak information (replicates and batch effects sit on both sides of the split) and flatter the model.
  Three hold-out types: whole batches held out together; whole suppliers held out (train on A and B, test on C, and so on);
  later dates held out (train on earlier, test on later).
- **The mock files are never used to tune a model.** They are used to develop and test reading and checking data. Models are
  tested on freshly generated seeds (the generator's truth file allows scoring).
- **An independent second test lab** (see Stage A below) is used only for final acceptance of the model and decision engine.

## 9. Stages
Every stage ends with a plain-language health check you can double-click and a git commit on `platform-build`. Every stage also
re-runs the five existing PoC checks, plus all earlier platform checks. Nothing existing is changed or deleted without asking.

| Stage | What is built | How you verify it without reading code |
|---|---|---|
| **1. Setup app, validation, launcher** **(DONE, tag `stage1-complete`)** | Setup wizard; shared validation module (schemas plus cross-field rules) with plain messages; save/load setup file (safe YAML, relative paths only); converter to PoC settings; `run.bat` offering the setup app and the dashboard | Open the setup app, load the example, break a field, read the message; the check tries many bad inputs. As built: `check_platform1.bat` and `check_all.bat`; see "Stage 1 as built" below |
| **2. Data ingestion** **(DONE: 2a settings, 2b reading layer, 2c cleaning, 2d replicates/failed runs/joins, 2e quality report; see "Stage 2 as built" below)** | Read the experiment table (a byte-order mark and either line ending accepted); map columns using the setup's `data:` section; convert units (N divided by 9.807 to kP); handle "<0.05", missing, failed runs, replicates, dates and batches; plain data-quality report | Load easy, hard and small; the report's counts match a separate recount (for example easy: 3,672 rows, 145 failed, 54 in newtons, 674 below-detection); broken copies give clear messages |
| **3a. Data preparation, candidate models, grouped validation** **(DONE, tag `stage3a-complete`: 3a-1 modelling table, 3a-2 grouped splitters, 3a-3 models, 3a-4 full comparison; see "Stage 3a as built" below; decisions in `docs/decisions.md`, "Stage 3a")** | A modelling table with leakage rules; grouped splitters holding out whole batches, whole suppliers and later dates (never random rows); two baselines and the candidate models (linear and quadratic ridge, boosted trees with conformal ranges, random forest, a neural-network ensemble, a Gaussian process and a joint one); a fixed selection rule; the full comparison | A fold map and a report per table and `model_summary_full.md`; `check_models.bat` (86 checks) scores models on a freshly generated mock seed against the generator's truth and plants random and backwards-in-time splits to confirm they are caught |
| **3b. Calibration, applicability-domain warning, decision-usefulness replay, scorecard** **(DONE, tag `stage3b-complete`: 3b-1 calibration, 3b-2 the warning with four separate statuses including a group-level one, 3b-3 the replay on the synthetic mocks only, 3b-4 the scorecard; see "Stage 3b as built" below; decisions in `docs/decisions.md`, "Stage 3b")** | A rule, fixed in advance, for which results are strong enough to carry; calibration of each model's stated 90% range; a warning when a recipe or a whole group is far from the data; a replay asking whether ranking recipes by a model would have chosen better than chance using only earlier data; one offline scorecard page per table plus an index | `run_scorecard.bat` opens the pages; `check_calibration.bat` (27 checks), `check_domain.bat` (38), `check_replay.bat` (43) and `check_scorecard.bat` (39) test the guards on known answers |
| **4. Decision engine upgrade** **(IN PROGRESS: plan approved 2026-10-11 with stops after each step: 4-1 the engine's brief, 4-2 the richer development lab and 4-3 the engine policy (all five rules) approved; 4-4 development comparison RUN on 2026-10-12 and awaiting review at the 4-4 stop (result: the governed engine beat random recipes in all four scenarios but did worse than the same models without governance in all four; see `docs/decisions.md`, "Stage 4-4 results"); 4-5 acceptance runner and one acceptance run NOT started and gated (never run without your written confirmation of its design). A seed guard now makes the code refuse any sealed acceptance seed outside the official runner, including in the engine classes themselves (fingerprints updated 2026-10-12). After the 4-4 review (`docs/decisions.md`, "Stage 4 follow-up"): Finding A (the period-shift step was too mild) was calibrated on development seeds and stopped at its pre-registered rule (no step size was both harsh enough and still winnable); Finding B (the staleness watch) is only partly supported and nothing in the watch is changed; the period_shift v2 comparison has NOT been run (seeds 10300 to 10339 are reserved and unused); Finding A is closed as a finding about the lab; a change to the all-stale exploration rule was tested on seeds 11000 to 11039 and NOT adopted (it missed its pre-registered bar by 0.08); a separately pre-registered second test with twice the sample on seeds 11100 to 11179 also missed (+5.11, interval +4.42 to +5.80, against a lower-end bar of +5) and the investigation of that change stopped there, so the 4-4 governed engine stands. Rule 5's design (the watch) is untouched in the engine. A recalibration response to a stale target (a new test-arm class, not the platform engine) was proposed, approved, built and checked, but its reshaped-shift scenario could not be calibrated to a qualifying size (no size met all four pre-registered conditions), so the two-scenario test did not run; the partial test (period_shift and the three no-harm scenarios, seeds 11400 to 11479) was run once and met P1, P3 and P4 (R minus the current engine in period_shift +12.22, interval +11.26 to +13.16; no harm shown elsewhere), with the verdict that R fixes the offset-shift problem it was designed for but is NOT shown to be a general fix for rule 5; R was then ADOPTED (2026-10-12) as the platform engine's rule 5 response under the exact scope recorded in docs/decisions.md, "Adoption of R", and recalibrated.py joined the engine lock; the reshaped scenario is closed. See "Stage 4 as it now stands" in docs/decisions.md for the full picture; 4-5 is not started and stays gated. The policy constants are fixed in `docs/decisions.md`, "Stage 4". The engine imports only `cellpoc.modelling.models` and `cellpoc.modelling.domain` from the modelling part, one direction.)** **(Former blocker RESOLVED 2026-10-11: the sealed acceptance lab now exists in `acceptance/` and is sealed, fingerprints in `docs/decisions.md`. Nothing in Stage 4 may import, open or run it except the dedicated acceptance runner; `check_seal.bat` enforces this. See "Stage A" below.)** | Engine uses the selected model; handles process factors, sum-to-100, several targets; richer development test lab built from the generator's formula with fresh seeds; first acceptance run on the sealed lab | The old 40-campaign comparison is unchanged; a new comparison on the richer lab; the engine still cannot import the lab's truth (guard) |
| **5. Configurable cell simulator** **(DONE 2026-10-13, built after Stage 6; `check_cellsim.bat`, 21 checks; see docs/decisions.md "Stages 5 to 8 as built")** | Steps, stations, timings, calendar and faults (scripted and random) come from the setup file; fault timing is taken from the executor, not from the PoC's rule | Change a timing or fault in the setup; the trial count moves as a separate recount predicts; PoC checks still pass |
| **6. Cell executor and motion plan** **(DONE 2026-10-13; `check_planner.bat` 21 checks, `check_executor.bat` 20 checks)** | Planner that **generates** plans (replacing the hand-authored examples) and must pass the same format checks, including the friability rule, wait reasons and step totals within 1 second; executor interface; Python stand-in producing executed timelines; plan validation (picks match places, no overlaps) | The check reports those rules in plain words; you open a plan and its generated story and read them |
| **7. 3D replay viewer** **(DONE 2026-10-13; `check_viewer.bat`, 24 checks with real headless Chrome; the by-eye checklist is only needed if Chrome is not installed)** | Data-driven, offline, no logic, replays the executed timeline; URL parameters for trial and moment | Automated: opens offline, consumes every action, **headless Chrome screenshot check** at chosen moments (trial 8 jam, trial 19 skip) with software rendering; if it fails on a machine, a short by-eye checklist replaces it |
| **7b. Visual verification layer (ROADMAP ITEM, PROPOSED 2026-10-13: not approved, not started, nothing built; see "Roadmap item 7b" below the table)** | Fiducial tags (ArUco) on each bottle plus an off-the-shelf pretrained detector, as a check on the fixed-position design: is the right bottle in the right place, upright, and is anything unexpected in the cell. No custom model training. Full custom-trained vision is a separate initiative and is NOT part of this item | Nothing yet. If approved, a check would run the detection on staged or rendered images with known faults and report the misses in plain words |
| **8. Dashboard integration** **(DONE 2026-10-13; `check_dashboard.bat`, 30 checks; the platform pages appear only for a platform record, the proof of concept's six pages are unchanged and compared with a recording made before the change; `run_platform.bat` opens the dashboard on a platform run)** | New "3D replay" tab and "Data and model" tab; record v2 fields; guard unchanged | Streamlit test harness plus checklist; the no-logic guard still passes |
| **9. Reports and exports** **(DONE 2026-10-13; `check_reports.bat`; the PDF is printed by an installed browser, no new library; all files in the Deloitte look)** | PDF, Excel and CSV exports: what was run, data quality, model scorecard, results, limitations; all labelled illustrative or synthetic | Open the files; numbers match the run record; labels present |
| **10. Hardening** **(DONE 2026-10-13 except the second acceptance run, which is gated: see docs/guides/acceptance_runner_design.md; `check_hardening.bat`)** | Bad-file handling, performance, paths with spaces, clean-folder install test, no-network check, documentation; second acceptance run | A "break it on purpose" list; a fresh-copy test; all checks pass |
| **11. One unified app (IN PROGRESS, approved 2026-10-13 stage by stage, stop and review after each: Stages A, B and C DONE, D not started; `check_app.bat`)** | One app on one address with a left menu (Overview, Setup, The run, Live run, 3D replay, Data and model, Reports, About and limits) in a dark Deloitte look. **Stage A (done):** the shell, the menu, the dark look and an Overview whose numbers are recounted independently by the check; the dashboard's pages hosted unchanged; Setup and Live run are signposts. **Stage B (done 2026-10-14):** the setup app's ten screens drawn inside the app (one small, behaviour-preserving refactor of `setup_app/app.py`; the stand-alone app is unchanged, proved by a fingerprint recorded before the edit). **Stage C (done 2026-10-14):** the live view inside the app, started and stopped by a supervisor (a separate program on port 8514, on this computer only; design note `docs/stage_c_design_note.md`), after the live server's controls were protected (step C0). **Stage D:** polish and one launcher. The existing apps and launchers stay as they are | `run_app.bat` (http://localhost:8510, this computer only; `connected` on 8511); `check_app.bat` |

### Roadmap item 7b: a visual verification layer (PROPOSED 2026-10-13; not approved, not started; illustrative)
**Status:** a proposal only. Nothing is built, no library is added, no existing behaviour or check changes. Building any of it needs your written approval, and a new library needs approval of its own (Stage rules in `CLAUDE.md`).

**The idea in plain words.** The cell is designed around fixed positions: every bottle sits in a known slot and the plan says where each one goes next. Today the only things that can notice something has gone wrong are the instrument readings (the balance, the gauge). This item adds a second pair of eyes. A printed square pattern (an **ArUco tag**, a black-and-white code that a computer can read from a photograph) goes on each bottle, each with its own number, so "bottle V-008" is a tag the camera can find. A fixed camera looks at each station. The software then asks one simple question: *is what the camera sees the same as what the plan says should be there?* An off-the-shelf **pretrained object detector** (one that was trained by someone else on everyday photographs and is used exactly as it comes) can add a rough "is anything else in the work area?" look. **No model is trained by this project.** Reading a tag is a fixed geometric procedure, not a learned model, and the detector's settings would be fixed in advance.

**What it would catch** (each is a mismatch between what is seen and what the plan expects):
- a bottle that is **missing** from its slot;
- the **wrong bottle** in a slot (the tag number does not match the plan), which matters in a formulation because it would be the wrong ingredient;
- a bottle **knocked over or tilted** (the tag's angle is outside a tolerance);
- a bottle that is **not where the plan says it should be** after a move;
- something **unexpected in the work area** (the pretrained detector, as a rough extra; it is not trained on laboratory bottles or a pill press, so how well it does here is unknown until tested);
- **"cannot verify"**: a tag hidden, dirty, or washed out by glare is reported as unverified, never as fine.

**What it would not catch:**
- **How much** is in a bottle or was dispensed. The balance already measures that far better, and the platform already shows its reading (for example the 0.20 g reading at the binder jam). Estimating quantity from a picture is custom vision and is outside this item.
- **What is inside** a bottle. A tag says which bottle it is, not what was put in it; a correct tag on a wrongly filled bottle looks fine.
- Powder jams or spills inside the dispenser, tablet quality, dissolution, hardness or friability (the instruments and the virtual lab own those).
- Whether a grasp was good, beyond "the bottle is where it should be afterwards".
- A tag stuck on the wrong bottle by a person.

**How it would fit the existing design, if approved.** It would be a new, separate verification step beside the executor, reading the expected state from the plan and the executed timeline and writing its answer (**ok / mismatch / cannot verify**) into the executed timeline as an extra reading, with new fault causes (bottle missing, bottle knocked over, wrong bottle) that use the existing alert and recovery path. The decision engine would never see a picture, only the alert. The dashboard and the 3D replay would only display what was recorded and calculate nothing. The architecture check would list the new part and what it may import.

**What a simulation can and cannot show here (stated now so it is not overstated later).** With no real camera, the verdict of a "simulated detector" would be invented by us, which proves nothing. The honest options are: (1) **rendered images**, pictures made from the 3D layout with tags drawn on the bottles, run through the real tag reader; this tests the software path and the logic for known faults, and says nothing about real lighting, lenses or print quality; and (2) **a real camera** with staged faults (a bottle removed, swapped and knocked over) to measure what is really caught and missed. Either way there is no training, but there is still **testing**, and testing needs pictures of each fault.

**What it would need.** One fixed camera per station or view, with a mount and steady lighting; camera calibration with a printed pattern; printed matte tags and a rule for where they go on each bottle; one new library (OpenCV, whose tag reader is built in; whether it installs on this project's Python 3.14 has NOT been checked, and that check comes first, as it did for scikit-learn); and a detector chosen with its licence read first (some popular detector packages carry licences that may not suit client work). No claim is made about accuracy. The figure that matters, how often it misses or raises a false alarm, is only known after a staged test.

**Separate initiative, recorded on purpose: full custom-trained vision.** Estimating how much is in a bottle from a picture, predicting how to grasp an object, or any model trained on this project's own images is **not** part of item 7b and is **not promised by it**. It is a separate, resourced initiative that would need **(1) a camera, (2) real or synthetic labelled image data, and (3) someone with computer-vision expertise.** **None of the three currently exists on the team.** This is the same kind of gap as the two already named for this project, the **formulation scientist** (no one on the team yet judges whether the recipes, targets and results make scientific sense) and the **robotics engineer** (no one yet judges whether the cell design would work on real hardware). Until those people and that data exist, the platform should not claim any custom vision capability. (Note, 2026-10-13: the formulation-scientist and robotics-engineer gaps were stated by the project owner and are written down here for the first time; no earlier entry for them was found in the project documents.)

**What this item does not do, whatever is built.** It does not test real hardware, and it does not make any claim about real tablets or a real robot. Everything it produced in this project would be labelled illustrative until real hardware, real data and expert review exist.

### Stage 1 as built (what was added, and what changed from the plan)
Details and reasons are in `docs/decisions.md` ("Stage 1"). In short:
- **Shared checker** in `cellpoc/setup/`: 99 plain-English messages, each with a test; `docs/setup_messages.md` is generated from them. Setups carry a
  `format_version` (older ones load, newer ones are refused) and saved setups record time, program version and a content fingerprint, never a name.
- **Setup app** in `cellpoc/setup_app/`: ten screens, labelled Error / Warning / Note messages beside each field and again on Review, Save switched off
  while errors remain (files go only into the git-ignored `setups/`), offline, project accent colour and font, "illustrative" banner on every screen.
  It calculates nothing. `docs/setup_app.md` has the by-eye checklist for what the automated test cannot see.
- **Converter** to the proof of concept's settings is a preview only and never writes `config/settings.yaml`.
- **Launcher**: `run.bat` menu (dashboard 8501, setup app 8502, both). `check_all.bat` runs every check and prints one table.
- **Changed from the plan:** schemas and four example files moved into `cellpoc/formats/` (four files, not two); Streamlit pages *can* be screenshotted in
  headless Chrome with a long virtual wait (the earlier note said they could not); the setup app listens on this computer only (the dashboard is unchanged);
  `requirements.lock.txt` added; public real datasets for later stages are recorded in `data/public/SOURCES.md` (data git-ignored).
- **Unchanged:** the proof of concept, its five checks (each gained one architecture line) and the dashboard.

### Stage 2 as built (what was added, and what changed from the plan)
Details and reasons are in `docs/decisions.md` ("Stage 2"). In short:
- **Reading** (`cellpoc/ingest/`): CSV, text and Excel `.xlsx` (needs `openpyxl`, approved); byte-order marks, three kinds of line ending, UTF-16, semicolon / tab / comma files, odd column-name spacing, blank rows. Unsafe files (macro or old Excel, oversized, binary) are refused; formulas are never evaluated. 88 messages, each tested (`docs/ingest_messages.md`).
- **Cleaning:** numbers, missing values (only what the setup lists), below-detection rules, hardness conversions (kg/cm2 marked assumed), dates exactly as the setup says (English and Slovenian month names, 2-digit-year rule stated everywhere it is used), mg amounts to a percentage of the total weight with the exact gap kept per row and flagged beyond 2%.
- **Rows:** failed runs set aside with statistics; replicates combined with their scatter kept for noise estimates; left joins on key columns; every row accounted for, and dropped rows are a warning.
- **Quality report:** one Markdown document per file set, labelled with its data status, opening with the row-accounting block, with every assumption written out (`make_example_reports.bat`).
- **Checks:** `check_ingest.bat` (106 checks, in `check_all.bat`): independent recounts on the mock files, freshly generated mock files and the real public data; 200 random file damages through reading and cleaning; random tables for the row accounting; the generated reports themselves.
- **Changed from the plan:** the setup's data section gained optional settings and the other parts became optional (format version stays 1); `Excel` and `pandas` added as approved; a real inconsistency in the public data (batch size of product codes 14 and 16 differs tenfold between two files) is recorded, not changed; the setup app's Data screen does not yet show the new settings (they can be edited in the setup file).
- **Not part of Stage 2:** modelling (Stage 3), and turning the cleaned table into the engine's input (Stage 4).

### Stage 3a as built (what was added, and what changed from the plan)
Details and reasons are in `docs/decisions.md` ("Stage 3a"). In short:
- **Modelling table** (`cellpoc/modelling/`): which rows and inputs each result uses, with every exclusion recorded and nothing filled in. Leakage rules: a calculated column and the columns it comes from never predict each other, an input that copies a result (correlation 0.999 or more) is left out, and the balance ingredient is not an input.
- **Grouped splitters** (`splits.py`, the only place rows are divided): whole batches in 5 folds, whole suppliers (one at a time up to 10), later dates in 4 forward steps; every plan is checked by an independent route; no random splitter exists anywhere in the modelling code (a scan enforces it).
- **Real data, kept honest:** the batch data's supplier split is `api_code`, always written "proxy, not a confirmed supplier"; the batch data has a **main comparison (977 batches)** and an **exploratory one (633 batches, labelled EXPLORATORY in every heading, nothing chosen from it)**; the literature table is **robustness only** (leave whole APIs out; no learning-accuracy claim).
- **Models:** training-mean and nearest-neighbour baselines; linear and quadratic ridge (penalty chosen on whole groups inside each training fold); boosted trees with conformal ranges; random forest; a 5-member neural-network ensemble; a two-stage Gaussian process and a joint Gaussian process (the only model fitted jointly across results; every report says so). A model is chosen only if it beats both baselines in every hold-out type; ties within 5% go to the simpler model.
- **Full comparison:** 9 min 16 s with 6 folds at a time, resumable (`runs/modelling/cache_full/`). Findings: on the synthetic mocks every model beats the baselines; on the real batch data hardness and tensile strength are predicted well, dissolution and yield barely; on the literature table no model beats the training mean.
- **Changed from the plan:** a linear regression was added beside the quadratic one; both choose their penalty by validation inside each training fold (the quadratic had failed badly on the real tables); the plan's runtime estimate of about 3 hours was replaced by the measured 9 to 16 minutes; only scikit-learn was added as a library (statsmodels stays out). The 47 modelling messages are listed in `docs/modelling_messages.md`.

### Stage 3b as built (what was added, and what changed from the plan)
Details and reasons are in `docs/decisions.md` ("Stage 3b"). In short:
- **3b-1 carry rule and calibration:** a result is carried if its chosen model beats both baselines everywhere and its worst error is at most 0.70 of the spread; 0.70 to 0.80 is carried but exploratory; anything else is not assessed and gets no number. Seven results are carried (three on the easy mock, two on the hard mock, real batch hardness and tensile strength, which are one finding), one is exploratory (hard mock dissolution). The stated 90% ranges are checked on held-out groups; a recalibration factor learned only from the other folds fixes uniform over-confidence but does not transfer reliably to a new supplier or a later month.
- **3b-2 applicability-domain warning:** four separate statuses and no combined flag: (1) per recipe, distance to the nearest training rows; (2) per recipe, a numeric input out of range; (3) per recipe, an unseen supplier or product (named); (4) whole group, is this batch, supplier or time period unfamiliar. No model's own range tracks its own error, so this is the platform's main safeguard. It works for batch-level variation and is weak for a new supplier or a later period; the group warning falls back to "chance alone" below 10 training groups.
- **3b-3 decision-usefulness replay:** synthetic mocks only (the real data has no client-specified target, so no window is ever invented): the top 10% of each forward step, ranked by the model's own probability of meeting the targets, compared with random and with the perfect ranking, with an error bar. Friability is met by over 99% of mock recipes, so it gets "no room to improve", not a verdict.
- **3b-4 scorecard:** one stand-alone offline page per table plus an index (`run_scorecard.bat`). Carried, carried-but-exploratory and not-assessed results each have their own look, and so do the four readings of the warning per kind of shift ("picks out the large errors", "mixed", "cannot be judged", "does not"); only the first is reliable, and a reading is worked out for each result separately and never averaged.
- **The one finding behind three results (your statement, on every page):** everything built so far recognizes batch-level variation well, but struggles specifically when the shift is a new supplier or a later time period.
- **Known limitation of the test data itself:** the mock generator's supplier effect barely touches the recipe inputs (at most 0.2% of an input's spread, against 86% on the real data) and the recipes do not drift with the date, so the mocks cannot validate the distance check under a supplier shift or input drift; "cannot be judged" there is a gap in the test design, not a passing result. Not fixed.
- **Changed from the plan:** the replay is mocks-only (not on real batch hardness and tensile); the scorecard is a page per table plus an index, not one page; of four options for the warning's weakness under supplier and date shifts, two were built (separate statuses, a group-level warning), one declined (a looser range check, as after-the-fact tuning) and one deferred (distance on the most influential inputs only).

**Stage A (sealed acceptance lab) - CREATED AND SEALED on 2026-10-11 (tag `sealed-lab-v1`).** The plan was to write it once, **before** modelling work began. **That timing was not kept:** it was written after Stages 3a and 3b, which were built and tested on the synthetic mocks and the public data only. Nothing in Stage 3 needed it, and nothing in Stage 3 could have been tuned to it (it did not exist), but it was written by the assistant that knew the Stage 3 findings, so its design properties were fixed in writing before it was first tested. It lives in `acceptance/`: `sealed_lab.py` (a mechanism-style dissolution curve, a Ryshkewitch hardness law, a friability that is a real constraint, batch and supplier effects on latent parameters, and a history generator in which the supplier and the date move the recipes), its `README.md` (what sealed means, precisely), `SEAL.json` and the append-only `LEDGER.md`. Its fingerprints are recorded in `docs/decisions.md` ("The sealed acceptance lab"); `check_seal.bat` verifies them, scans the whole project for any import, open or mention of the lab, and reads the ledger; it is run only by a dedicated acceptance runner (to be written in Stage 4, inside `acceptance/`), at the end of Stage 4 and again in Stage 10, each run entered in the ledger. If it is ever opened for debugging, that is recorded and a new sealed lab is written.

## 10. Decisions from the format review (recorded in `docs/decisions.md`)
Fourteen decisions were taken after the example files were reviewed, and the review's eight open points were answered.
- **Fourteen decisions:** the ten-name action vocabulary; two files (plan = intent, executed timeline = what happened, with `planned` / `recovery` origins);
  a `step` on every action and a `trial_start_minute` in the header, with step totals within 1 second; one ID per quantity with its unit in the name and
  lowercase phases (`docs/naming.md`); `data_status` values synthetic, illustrative, real, validated, and a record takes its weakest input; `batch_size_g`;
  targets split into constraints and objectives; structured fault `where` and documented probabilities; a `data:` section in the setup and tolerant
  reading of a BOM and Windows line endings; layout object list, tool positions, shoulder height, link lengths and a 3D reach check; machine-readable schemas,
  safe YAML reading and relative-only file references; BOM-free CSV with a companion `.meta.json` and a messy example; a complete run record with null
  model numbers; and a permanent `check_formats.bat`.
- **Eight answers:** (1) `data_status` order is synthetic, illustrative, real, validated, weakest to strongest; (2) the planner includes friability steps
  only when the setup needs them; (3) platform fault timing comes from the executor and will not match the PoC's; (4) reach policy: warn below 0.10 m of spare
  reach, fail below 0.03 m; (5) every wait names the real process it stands for; (6) the example files are hand-authored until Stage 6;
  (7) the trial-8 story is generated by script and checked against the timeline; (8) BOM and CRLF tolerance is a Stage 2 requirement, already proven in the format check.
