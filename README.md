# Cell POC

A simulated autonomous formulation cell (tablet recipes), with a Streamlit dashboard.
**Simulation with illustrative values** - nothing here is real client data.

## Start the apps

Double-click `run.bat`. A small menu asks what to open (type the number and press Enter):

| Type | Opens | Address |
|---|---|---|
| 1 | Results dashboard | http://localhost:8501 |
| 2 | Setup app (describe a study; see `docs\setup_app.md`) | http://localhost:8502 |
| 3 | Both, each in its own black window | both addresses |

`run.bat dashboard` and `run.bat setup` start one directly (from a terminal or a shortcut). Each app keeps its black window open: leave it open,
and close it (or press Ctrl+C in it) to stop the app. If a window says **a port is already in use**, that app is already running in another black
window: close that window, or just use the browser tab that is already open.

If the run record does not exist yet, the dashboard builds it first (about a minute). Everything works fully offline.
`build_demo.bat` rebuilds the record after you change `config\settings.yaml`. See `docs\dashboard.md`.
The setup app can only be opened from this computer. Saved setups go into the `setups` folder (never saved to git).
(The dashboard can currently be opened from other computers on the same network, which is fine on a laptop. If this platform is ever put on a shared server, revisit who may reach each app: see `docs\decisions.md`.)

All tunable numbers are in `config\settings.yaml`. The plain-English description of the scenario is
`docs\scenario.md` (generated from the settings by the checks).

## The platform: run, replay, reports and guides (Stages 5 to 10)

Everything here is **illustrative or synthetic**, runs only on this computer and needs no internet. Showing it to someone? Open `docs\demo_start.html` (double-click): one page that lists the screens in demo order, with a link to each. New to the project? Start with the guides in `docs\guides\` (double-click `make_guides.bat` for branded pages and PDFs): **the demo script**, **the system explained in plain language**, **the work report** and **the design for the sealed acceptance run** (for your review: nothing built, nothing run).

| Double-click | What it does |
|---|---|
| `run_platform.bat` | Builds a platform run from the example setup (a few seconds) and starts the dashboard on it (answering **this computer only**) at http://localhost:8503: the six usual pages plus **3D replay**, **Data and model** and **Reports**. Drag a saved setup file from `setups\` onto it to run that setup instead. |
| `run_app.bat` | **The unified app: start here (illustrative).** A short menu (1 the platform run, 2 the loop connected, 3 both; Enter alone is 1). It builds a platform run, draws the MuJoCo view of it (about two minutes the first time, a second after), and opens one app, on **this computer only**, at http://localhost:8510 with a dark Deloitte look and a left menu in demo order: **Overview** (the idea, the four headline numbers a client remembers, the run in numbers), **Vision** (a picture of the bench in, the coloured liquids out: which solution, how full, where it stands for the arm, whether the arm can reach it; sample scenes, the camera, or a photo; choose the colour rules or a trained model; see `docs/vision.md`), **Results at a glance** (charts made for a client demo: more experiments, learning, working unattended, where good recipes are, faults handled, what "good" means), **Setup** (the setup app's ten screens, drawn inside this app: Stage B), **Live run** (Stage C: press Start the live view on the page and the live view runs inside the app, with the cell drawn by the MuJoCo physics model as it happens, as a separate program on port 8514 on this computer only; Stop ends it and so does closing the app), **The run**, **3D replay**, **Physics (MuJoCo)** (the run played by an arm in a physics model of the cell, with the reach and collision checks), **Data and model**, **Reports** and **About and limits** (the dashboard's own pages, unchanged). `run_app.bat connected` does the same with the loop connected, at http://localhost:8511. The other launchers and dashboards are unchanged. |
| **Setup app: three illustrative examples** (`run.bat`, option 2) | In the left panel, choose an **Illustrative example** and press **Load example**: example 1 is the standard five-day run with two scripted jams (30 trials); example 2 is a week with random faults (about 42 trials); example 3 has demanding targets and a short run (about 24 trials). `?start=example2` and `?start=example3` open the other two directly. |
| **Setup app, last screen: "Save and run it"** (`run.bat`, option 2, http://localhost:8502) | **Run your own setup.** Fill in the setup, go to screen 10 and press **Save and run it**: it saves the file in `setups\` and simulates a run of that saved file in a few seconds, then offers **Open the dashboard on this run** (http://localhost:8506) and **Watch this setup run live** (http://localhost:8504). Change a setting (for example the run window on the Calendar screen) and run again to see the run change. Switched off, with the reason, while the setup has errors or cannot be simulated yet. The run goes in `runs\setup_run\`. |
| `run_platform.bat connected` | **The loop connected.** The experiment table is read and judged (Stage 2 and 3), what Stage 3 concluded becomes the decision engine's brief, and **the adopted Stage 4 engine chooses every recipe, process settings included, from that table and the measurements so far** (about a minute; the first time it may take a few minutes to judge the models). The dashboard opens on it at http://localhost:8505 (so it can be open together with the usual one). Add a scenario if you like: `baseline` (default), `new_supplier` (the engine runs bridging trials when an unseen supplier appears), `period_shift` or `unpredictable_dissolution` (dissolution is not modelled). Everything is the development lab's synthetic world. |
| `run_live.bat connected` | The same loop connected, **live**: watch the engine choose recipes from the data while the cell works. |
| `run_live.bat` | **The live run.** Opens a page at http://localhost:8504 where the simulated cell runs while you watch: the 3D arm moves, the simulated date and time advances, results appear when their tests finish, faults when they strike, and a chart of good recipes grows. Press **Start the run**; choose **which setup to run** from the Setup list at the top (the three illustrative examples, your saved setups, or the loop connected; switching restarts the run); choose a speed (300x means one simulated hour in 12 real seconds, so the whole 5-day run takes about 24 minutes; 7200x is about a minute). It is the same simulation as a normal run, only paced. When it finishes it saves the run to `runs\live\`. Drag a saved setup onto it to run that one. |
| `view_physics.bat` | **The physics view (illustrative).** Writes the cell as a MuJoCo scene (`runs\physics\cell.xml`) and opens it in MuJoCo's own viewer, a separate window on this computer only: the arm, the table and every station at the layout's positions. Drag the joint sliders to move the arm. Nothing else in the project uses it. See `docs/physics_plan.md`. |
| `play_physics.bat` | **The robot working in MuJoCo (illustrative).** Opens MuJoCo's viewer and plays a trial of the run `run_app.bat` built: the arm lifts, glides over each station, picks the vial and the ingredient bottles, tilts them to pour, shakes, presses, stirs and returns everything, with the run's simulated clock and what it is doing printed in the window. By default it plays the first trial with a fault (the binder jam and its recovery). `play_physics.bat 12` plays trial 12; `play_physics.bat 8 gif` writes `runs\physics\trial_8.gif` to send or put in a slide. A separate view: nothing in the run changes. |
| `tools\download_labpics.py`, `tools\train_vision.py` | **The vision model's training (illustrative; needs the internet once).** The first downloads the public LabPics photographs (3 GB, MIT licence) into `data\public\labpics`; the second trains the network on them (about an hour on this computer's processor) and writes `data\vision_models` (weights, a progress file the Vision page shows, a report of its scores). Neither is part of the running app; the app only reads the weights. Run them with `.venv\Scripts\python.exe tools\...`. `tools\pick_bottle_photos.py` (run after the download) cuts five real test photographs, one per solution colour, into `data\public\labpics\demo_bottles`; the live run's vision check and the Vision page use them automatically (a drawn photograph is used if they are missing). **Reading the name on a bottle's sticker:** `tools\download_ocr_models.py` (36 MB, no account) fetches two small text-reading models from OpenCV's collection into `data\vision_models\ocr`; without them a bottle is identified by its barcode alone. **The tablet inspection:** 	ools\download_pharmavision.py (38 MB, no account) fetches the public PharmaVision tablet photographs into data\public\pharmavision (its own licence text was not readable to me; the project owner confirmed it may be used); 	ools\train_tablet.py trains the normal-or-defective network (about six minutes); 	ools\score_tablet.py scores it through the app's own reading path; 	ools\pick_tablet_photos.py cuts twelve test photographs for the live run's tablet check. |
| `make_physics_view.bat` | Draws the MuJoCo view for the app's **Physics (MuJoCo)** page for a saved run (`runs\platform` by default; `make_physics_view.bat runs\setup_run` for another). `run_app.bat` does it for you; a view that is already up to date is not drawn again. |
| `run_app_developer.bat` | The same app as `run_app.bat` in its **developer view**: every page (the finished run moment by moment, the 3D and physics views, the data and models) and the technical detail. `run_app.bat` opens the **client view**, the pages and wording meant for the people the demo is for; it opens with a **welcome window** and a **guided tour** of the eight things to see (start it again any time with *Take the tour* in the left menu; add `?welcome=off` to the address to skip the welcome window). The front page's picture is `static\\cell_hero.jpg` (`tools\\make_hero_image.py` makes it again). |
| `run_console.bat` | **The operations console: the screen to demo.** Opens http://localhost:8504/console in your browser: a welcome window, a guided spotlight tour and three views of the simulated cell at work (**Overview** for leadership and clients, **Operator** for whoever watches the cell, **Lab manager** for alerts, results and logs), with a narrated **Guided demo** (the simulation runs while a caption explains each moment as it happens), play and speed controls, a progress timeline, **Inject event** (arm a wrong bottle, an unreadable barcode, a bottle with no stickers, a mismatched liquid or a defective tablet for the next pick), **Explain** and **About**. Everything is illustrative; the page answers this computer only. Add `?welcome=off` to the address to skip the welcome window. |
| `setup_voice.bat` | One-time set-up of the narrator's clear offline voice (Piper): makes its own small environment and downloads three voice files (about 120 MB each; the only step that uses the internet, and it only downloads). Run it once, before `build_replay.bat`. |
| `build_replay.bat` | **Makes the one file you can send to people**: `runs\replay\Autonomous_Formulation_Cell_replay.html`. It plays the guided demo by itself, with the narrator's voice, in Chrome or Edge, with no program running and no internet (a recorded simulated run, so it is the same every time). Takes a few minutes. `build_replay.bat en_US-lessac-high` (or `en_US-hfc_female-medium`) uses another voice. |
| `run_rules34.bat` | **Rules 3 and 4 diagnosis** (analysis only, approved 2026-10-13): reads the stored 4-4R campaigns (seeds 11500 to 11539), runs no campaign and changes nothing in the engine, and writes `runs\rules34\summary.md`: where the adopted engine's remaining gap to the ungoverned engine sits, by kind of pick and by block of trials, for `period_shift` and `new_supplier`. |
| `make_platform_demo.bat` | Builds a platform run and opens its stand-alone 3D replay page at trial 8's jam. |
| `make_reports.bat` | Writes a branded report page, a PDF (needs Chrome or Edge), an Excel workbook and three CSV tables for the latest run into a `reports` folder next to its record. |
| `make_guides.bat` | Writes the guides as branded pages and PDFs into `runs\guides`. |

Where things are written: `runs\platform\` holds the run record, every trial's plan and executed timeline, the layout, the index, `replay.html` and `reports\` (all generated, not saved in git). The platform pieces are `cellpoc\planner`, `executor`, `platform_cell`, `viewer`, `reports`, `platform_info.py` and `platform_runner.py`; the original proof of concept is untouched (`check_dashboard.bat` proves its six pages render exactly as before).

The checks for these stages are in the table below: `check_planner.bat`, `check_executor.bat`, `check_cellsim.bat`, `check_viewer.bat`, `check_dashboard.bat`, `check_reports.bat` and `check_hardening.bat` (breaks the platform on purpose, tries a clean copy, no network, odd folder names, time limits, documentation).

## Check a stage

Each stage has a health check you can double-click. It prints a PASS/FAIL list in plain words.

| Stage | Double-click | What it covers | Time |
|---|---|---|---|
| 1 | `check_stage1.bat` | settings, scenario page, virtual lab | seconds |
| 2 | `check_stage2.bat` | the cell simulator on a fixed list | seconds |
| 3 | `check_stage3.bat` | adaptive engine, 40-campaign comparison, difficulty table | a few minutes |
| 4 | `check_stage4.bat` | closed-loop run with scripted faults, alerts, overnight summaries | under a minute |
| 5 | `check_stage5.bat` | the dashboard | a few minutes |
| formats | `check_formats.bat` | the file formats, schemas and naming rules | seconds |
| platform 1 | `check_platform1.bat` | the setup rules, setup app and converter (every rule has a test; list in `docs\setup_messages.md`) | under a minute |
| ingest | `check_ingest.bat` | the data reader, cleaning and quality reports (Stage 2): CSV and Excel files, 200 random file damages, the mock and public data files, the generated reports (messages listed in `docs\ingest_messages.md`) | under a minute |
| models | `check_models.bat` | preparing tables for modelling and the model comparison (Stage 3a): leakage rules, the grouped splitters (never random rows), the models on known answers, the selection rule, the reports and their labels (messages listed in `docs\modelling_messages.md`) | about 3 minutes |
| calibration | `check_calibration.bat` | calibration (Stage 3b-1): which results are strong enough to calibrate, hit rates and verdicts on made-up errors with a known answer, the recalibration guard (a fold's scale factor never uses its own answers), the reports | under a minute |
| domain | `check_domain.bat` | the applicability-domain warning (Stage 3b-2): far-away recipes are warned, the threshold uses only training rows and is steady across folds, the reports keep their labels | about a minute |
| replay | `check_replay.bat` | the decision-usefulness replay (Stage 3b-3): a perfect predictor scores perfectly and a useless one scores like chance, a window that could see the future is refused, nothing measured in a window reaches the ranking, it only runs on the synthetic mocks, the reports keep their labels | about a minute |
| scorecard | `check_scorecard.bat` | the model scorecard pages (Stage 3b-4): the reading for each kind of shift is worked out per result and never averaged, each reading and each result status has its own look, labels and fixed sentences are present, pages need no internet | about a minute |
| seal | `check_seal.bat` | the sealed acceptance lab (`acceptance\`, see its README): its files have not changed by one byte, nothing else in the project imports or names it, and its ledger shows it was never opened | seconds |
| brief | `check_brief.bat` | the decision engine's brief (Stage 4-1): it matches what Stage 3 concluded, only a carried result is ever usable, the range factor is a median never below 1, and the engine can reach only the model classes, one direction | about a minute |
| dev lab | `check_devlab.bat` | the development lab (Stage 4-2): it is the mock generator's formula plus friability, a new supplier and a process step; its histories shift the recipes where they should; the engine can never see its truth | under a minute |
| engine | `check_engine.bat` | the governed decision engine (Stage 4-3): a target Stage 3 did not carry never enters a probability, a warned recipe is never an ordinary pick, a new supplier causes exactly three bridging trials, the staleness watch fires exactly where it was fixed, a leak is refused | under a minute |
| comparison | `check_comparison.bat` | the development comparison (Stage 4-4): scoring on the lab's truth, pairing, the statistics, the report's fixed labels, and that the two engine files still match their recorded fingerprints | under a minute |
| seed guard | `check_seedguard.bat` | the code itself refuses a sealed acceptance seed (live 7,000,101 to 7,000,140, retired 7,000,001 to 7,000,040) at every development entry point and in the three strategy classes themselves, and ordinary seeds are not affected | seconds |
| recalibrated | `check_recalibrated.bat` | the recalibrated response to a stale target (R), the rule 5 response adopted as the platform engine's: its evidence classes and correction are exact, it behaves exactly like the 4-4 engine until the watch fires, its safeguards route decisions as written, and the scope statement of the adoption equals the one recorded | under a minute |
| planner | `check_planner.bat` | the motion planner (Stage 6): plans obey every rule (step totals, named waits, picks match places, no overlaps), refusals in plain words | seconds |
| executor | `check_executor.bat` | the cell executor (Stage 6): the hand-authored timeline is reproduced, faults, skips and refusals | seconds |
| cell simulator | `check_cellsim.bat` | the configurable cell simulator (Stage 5): the proof of concept's run with the setup's plan, executor and faults, recounted independently on several setups | under a minute |
| 3D viewer | `check_viewer.bat` | the 3D replay viewer (Stage 7): one self-contained page, offline, no logic of its own, a fault shows; it drives Chrome invisibly | about a minute |
| dashboard | `check_dashboard.bat` | the dashboard with the platform wired in (Stage 8): the platform pages appear only for a platform record and the proof of concept's pages are unchanged | a minute or two |
| reports | `check_reports.bat` | reports and exports (Stage 9): every file says what the run record says, is labelled and uses the Deloitte look | a minute or two |
| run this setup | `check_setup_run.bat` | "Save and run it" on the setup app's last screen: the setup you fill in really drives a simulated run (the example gives 30 trials, a 240-hour window gives 60), it is refused in words when the setup has errors or cannot be simulated yet, and the dashboard and live buttons start the platform's own programs | a minute or two |
| launchers | `check_launchers.bat` | the dashboard `run_platform.bat` starts (both variants) answers this computer only: it runs the launcher for real, reads the addresses the computer is listening on (127.0.0.1 only) and tries the computer's other address (refused); a self-test with the flag removed sees every address and a successful connection | about a minute |
| instruments | `check_instruments.bat` | the barcode scanner and balance drivers against pretend devices (clean, noisy, silent, a different vial, a settling balance, overload...), a barcode fault played through the cell (unreadable then rescanned, unreadable twice, a wrong vial) with its alerts, a pretend real scanner in the executor, the dashboard opening such a run, and proof that every normal run is unchanged | a few minutes |
| physics | `check_physics.bat` | the MuJoCo model of the cell built from the layout: gravity, repeatability, a vial resting on a pad, all 28 reach targets solved by MuJoCo with nothing touched, the spare reach equal to the setup rules' formula, with self-tests that can fail (a slot out of reach, a shorter and a longer arm, a tool through the table); nothing else uses it; and a real trial played with the MuJoCo arm (every action, every object ending where the timeline puts it, nothing touched, the jam and its recovery shown, the run unchanged), with a picture drawn | a minute or two |
| vision | `check_vision.bat` | the Vision page's reader: drawn bench scenes with a known answer (every vessel found, each level within a few percentage points, eight colours told apart, positions for the arm to a few millimetres, the arm's reach judged right, dim, noisy and blurred pictures, a picture with nothing in it, a file that is not a picture), a planted wrong reading is caught, the page draws; nothing else uses it | a few minutes |
| client view | `check_client.bat` | the app as a client sees it: the client menu is the intended one, no developer wording on any page (launcher and file names, document and stage names, technical status lines), the illustrative labelling is intact, the numbers equal the developer view's, with a self-test that the scan can fail | a minute or two |
| console | `check_console.bat` | the operations console: served to this computer only (a wrong host is refused, a control needs its secret), no outside address and no developer wording, the words about the product are the app's own words, every element its script and tour look for exists, and in real Chrome the three views, the camera verdicts (right bottle, defective tablet), the welcome and the tour draw | a few minutes |
| client story | `check_story.bat` | the Results page and the Overview's headline cards, made for a client demo: every number in the saved story equals a recount from the raw run record (planted wrong numbers are caught), the story is written for every saved run, the page draws its four cards and five charts, a run without the summary gets a plain message | a few minutes |
| unified app | `check_app.bat` | the unified app (Stages A to C): the approved menu and every page draws; the hosted pages say exactly what the dashboard's say; "Simulation with illustrative values" appears once per page; the Overview's headline numbers and the top bar's trial count equal a separate recount from the raw run record, with planted wrong numbers proving the comparison can fail; `run_app.bat` (both variants) answers this computer only, with a self-test that removes the flag; Stage B: the stand-alone setup app is exactly as before (a fingerprint of its welcome page and ten screens), the Setup page inside the unified app draws the same screens with the label once, the rules, saving and running work there, and the new web-address routes cannot reach anything the stand-alone app's addresses cannot; Stage C: the supervisor starts the real live program on 127.0.0.1 only and stops it cleanly, a planted program on 0.0.0.0 (shown reachable first) is detected, killed and refused, one that moves there later is caught on the next refresh, a hard kill of the app leaves no orphan, and in real Chrome on the actual app and Streamlit frame the live page starts a run | several minutes |
| rules 3/4 tool | `check_rules34.bat` | the rules 3/4 diagnosis tool (`run_rules34.bat` runs it): its accounting is exactly right on made-up campaigns worked out by hand, it reads only the stored 4-4R campaigns, runs nothing, and reproduces the 4-4R table before saying anything else | seconds |
| connected loop | `check_connected.bat` | the connected loop: the engine really chooses the recipes from the data file and what Stage 3 concluded (the chain reproduces the Stage 4-2 brief byte for byte, the first recipe equals the engine's own, one result per completed trial and none for a skipped one), and the default platform run is unchanged | a minute or two |
| live run | `check_live.bat` | the live run (its controls obey only the live page itself: refused without the page's secret token or from any other site, shown in real Chrome with an attack page on another site, and still working end to end, also inside a frame with Streamlit's own sandbox attributes): it is exactly the same simulation as a normal run, only paced; nothing appears before its simulated moment; its page shows it as it happens and listens only on this computer; it drives Chrome invisibly | about a minute |
| hardening | `check_hardening.bat` | hardening (Stage 10): bad files, odd folder names, no network, a clean copy, time limits, the documentation | a few minutes |
| **all** | **`check_all.bat`** | all of the above in order, ending with one summary table and the total time | about 20 minutes |

Run them in order the first time: Stage 4 also confirms every generated chart page works with no internet.
Outputs are written under `runs\` (not saved in git). `check_all.bat` is the one to double-click when you only want to know "is everything still fine?".

## Data quality reports (Stage 2)

Double-click `make_example_reports.bat`. It reads the three synthetic mock data files and, if the real public data files are on this computer
(`data\public\`, never in git), the four public ones, and writes one report for each into `runs\ingest\`. Open the `.md` files with any text editor.
Every report starts with its data label (for example "SYNTHETIC DATA" or "REAL PUBLIC DATA, NOT CLIENT DATA"), then a row-accounting block (rows dropped and
failed runs in capitals), then what needs attention, then every assumption written out. See `docs\ingest_messages.md` for every message the reader can show.

## Model comparison (Stage 3a)

Three double-click files (all in the project folder; nothing is uploaded, nothing needs the internet):

| Double-click | What it does | Time |
|---|---|---|
| `make_fold_maps.bat` | writes, for each test table, a plain document showing exactly how it is divided into training and test rows (whole batches, whole suppliers, later dates; never random rows) into `runs\modelling\` | seconds |
| `run_fast_validation.bat` | fits every model on every fold at reduced effort and writes a report per table plus a summary: a first look | about 3 minutes |
| `run_full_validation.bat` | the full comparison at full effort: a report per table plus `model_summary_full.md`. Each fold is saved as it finishes, so if you stop it, running it again carries on where it stopped | about 10 minutes |

Start with `runs\modelling\model_summary_full.md`. It has three separate parts: the main comparisons (the only ones a model is chosen from), exploratory comparisons, and robustness-only tables.
Every report opens with its data label ("SYNTHETIC DATA" or "REAL PUBLIC DATA, NOT CLIENT DATA"). Read `docs\modelling.md` for what the reports mean and what they do not show.

## Calibration (Stage 3b-1)

Double-click `run_calibration.bat` (about 15 seconds once the full comparison above has been run). It asks whether the 90% range each model states is honest, and writes `runs\modelling\calibration_summary.md`
and one report per table. Results are kept in three separate parts: **carried**, **carried but exploratory (borderline)** and **not assessed**; a result no model predicts well enough gets no calibration number.
Read `docs\modelling.md` for what the words mean.

## Applicability-domain warning (Stage 3b-2)

Double-click `run_domain.bat` (about a minute once the full comparison has been run). It asks whether a recipe is far from the data a model learned from, and writes `runs\modelling\domain_summary.md` and one
report per table. This warning is the platform's main safeguard, because the calibration report found that no model's own range tracks its error. It shows four separate warning statuses (distance, numeric range, unseen supplier or product, whole-group) and never one combined flag. Same three parts as calibration: carried, carried but exploratory, not assessed.

## Decision-usefulness replay (Stage 3b-3)

Double-click `run_replay.bat` (about 30 seconds once the full comparison has been run). It asks, on the **synthetic mock data only**, whether ranking recipes by a model's probability of meeting the targets
would have chosen better than chance, using only data from before each decision, and writes `runs\modelling\replay_summary.md` and one report per mock. It compares the top picks with random picking and with the
perfect ranking, with an error bar, and says plainly for which kind of shift (whole batches, whole suppliers, later dates) the warning can be trusted. For real batch hardness and tensile strength it is **not run**
(no client-specified target exists) and the reports say so; no target window is ever invented.

## Model scorecard (Stage 3b-4)

Double-click `run_scorecard.bat` (about a minute once the full comparison has been run; it opens the index in your browser). It writes one stand-alone web page per table plus an index into `runs\scorecard\`; the pages
need no internet. Each page opens with its data-status banner, the unifying statement, and the safeguard panel (the warning is the main safeguard; four separate statuses, no combined flag), then says for each kind
of shift (whole batches, whole suppliers, later dates) whether the per-recipe distance warning can be trusted, then shows the results in three looks: **carried** (solid green bar), **carried but exploratory** (dashed blue,
hatched, labelled) and **not assessed** (dotted grey, with the reason and no number). The four readings also look different: **picks out the large errors** (green, the only reliable one), **mixed** (blue, weak but positive),
**cannot be judged** (dotted, not enough data) and **does not** (dark, clearly negative). Synthetic pages state the limit of the test data itself (the mocks cannot validate the warning under a supplier shift).
Real batch hardness and tensile strength say that the replay was not run because no client-specified target exists.

## The decision engine's brief (Stage 4-1)

Double-click `make_engine_brief.bat` (under a minute once the full comparison has been run). For each table it writes a plain-words page and a data file into `runs\brief\` saying what Stage 3 concluded about each
result: **carried** (the engine may use it to rank recipes), **carried but exploratory** (no model, no decision) or **not assessed** (only ever measured), with the model the Stage 3 rule chose, whether its stated range
is honest, and the factor by which the engine will widen it (never below 1). Start with `runs\brief\brief_summary.md`. Nothing is refitted and no lab is touched.

## The development lab and the governed engine (Stage 4-2 and 4-3)

Double-click `make_dev_scenarios.bat` (about 15 minutes the first time, seconds after that). It writes four synthetic scenario histories from the **development lab** (the mock generator's formula plus friability,
a supplier and date that move the recipes, an unseen supplier, a true process step, and a dissolution surface Stage 3 should not carry) into `runs\devlab\` and shows, in `scenario_summary.md`, what each scenario was
designed to show and what Stage 3 concluded. The **governed decision engine** (`cellpoc\decision_engine\governed.py`) is the engine developed against it: it models only what Stage 3 carried, treats a recipe the warnings
cannot vouch for as exploratory only, runs three bridging trials when a supplier it has never seen appears, and watches its own stated ranges for a collapse. It is checked by `check_engine.bat`; there is no
double-click to run a campaign yet. The sealed acceptance lab in `acceptance\` is never touched by any of this.

The **development comparison** (Stage 4-4) has been run once (480 campaigns, about 19 minutes; `run_dev_comparison.bat` repeats it from the stored campaigns in seconds). Its report is `runs\devcomparison\summary.md`
(synthetic data, not in git). In this lab the governed engine beat random recipes in all four scenarios but did **worse** than the same models without the governance in all four; the period-shift scenario was probably too mild to be a fair test and is not accepted as final; the reasons and the options are in
`docs\decisions.md`, "Stage 4-4 results". It is a development comparison, not a blind test and not a claim about real tablets.

## Running the demo

**The current demo script, covering the whole platform (setup app, dashboard, 3D replay, data and model page, reports, and the honest findings) is `docs\guides\demo_script.md`** (a branded page after `make_guides.bat`). The older notes below describe the original proof-of-concept demo and `docs\demo_walkthrough.md` the Stage 3 demo; some of their "not built yet" remarks are now out of date.

Everything below runs on the presenting laptop alone. **No internet is needed.** The times quoted are for the
default settings and default seed; if you change `config\settings.yaml`, run `build_demo.bat` and the times may move.

### The day before (once)
1. Double-click `build_demo.bat` and wait for "Done" (about a minute or two). This builds the run record the dashboard shows.
2. Double-click `run.bat`. Check the dashboard opens (details below), then close it (see "Closing down").
3. **Rehearse offline:** turn off Wi-Fi / unplug the network, then repeat step 2. It should look exactly the same.
4. Optional but recommended: double-click `check_stage5.bat` (a few minutes). It should end with **ALL GOOD**.
5. Make a backup in case the app misbehaves: the files `runs\stage4\timeline.html`, `runs\stage3\comparison.html` and
   `docs\scenario.md` open without the app (double-click the two .html files; they work offline). They exist after
   `check_stage3.bat` and `check_stage4.bat` have been run once. Copy them to a USB stick.
6. On the laptop: switch off sleep/screen lock, close other programs, and set the browser to full screen (F11) at 100% zoom.

### Starting the demo
1. Double-click **`run.bat`** and type **1** (Results dashboard), then Enter. A second black window opens. **Leave it open: it is the app running.** (If the run record is missing it is built first, about a minute.)
2. After about 10 seconds your browser opens at **http://localhost:8501**. If it does not, open the browser yourself and type that address.
3. Check the top of the page: a green bar reading **"Simulation with illustrative values"**, and under it six tabs. The first tab, "The run", should say **Fri 09 Oct 18:00** and "Nobody is in the lab".

### A suggested walk-through (about 10 minutes)
1. **The run.** Click **Next event** a few times to show the cell working through Dispense, Blend, Press, Test and Clean, with nobody in the lab. Point out the four boxes (Sense, Reason, Act, Adapt: a loop that repeats every trial) and the recipe with its "why this recipe".
2. Drag the slider to **Sat 10 Oct 09:00**: trial 4's result appears, the first recipe to be measured good.
3. Drag to **Sat 10 Oct 22:30**: trial 8's dispenser clog. The Dispense tile turns red ("Purging after binder dispenser clog"). Click Next event until **Sun 11 Oct 00:00**: it recovers by itself.
4. Drag to **Mon 12 Oct 21:30**: trial 19's retry fails and the candidate is skipped. The alert says it is **waiting for staff, queued for Tue 13 Oct 08:00**; the cell cleans and carries on. Step to Tue 08:00 and watch the alert change to "Staff arrived".
5. **Timeline.** Every trial across the run; grey shading is nobody in the lab (darker = weekend). Faults are red/amber, alerts are triangles. The phases-over-time view is open below.
6. **Overnight handovers.** Read one summary aloud: this is what the first person in on Monday or Tuesday gets.
7. **Does learning help?** The adaptive strategy against a fixed list and random recipes over 40 campaigns, and the difficulty table: the advantage is largest when good recipes are rare and disappears when they are common.
8. **Throughput.** Autonomous against manual. Type the client's own manual figure into the box and the multiple updates.
9. **What this shows.** Finish here: it states plainly what the simulation does not show.

### Optional: show the setup app (about 5 minutes)
This is how a client describes their own study. It checks, saves and previews; it calculates no results.
1. Double-click `run.bat` and type **2** (or **3** to have both apps open). The setup app opens at **http://localhost:8502**.
2. Click **Load example**. Point out the green "Simulation with illustrative values" bar, the ten screens in the left list and the count of errors and warnings under each (the example has one warning, on Equipment).
3. On **Ingredients**, change Drug's *Lowest value* to 40. A box starting **Error:** appears right under the field, the left list now says "1 error", and the **Review and save** screen lists the same message grouped under Ingredients.
4. On Review, show that **Save setup** is greyed out while an error remains. Put the value back to 10, then save it (for example as `demo`): the file appears in the `setups` folder.
5. Open **Preview: what the proof of concept would use**: it is labelled "PREVIEW ONLY" and is never written over `config\settings.yaml`.
6. Click **Start blank** to show a fresh setup listing everything still to do. Every message is plain English, listed in `docs\setup_messages.md`.

### Closing down
Close the browser tab. Click each black window and press **Ctrl+C** (or just close the black window). Always close it before starting that app again.

### If the app will not start
| What you see | What to do |
|---|---|
| Black window flashes and closes straight away | Open a terminal in this folder and run `run.bat dashboard` (or `.venv\Scripts\python.exe -m streamlit run app.py`) to see the message. If it says the file is not found or `python` is missing, the environment is missing: follow "Rebuild the environment" below, then try again. |
| Browser does not open | Open it yourself and go to http://localhost:8501 |
| "This site can't be reached" / page never loads | The black window may have closed or still be starting. Wait 20 seconds and refresh (F5). If the black window is gone, double-click `run.bat` again. |
| The window says **"cannot start: port 8501 (or 8502) is already in use"** | That app is already running in another black window, or in a tab you already have open. Close the other black window (or press Ctrl+C in it) and run it again, or simply use the page that is already open. Still stuck: restart the computer. |
| Page says **"There is no run record"** or **"out of date or damaged"** | Double-click `build_demo.bat`, wait for "Done", then refresh the page (F5). This always happens after the program or the settings change. |
| Windows or antivirus asks about network access | It is only talking to itself (localhost). Choose "Private networks" / allow once. Nothing leaves the computer. |
| The page looks half-drawn or buttons do nothing | Press F5 to refresh. If that fails, close the black window and start `run.bat` again. |
| Anything else | Double-click `check_stage5.bat`: it names the part that is failing in plain words. If time is short, use the backup files from the USB stick (`runs\stage4\timeline.html`, `runs\stage3\comparison.html`, `docs\scenario.md`) and present from those. |

## Add a library

Only with the project owner's approval. Then add the package, with its version, to `requirements.txt` (the short list
people read) and refresh the exact list:

    .venv\Scripts\python.exe -m pip install <package>
    .venv\Scripts\python.exe -m pip freeze > requirements.lock.txt

## Rebuild the environment (e.g. on a new machine)

`requirements.txt` is the readable list of what the project uses. `requirements.lock.txt` rebuilds the exact environment
(every package at the exact version the checks were run with). Prefer the lock file:

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.lock.txt

(`pip install -r requirements.txt` also works but may pick newer versions of the packages that the readable list does not pin.)
