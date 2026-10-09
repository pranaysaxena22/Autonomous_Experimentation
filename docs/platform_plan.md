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

**Libraries on Python 3.14.6 (checked by dry run; nothing installed; not yet run).** Installers exist for scikit-learn 1.9.1,
scipy 1.18.1, statsmodels 0.15.0, openpyxl 3.1.5, reportlab 5.0.1 (also xgboost 3.4.1, lightgbm 4.7.0, shap 0.53.0, optuna 5.0.0).
Plan to use only scikit-learn, scipy and statsmodels for modelling (openpyxl for Excel, reportlab for PDF). No torch or
tensorflow (not needed for a few thousand tabular rows; tensorflow is only a release candidate). The modelling stage begins with
an install-and-import test in a scratch copy of the environment.

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
moment to show as a URL parameter. Streamlit pages did not render in a headless screenshot (they need a live session), so the
dashboard and setup app are checked by Streamlit's test harness plus a checklist by eye.

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
| **1. Setup app, validation, launcher** | Setup wizard; shared validation module (schemas plus cross-field rules) with plain messages; save/load setup file (safe YAML, relative paths only); converter to PoC settings; `run.bat` offering the setup app and the dashboard | Open the setup app, load the example, break a field, read the message; the check tries many bad inputs |
| **2. Data ingestion** | Read the experiment table (a byte-order mark and either line ending accepted); map columns using the setup's `data:` section; convert units (N divided by 9.807 to kP); handle "<0.05", missing, failed runs, replicates, dates and batches; plain data-quality report | Load easy, hard and small; the report's counts match a separate recount (for example easy: 3,672 rows, 145 failed, 54 in newtons, 674 below-detection); broken copies give clear messages |
| **3a. Data preparation, candidate models, grouped validation** | Cleaning pipeline; candidate models (quadratic regression, Gaussian process, gradient boosting from scikit-learn); validation holding out whole batches, suppliers and later dates | A plain report per hold-out type; the check scores models on freshly generated seeds; confirms no random-row splits exist |
| **3b. Uncertainty calibration, applicability-domain warning, scorecard, decision-usefulness replay** | Calibrated "how sure" ranges; a warning when a recipe is far from the data; a one-page scorecard; a replay of history asking whether the engine, using only earlier data, would have pointed at good recipes | Open the scorecard; the check tests that stated 90% ranges cover about 90% on held-out groups, that far-away recipes are flagged, and that the replay uses only data from before each decision |
| **4. Decision engine upgrade** | Engine uses the selected model; handles process factors, sum-to-100, several targets; richer development test lab built from the generator's formula with fresh seeds; first acceptance run on the sealed lab | The old 40-campaign comparison is unchanged; a new comparison on the richer lab; the engine still cannot import the lab's truth (guard) |
| **5. Configurable cell simulator** | Steps, stations, timings, calendar and faults (scripted and random) come from the setup file; fault timing is taken from the executor, not from the PoC's rule | Change a timing or fault in the setup; the trial count moves as a separate recount predicts; PoC checks still pass |
| **6. Cell executor and motion plan** | Planner that **generates** plans (replacing the hand-authored examples) and must pass the same format checks, including the friability rule, wait reasons and step totals within 1 second; executor interface; Python stand-in producing executed timelines; plan validation (picks match places, no overlaps) | The check reports those rules in plain words; you open a plan and its generated story and read them |
| **7. 3D replay viewer** | Data-driven, offline, no logic, replays the executed timeline; URL parameters for trial and moment | Automated: opens offline, consumes every action, **headless Chrome screenshot check** at chosen moments (trial 8 jam, trial 19 skip) with software rendering; if it fails on a machine, a short by-eye checklist replaces it |
| **8. Dashboard integration** | New "3D replay" tab and "Data and model" tab; record v2 fields; guard unchanged | Streamlit test harness plus checklist; the no-logic guard still passes |
| **9. Reports and exports** | PDF, Excel and CSV exports: what was run, data quality, model scorecard, results, limitations; all labelled illustrative or synthetic | Open the files; numbers match the run record; labels present |
| **10. Hardening** | Bad-file handling, performance, paths with spaces, clean-folder install test, no-network check, documentation; second acceptance run | A "break it on purpose" list; a fresh-copy test; all checks pass |

**Stage A (sealed acceptance lab) - timing to confirm.** A second test lab with a structurally different formula from
`tools/make_mock_data.py` (for example a mechanism-style dissolution curve and a different hardness law, different interaction
structure and noise). It is written once, **before** modelling work begins, and sealed: its fingerprint (file hash) is recorded in
`docs/decisions.md`; an automated guard makes sure no development code or check imports it; it is run only by a dedicated
acceptance check (end of Stage 4 and again in Stage 10). If it is ever opened for debugging, that is recorded and a new
sealed lab is written.

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
