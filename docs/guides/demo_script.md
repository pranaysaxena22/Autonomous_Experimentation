# Demo script for the autonomous formulation cell

> **Start with the unified app (2026-10-16).** Double-click `run_app.bat` and press Enter: one app at http://localhost:8510 holds every screen below (Overview, Results at a glance, Setup, The run, Live run, 3D replay, Physics (MuJoCo), Data and model, Reports, About and limits). The ports and launchers named below (8501 to 8506, `run.bat`, `run_platform.bat`, `run_live.bat`) still work on their own. For a client, use the **client demo script** (`client_demo_script`).

**Illustrative. Say this first and let the banners say it again:** everything you will show is a simulation with made-up values. There is no real robot, and nothing says anything about real tablets or a client. Everything runs on this laptop and needs no internet.

## The use case in four lines

- **The problem:** developing a tablet recipe is slow and manual. A scientist makes and tests a few batches a week (we assume 9, an editable assumption), only in working hours, and picks each next recipe by judgement, so labs sit idle nights and weekends and good recipes are found late.
- **The idea:** an autonomous cell that runs trials by itself day and night. It chooses the next recipe from the data and the results so far, recovers from faults on its own, and leaves a plain-language handover for the people who come in next.
- **What we made:** a working simulation of that cell plus the software platform around it: a setup app to describe a study, a data reader and models that say how far to trust them, a decision engine, a planner and executor for the arm, a dashboard, a 3D replay and a live view, and labelled reports.
- **Why a simulation first:** it proves the design and the software end to end before any hardware is bought. A real robot or a robot simulator plugs in later through the same executor interface. Everything is synthetic, and nothing yet says anything about real tablets.

**Two versions below:** the **Short demo** (about 15 minutes, the one to use first) and the **Full demo** (about 40 minutes, every page). Each step of the full demo can stand alone.

## Short demo (15 minutes)

**Before you start (2 minutes):** double-click `run.bat` and type **3** (the dashboard at 8501 and the setup app at 8502), then `run_live.bat` (the live page at 8504) and `run_platform.bat connected` (the connected dashboard at 8505; the first time it can take a few minutes, so do it earlier). Say first: *"Everything is a simulation with made-up values. There is no real robot, and nothing says anything about real tablets."*

| # | Minutes | Open | Do | Say |
|---|---|---|---|---|
| 1 | 2 | Setup app, http://localhost:8502 | Pick **Example 1** in the list, press **Load example**, click through two or three screens, then go to screen 10 | "The study is described in plain words, screen by screen. Mistakes show right beside the field, and Save is greyed out while any error remains." |
| 2 | 2 | Setup app, screen 10 | Press **Save and run it** | "The setup is saved and simulated right now. Thirty trials in a few seconds." |
| 3 | 1 | Setup app, screen 6 (Calendar) | Change the run length from 120 to 240 hours, press **Save and run it** again (tick Replace) | "Change the setup, change the run: now sixty trials. The setup page drives the simulation." |
| 4 | 3 | Live page, http://localhost:8504 | Choose **Example 2** in the **Setup** list, press **Start the run**, set the speed to **1800x** | "Watch it happen. The arm moves, the clock runs, results appear when their tests finish, faults when they strike. Whichever setup you pick is the one that runs." |
| 5 | 2 | Live page | Pause, change the **Camera**, resume | "We can stop and look at any station." |
| 6 | 3 | Connected dashboard, http://localhost:8505, **Data and model** page | Read the first two sections, then open **The run** and click **Next event** | "This is the loop closed: the data file is read, the models are judged, and the decision engine chooses every recipe from that data. The reason for each recipe says how many measured results it chose from." |
| 7 | 1 | Dashboard, **Reports** page (http://localhost:8503) | Click **Report as PDF** | "Everything can be taken away as a labelled report." |
| 8 | 1 | Say it | | "It is a simulation. The engine still loses to simply ignoring the alarm in all four tested scenarios, and its final acceptance test has not been run. Nothing has been tried on real data." |

**If something does not open:** press F5; if a window says a port is already in use, that app is already running in another black window.

## What the files in the live page's Setup list are

The **Setup** list at the top of the live page chooses which setup runs. Nothing is typed: the page only sends the name of a choice.

| Choice in the list | What it is | Where the file is |
|---|---|---|
| **Example 1: a standard five-day run with two scripted jams** | The original illustrative setup: a 120-hour run, jams on trials 8 (recovered) and 19 (not recovered). About 30 trials | `cellpoc\formats\examples\setup_example.yaml` |
| **Example 2: a week with random faults** | A 168-hour run staffed Monday to Friday, with jams by chance instead of on a script. About 42 trials | `cellpoc\formats\examples\setup_example_2_week_random_faults.yaml` |
| **Example 3: demanding targets, a short run** | Stricter targets (dissolution at least 90%, hardness 7 to 9 kP), narrower ingredient ranges, noisier instruments, a 96-hour run. About 24 trials, very few of them good | `cellpoc\formats\examples\setup_example_3_demanding_targets.yaml` |
| **Your saved setup: (a name)** | A setup you saved in the setup app. It appears in the list as soon as it is saved | `setups\(name).yaml` (this computer only, never in git) |
| **The loop connected: baseline, new supplier, period shift, unpredictable dissolution** | Not a setup file. The data file is the development lab's synthetic history; Stage 3 judges the models on it and the Stage 4 engine chooses the recipes. The first time it prepares the models and can take a few minutes | `runs\connected\dev_(scenario).csv` (generated) |

All three examples use the same equipment layout and the same example experiment table; they differ in run length, calendar, faults, targets and ranges. Everything in them is illustrative.

## What each page shows, and how it works

**Setup app (http://localhost:8502)**
- *Shows:* ten screens that describe a study (ingredients, process settings, targets, equipment and timings, calendar, faults, data), with three illustrative examples to start from. Every problem appears in plain words right beside its field.
- *How:* one shared checker validates every field (the same one the health checks use). **Save** writes a file into `setups\`, and **Save and run it** simulates that saved file by starting the platform's own program. The app itself calculates nothing.

**Original dashboard (http://localhost:8501) and the first six pages of the platform dashboard (8503): The run, Timeline, Overnight handovers, Does learning help?, Throughput, What this shows**
- *Shows:* a finished five-day simulated run moment by moment (stations, who is in the lab, the recipe and why it was chosen, the result), the whole run on a timeline, the overnight handovers, how a learning strategy compares with a fixed list and random recipes, and trials per week against a manual baseline.
- *How:* it reads one pre-computed run record file and calculates nothing, except trials per week divided by the manual baseline. A result only appears after its test has finished.

**3D replay (platform dashboard, 8503)**
- *Shows:* the finished run played back in 3D, trial by trial: the arm's actions, the instrument readings, faults and recoveries, with a line per trial of what was planned and what really happened.
- *How:* one self-contained page holds the executed timelines. The viewer only draws what a timeline says (actions, times, readings), so it can invent nothing, and it works offline.

**Data and model (platform dashboard, 8503; connected dashboard, 8505)**
- *Shows:* how the pieces connected in this run, what the data reader found in the data file (every row accounted for), what the modelling step made of it, and what the run does not show.
- *How:* the text is written in advance by the platform's own data reader and modelling code, and stored in the run record. In the connected run it also lists what Stage 3 concluded for each result and how many decisions of each kind the engine made.

**Reports (platform dashboard, 8503)**
- *Shows:* download buttons for the report page, a PDF, an Excel workbook and CSV tables of the trials, events and alerts.
- *How:* the files are written from the same run record the dashboard reads, so every number matches, and each file carries the illustrative label.

**Live run (http://localhost:8504)**
- *Shows:* the simulated cell running while you watch: the 3D arm, the simulated date and time, the current action, results appearing when their tests finish, faults and alerts, an event log, and a growing chart of good recipes. A **Setup** list chooses which setup runs, and there are Start, Pause, speed and camera controls.
- *How:* the simulation runs on its own thread against a clock that you speed up or slow down. Every event waits for its simulated moment before it is published, and the page asks the local server for news about twice a second. It uses the same drawing code as the replay and gives exactly the same trials as a normal run.

**Connected dashboard (http://localhost:8505)**
- *Shows:* the same pages, but the recipes are chosen by the Stage 4 decision engine from the experiment data and what Stage 3 concluded about it.
- *How:* the data file is read, the models are judged only on groups they have not seen, the conclusions become the engine's brief, and the engine chooses each recipe from that data and the measurements so far. The cell then runs those recipes.

**Model scorecard (`run_scorecard.bat`)**
- *Shows:* for each data table, how well each model predicted on data it had not seen, and whether its warnings can be trusted. Results are marked carried, carried but exploratory, or not assessed.
- *How:* models are tested only on whole batches, whole suppliers and later dates, never on random rows, and the pages are written from those saved test results.

**Data quality reports (`make_example_reports.bat`)**
- *Shows:* for each data file, how many rows were read, set aside, combined or kept, every assumption made, and the data's label (synthetic or real public data).
- *How:* the reader counts every row as it cleans the file, and the report checks that the counts add up.

## Full demo

**Length:** about 40 minutes, plus questions.

## Before the audience arrives (10 minutes)

1. Close any old black windows from earlier. Switch off sleep and screen lock. Set the browser to 100% zoom and full screen (F11).
2. Double-click **`build_demo.bat`** only if the folder `runs\demo` does not exist (it takes about a minute).
3. Double-click **`run_platform.bat`**. A black window builds a platform run (a few seconds) and starts the dashboard. **Leave that black window open.** Your browser opens at **http://localhost:8503**. Check that you can see these tabs: *The run, Timeline, Overnight handovers, Does learning help?, Throughput, What this shows, 3D replay, Data and model, Reports*.
4. Double-click **`run.bat`**, type **2** and press Enter: the setup app opens at **http://localhost:8502**. Leave that black window open too.
5. Double-click **`run_platform.bat connected`** for Act 5b (it opens at **http://localhost:8505**; the first time it may take a few minutes). Optional: double-click **`run_live.bat`** if you want the live run ready (it opens at http://localhost:8504), **`run_scorecard.bat`** (it opens the model scorecard index in your browser) and **`make_guides.bat`** (it writes the guides and opens the folder).
6. Rehearse once with Wi-Fi off. It should look exactly the same.

If any window says **a port is already in use**, that app is already running in another black window: close the other window or just use the page that is open.

## Act 1. The story and the one big caveat (3 minutes)

**Say:** "This is a simulated autonomous laboratory for tablet formulation. It runs by itself through nights and weekends: it chooses a recipe, makes the tablets, measures them, learns, and chooses the next recipe. If a bottle jams, it recovers; if it cannot, it skips that recipe and leaves a message for whoever comes in next. We built it as a simulation first, with the software designed so that a real robot, or a robot simulator, can be connected later."

**Point at:** the green bar at the top of the page, "Simulation with illustrative values".

**Say:** "Every page and file is labelled illustrative or synthetic. We make no claim about real tablets."

## Act 2. Describe a study: the setup app (5 minutes) at http://localhost:8502

| Click | Say |
|---|---|
| **Load example**. (There are three illustrative examples in the list above the button: a standard five-day run, a week with random faults, and demanding targets with a short run. Start with the first.) Point at the ten screens on the left and the counts under each | "A client describes their own study screen by screen, in plain words. It checks, saves and previews. It calculates no results." |
| Screen **2. Ingredients**: change Drug's *Lowest value* to **40** | "A plain-English error appears right under the field, and the left list now says one error. Mistakes are caught where they are made." |
| Screen **10. Review and save** | "The same message is listed here, and **Save setup** is greyed out while an error remains. A broken setup cannot be saved." |
| Put the value back to **10**, save it as `demo` | "It saves. The file goes in the setups folder and never into git." |
| **Start blank** | "A fresh setup lists everything still to do." |
| Load the example again, go to screen 10 and press **Save and run it** | "The setup is saved and then simulated, right now: thirty trials in a few seconds. Whatever we set on these screens drives the run." Then go back to screen 6 (Calendar), change the run length from 120 to 240 hours, press **Save and run it** again (tick the Replace box) and show the page now says 60 attempted: "Change the setup, change the run." Press **Open the dashboard on this run** to see it at http://localhost:8506. |

## Act 3. The cell at work: the dashboard (8 minutes) at http://localhost:8503

Click the **The run** tab. (The same six pages exist in the original proof of concept, and they are unchanged.)

| Click | Say |
|---|---|
| Click **Next event** a few times | "The cell works through Dispense, Mix, Press, Test and Clean with nobody in the lab. The four boxes, Sense, Reason, Act and Adapt, repeat for every trial, and every recipe has a plain-language reason." |
| Drag the slider to **Sat 10 Oct 09:00** | "Trial 4's test has just finished: the first recipe measured good. A result never appears before its test has finished." |
| Drag to **Sat 10 Oct 22:15** (or click **Next event** until a fault appears) | "Trial 8: a fault. The binder bottle has jammed at the dispense step. The Dispense tile changes." Then step forward to **Sat 10 Oct 23:20**: "It tapped and shook the bottle, put it back, purged and retried by itself, and carried on. About an hour lost." |
| Drag to **Mon 12 Oct 19:20**, then **20:26** | "Trial 19: the same jam, but the retry failed. The candidate is skipped (no tablets, no result), and an alert is queued for when staff next arrive: **Tue 13 Oct 08:00**." |
| **Timeline** tab | "Every trial across the run. Grey shading is nobody in the lab (darker at the weekend). Faults and skips are marked." |
| **Overnight handovers** tab | Read one aloud. "This is what the first person in on Tuesday gets: what happened while they were away." |
| **Throughput** tab | "Autonomous trials with results per week against a manual baseline of 9, which is an **assumption** you can edit here." Type another number to show it update. |
| **What this shows** tab | "And here is the plain statement of what the simulation does **not** show." |

## Act 4. The 3D replay (5 minutes)

Click the **3D replay** tab. Wait a moment for the picture.

| Do | Say |
|---|---|
| Press **Play** | "This is the cell's arm doing every action of a trial. Nothing in this picture is invented by the viewer: it replays what the executor reported, action by action." |
| Click a numbered chip, for example **8** | "Each chip is a trial. Green is good, grey not good, red skipped, and an amber underline means it recovered from a fault." |
| Pick a **Camera**, for example *balance* or *press* | "Different views of the same trial." |
| With trial **8** chosen, click the action in the list that has a **red mark** (the failed pour), or press **Action ▶** until the **red banner** appears | "A fault, named in plain words, with the balance's reading of how much really arrived." Then go forward to an action with the amber **RECOVERY ACTION** badge: "The recovery is drawn like any other action and marked." |
| Choose chip **19** (red) | "The skipped trial: the retry failed and nothing was pressed." |
| Scroll below the picture to **What happened, trial by trial** | "One line per trial: how many actions were planned, how many ran, how long it took and the result." |

**If the 3D picture does not appear** (an old or locked-down browser): "The page says so plainly, and the list of actions and readings still works." For a larger view, double-click `make_platform_demo.bat`.

## Act 4b. The live run: watch it happen (5 minutes, the showpiece)

The 3D replay above plays back a finished run. This is the cell running **while you watch**. Double-click **`run_live.bat`** (before the audience arrives, or now). Your browser opens at **http://localhost:8504**.

| Do | Say |
|---|---|
| Open the **Setup** list at the top of the page (the three examples, any setup you saved, and the loop connected). Leave it on **Example 1**, or switch to **Example 2** (a week with random faults) to show a different run. | "Whichever setup we choose here is the one that runs. Switching restarts the run." |
| Press **Start the run**. Leave the speed at **300x** | "This is the simulation actually running. One simulated hour passes every 12 seconds. The arm moves as each action happens, and the clock at the top right is the simulated date and time." |
| Point at **Results so far** as a trial's test finishes | "A result appears the moment its test finishes, and not before. The recipe for the next trial is only chosen after that result is in." |
| Watch the strip of numbered chips under the picture | "Each trial is plain while it is in progress. It turns green, grey or red only when its result is published." |
| Choose **1800x** to reach a fault faster (trial 8 is about 28 hours in) | "Faults appear when they strike. The red banner is the fault, the amber badge is the recovery, and the **Faults and alerts** list fills in." |
| Press **Pause**, change the **Camera**, press **Resume** | "You can pause and look at any station." |
| Point at **What is happening** and the **Good recipes so far** chart | "Every line here was published by the simulation at that moment. The chart is the running count of good recipes." |

**Say honestly:** "It is still a simulation, running faster than real time, with a stand-in robot arm. It is the same simulation as the recorded run: if you run it live or in one go, you get exactly the same trials. When it finishes, it saves the run so the dashboard can open it."

**For a short demo, use 3600x or 7200x** (the whole run in two minutes or one), or keep to the recorded replay in Act 4. Press **Restart** to begin again.

## Act 5. Where the data and models fit (4 minutes)

Click the **Data and model** tab.

| Point at | Say |
|---|---|
| **How the pieces connect in this run** | "Setup, decision engine, motion planner, executor, virtual lab, cell simulator, 3D replay. Each does one job, and an automatic check stops one piece reaching into another." |
| **The data file (as the reader found it)** | "The reader accounts for every row: twelve rows read, eight left after four replicate rows were combined, 'the counts add up'. Nothing is dropped silently. The label says synthetic." |
| **What the modelling step made of it** | "Models are tested only on groups they have not seen: whole batches, suppliers, later dates, never random rows. For this tiny example setup no modelling table was built, and it says so plainly." |
| **What this run does not show** | "In this default run the recipes come from the proof of concept's adaptive strategy, and the Stage 4 engine is not used. Act 5b shows the run in which it is." |

If you opened the scorecard page (`run_scorecard.bat`): "These pages show the model results on the mock and public tables, in three looks: carried, carried but exploratory, and not assessed. They say plainly when a model cannot be trusted."

## Act 5b. The loop connected: from the data to the engine to the cell (6 minutes, the point of the platform)

Before the audience arrives, double-click **`run_platform.bat connected`**. It reads the experiment table, judges the models on it (about a minute; the first time a few minutes), and opens the dashboard at **http://localhost:8505**. Open its **Data and model** page.

| Point at | Say |
|---|---|
| **How the pieces connect in this run** | "This time the loop is closed. The data file is read and cleaned, the models are judged on groups they have not seen, and what that concluded becomes the brief the decision engine reads." |
| **The data file** | "3,734 rows, every one accounted for. The label says synthetic: it is the development lab's history." |
| **What the modelling step made of it** | "For each result: carried, meaning the engine may model it, or not assessed, meaning it never does. Here dissolution, hardness and friability are carried, each with the model Stage 3 chose." |
| The line **The engine made 31 decisions** | "How many decisions of each kind: ordinary picks, exploratory ones, bridging trials when a new supplier appears." |
| Go to **The run**, click **Next event** | "Every recipe now comes from the engine, and its reason says how many measured results it chose from: the file's 3,734, growing by one with every new measurement. It also chooses the compression force and the blend time, which the original strategy never did." |
| **3D replay** | "The same cell, now running the engine's recipes." |

**For variety, run a scenario.** `run_platform.bat connected new_supplier` shows the engine running three bridging trials when a supplier it has never seen appears. `run_platform.bat connected unpredictable_dissolution` shows what it does when dissolution cannot be modelled: it searches, and far fewer recipes are good.

**Watch it live:** double-click `run_live.bat connected` (the live page at http://localhost:8504, closing any live page already open first) to watch the engine choose recipes from the data while the cell works.

**Say honestly:** "The data and the lab are the same synthetic world, so this shows the chain works end to end, not that it works on real data. The engine's known weaknesses, including that it loses to simply ignoring the alarm in all four tested scenarios, are listed on the page."

## Act 6. Reports (2 minutes)

Click the **Reports** tab.

**Say:** "Everything on the dashboard can be taken away as files." Click **Report as PDF** and **Excel workbook**. Open each. "Every file carries the illustrative label. The numbers are the dashboard's numbers: the report is written from the same run record."

(If the Reports tab says no files were found, double-click `make_reports.bat`, then refresh the page.)

## Act 7. The honest part (3 minutes)

**Say these plainly. They are part of the strength of the project.**

1. "It is a simulation. There is no real robot. The arm is generic and the numbers are made up."
2. "We built a more advanced decision engine (the one that drives the connected run) and tested it carefully on a development lab. It beats random recipes by a wide margin in every scenario we tried. But it **loses to simply ignoring the alarm** in all four tested scenarios, because of the caution built into two of its rules. We recorded that rather than hide it."
3. "There is a second, sealed laboratory for one final acceptance test. It has **never been run**. It can only be used once, so we wrote a design for it for your review before anyone presses the button."
4. "On real production data, dissolution is hardly predictable from the columns we had. Nothing has been run on client data."

## Act 8. How it connects to a real robot (2 minutes)

**Say:** "The plan for each trial is data. A planner writes it, an **executor** runs it and reports what happened. Today the executor is a Python stand-in. The executor has one fixed interface, plan in and executed timeline out, so a robot simulator such as Gazebo, or real hardware, can be plugged in later. The dashboard, the 3D replay and the reports read the same files either way and need no change."

**If asked "is it connected to Gazebo now?":** "No. It is designed to be, and the interface is built and tested. The connection itself is a later stage."

## Appendix A. Every page, and the one sentence to say about it

Use this when you want to show a particular page, or to walk through the whole system in order. Addresses: setup app http://localhost:8502, original dashboard http://localhost:8501, platform dashboard http://localhost:8503, live run http://localhost:8504.

### Setup app (8502): describe the study

| Screen | Say |
|---|---|
| 1. Project | "The study's name and its data status label: illustrative, synthetic or real. Everything downstream carries that label." |
| 2. Ingredients and constraints | "Ranges for each ingredient and the rule that the recipe sums to 100%. A wrong value shows its error right beside the field." |
| 3. Process settings | "Settings such as compression force and blend time, with their ranges." |
| 4. Targets | "What counts as a good tablet: dissolution and hardness limits (and friability if you ask for it)." |
| 5. Equipment and timings | "The cell layout and how long each step takes. The example has one honest warning about the robot's tightest reach." |
| 6. Calendar | "When the run starts, how long it lasts and when people are in the lab." |
| 7. Faults | "Scripted faults (trial 8 and trial 19 in the example) and random ones." |
| 8. Baseline and comparison | "The manual baseline that the throughput page compares against, and the comparison settings." |
| 9. Data upload and column mapping | "Which file holds the client's past experiments and how its columns map to the study." |
| 10. Review and save | "Every message in one list. Save is greyed out while any error remains." |
| Preview | "What the proof of concept would use. Preview only; it never overwrites the real settings." |

### Original dashboard (8501) and the first six pages of the platform dashboard (8503)

| Page | Say |
|---|---|
| The run | "Slider and Next event: stations, who is in the lab, the recipe and why, the result only after its test." |
| Timeline | "Every trial across the run, nights and weekends shaded, faults and skips marked." |
| Overnight handovers | "What happened while nobody was in, in plain language." |
| Does learning help? | "The adaptive strategy against a fixed list and random recipes over 40 campaigns, and how the advantage changes with difficulty." |
| Throughput | "Autonomous against a manual baseline you can edit. The one calculation the dashboard makes." |
| What this shows | "What the simulation shows, and plainly what it does not." |

### Platform pages (8503 only)

| Page | Say |
|---|---|
| 3D replay | "The finished run played back in 3D, trial by trial, with the plan and the executor's report for each." |
| Data and model | "How the pieces connected, what the reader found in the data file, what the modelling step made of it, and what this run does not show." |
| Reports | "Download the report page, the PDF, the Excel workbook and the CSV tables: the same numbers as the dashboard, labelled." |

### Live run (8504)

| Part of the page | Say |
|---|---|
| Start the run, speed, camera | "The simulation running while we watch. Faster than real time; we choose the speed." |
| Clock and phase chips | "The simulated date and time, and which of Act, Sense, Reason or Adapt the cell is in." |
| 3D picture and trial strip | "The arm at work. A trial turns green, grey or red only when its result is published." |
| Results so far, Faults and alerts, What is happening | "Each is published by the simulation at that moment. Nothing is shown early." |
| Good recipes so far | "The running count of good recipes." |

### Other things to open

| Open | Say |
|---|---|
| `runs\scorecard\index.html` (double-click `run_scorecard.bat`) | "How each model did on data it had not seen, with a plain verdict on whether its warnings can be trusted. Models that cannot be trusted are marked as such." |
| `runs\ingest\...quality_report.md` (double-click `make_example_reports.bat`) | "A report for each data file that accounts for every row and writes down every assumption." |
| `runs\guides` | "The demo script, the system explained in plain language, the work report and the acceptance-run design, all in one look." |

## If a question comes up

| Question | Answer |
|---|---|
| Is this real data? | No. Illustrative or synthetic. The only real data are public datasets used to test the software, labelled "real public data, not client data". |
| Does it need the internet? | No. The page, the 3D library and the font are all inside the files. |
| Can it run a different study? | Describe it in the setup app, then drag the saved file onto `run_platform.bat`. If it has more than the five ingredients the stand-in lab knows, it says plainly what to change. |
| How many trials does it do? | About 30 in the 5-day window (written as a range such as 29 to 30 elsewhere, because the count hangs on a small timing margin). It is not a target. |
| How do you know it is working? | Every stage has a double-click health check, and `check_all.bat` runs them all in one table. |
| Why does the dashboard not calculate? | By design, so what you see is what the simulator recorded. The one exception is trials per week divided by the manual baseline. |

## Closing down

Close the browser tabs. Click each black window and press **Ctrl+C**, or just close it. Always close a black window before starting that app again.

## If something goes wrong

| What you see | What to do |
|---|---|
| A black window flashes and closes | Open a terminal in the project folder and run `run_platform.bat` from there to see the message. |
| "There is no run record" or "out of date or damaged" | Double-click `build_demo.bat` (original dashboard) or `run_platform.bat` (platform dashboard), then press F5. |
| The 3D picture is blank | Press F5. If it stays blank, double-click `make_platform_demo.bat` for the stand-alone replay page. |
| The Reports tab shows no files | Double-click `make_reports.bat`, then F5. |
| Anything else | Double-click `check_dashboard.bat`: it names the failing part in plain words. |
