# Demo walkthrough: one sitting, about 40 minutes

> **Note (2026-10-13):** this is the Stage 3 demo. For the whole platform (setup app, dashboard, 3D replay, data and model page, reports and the honest findings) use the newer **demo script**, `docs/guides/demo_script.md` (double-click `make_guides.bat` for the branded page). Where this older walkthrough says the platform's own 3D viewer or the configurable simulator are "not built yet", that is out of date: they are built (Stages 5 to 8).

**Everything shown is illustrative or synthetic, or real public data that is not client data.** Say this first and let the banners say it again.
Nothing is uploaded anywhere. Everything runs on this laptop. The one exception that needs the internet is the optional 3D reference viewer (see "Risks").

## Before you start (10 minutes, do it before people arrive)
1. Close old black windows from earlier testing. Check nothing is running: double-click `run.bat` later will tell you if a port is busy.
2. In **VS Code**, open these files in tabs and press **Ctrl+Shift+V** in each to see them as formatted pages (do not use Notepad: it may garble the "›" and "÷" characters):
   - `runs\ingest\literature_quality_report.md`, `runs\ingest\mock_formulation_experiments_quality_report.md`
   - `runs\modelling\model_summary_full.md`, `runs\modelling\calibration_summary.md`, `runs\modelling\domain_summary.md`
3. Switch off sleep and screen lock. Browser at 100% zoom. Close the other programs.
4. Double-click `run.bat`, type **3** and press Enter. Two black windows open (the dashboard on port 8501, the setup app on port 8502). **Leave both open.** If a window says "port ... is already in use", an old one is still running: close it and try again.
5. Rehearse offline if you like: turn Wi-Fi off. Everything except the 3D viewer still works.

## Part 1: the setup app (about 6 minutes) at http://localhost:8502
| Click | What to say / what it proves |
|---|---|
| Click **Load example**. Point at the green "Simulation with illustrative values" bar, the ten screens on the left and the counts under each | A client describes their own study screen by screen, in plain words. It checks, saves and previews; it calculates no results. The example has **one warning, on Equipment** (the robot's tightest spot has 0.080 m of spare reach; "it still works"): an honest warning, not a fault. |
| Screen **2. Ingredients**: change Drug's *Lowest value* to **40** | An **Error:** box appears right under the field in plain English; the left list says "1 error". Mistakes are caught where they are made. |
| Screen **10. Review and save** | The same message is listed under Ingredients, and **Save setup** is greyed out while any error remains: a broken setup cannot be saved. |
| Put the value back to 10, save as `demo`. Open **Preview: what the proof of concept would use** | It saves; the preview says "PREVIEW ONLY" and never overwrites the real settings. |
| Click **Start blank** | A fresh setup lists everything still to do. Every message is listed in `docs\setup_messages.md` (134 tests, one per message). |

## Part 2: reading the client's data (about 6 minutes), in VS Code
| Open | What to say / what it proves |
|---|---|
| `mock_formulation_experiments_quality_report.md` | Starts with its label **SYNTHETIC DATA**, then the **row accounting**: 3,672 rows read, 145 failed runs set aside, 644 replicate rows combined, 2,883 left, "the counts add up". Nothing is dropped silently. |
| `literature_quality_report.md` (real public data) | Label **REAL PUBLIC DATA, NOT CLIENT DATA**. 1,982 rows in, 1,982 out. Under "What needs your attention": values outside 0 to 100% **kept, not changed**; hardness converted from kg/cm2 assuming 1:1, **marked as an assumption**; the **Weight check** shows 118 rows (6.0%) whose ingredient amounts do not add up to the tablet weight. Every assumption is written down. |
| Mention `laboratory_quality_report.md` | The second real dataset (1,005 production batches), same treatment. |

## Part 3: models, calibration and the safeguard (about 12 minutes), in VS Code
**Open `model_summary_full.md`.** It has three parts kept apart: **A** the main comparisons (the only ones a model is chosen from), **B** exploratory, **C** robustness-only.
| Where | What to say / what it proves |
|---|---|
| Top of the page | Every model is tested only on **whole groups it has never seen** (whole batches, whole suppliers, later dates): never random rows. Every table shows the two naive baselines beside every model, and a **Fitted** column says whether a model was fitted jointly across results (only one was) or separately for each result. |
| Part A, real batch data (`batch_production`), **tbl_av_hardness** | Hardness is predicted well (the best model's error is about 36% of the spread). Note that the supplier column says **"proxy, not a confirmed supplier"** wherever it appears: the file has no supplier column and we say so. |
| Part A, **dissolution_av** | The honest finding below: dissolution is barely predictable from this data. |
| Part C, literature table | The honest finding below. |
**Open `calibration_summary.md`.** "Is the uncertainty each model states honest?" A model's "90% range" should contain the truth about 90% of the time. Show one carried table: some models are honest, some are over-confident (the neural-network ensemble, about 33 to 45%), and recalibration fixes a uniform over-confidence but **does not reliably carry over to a new supplier or a later month**. Part C lists what was **not assessed, with reasons**: no calibration number is given for results the model cannot predict.
**Open `domain_summary.md`.** The top paragraph is the point: **no model's stated range tracks its own error**, so a model cannot tell you when it is unsure. These warnings ("is this recipe, or this whole group of recipes, far from the data?") are the safeguard. They show **four separate statuses**, never one combined flag: distance, numeric range, an unseen supplier or product (named), and a whole-group check. They are reliable for new batches (the group check flags 5% of ordinary batches, as designed), and their thresholds are steady across folds (largest-over-smallest ratio at most 1.18, while the recalibration factor swung up to 2.11). **Limit: for a new supplier or time period there are too few ordinary groups to compare with, so the group check can only say "new group" and flags them all; the report says "chance alone".**

## Part 4: the original proof-of-concept dashboard (about 10 minutes) at http://localhost:8501
Unchanged since the first demo (its code is byte-identical to the `main` branch). It runs on a simulated cell with illustrative values. Six tabs; the banner says "Simulation with illustrative values".
| Click | What to say / what it proves |
|---|---|
| **The run** tab: click **Next event** a few times | The cell works through Dispense, Blend, Press, Test and Clean with **nobody in the lab**. The four boxes (Sense, Reason, Act, Adapt) repeat every trial, and each recipe has a "why this recipe". The run starts **Fri 09 Oct 18:00**. |
| Drag the slider to **Sat 10 Oct 09:00** | Trial 4's result appears: the first recipe measured good. Results never show before their test finishes. |
| **Sat 10 Oct 22:30**, then Next event to **Sun 11 Oct 00:00** | Trial 8's dispenser clog: the Dispense tile turns red ("Purging after binder dispenser clog"); the cell recovers by itself. |
| **Mon 12 Oct 21:30**, then to **Tue 13 Oct 08:00** | Trial 19's retry fails and the candidate is skipped: an alert "waiting for staff, queued for Tue 13 Oct 08:00", then "Staff arrived". Faults are handled, and people are told. |
| **Timeline**, **Overnight handovers** | Every trial across the run, grey shading where nobody is in the lab; read one handover aloud: this is what the first person in on Monday gets. |
| **Does learning help?** | The adaptive strategy against a fixed list and random recipes over 40 campaigns, with the difficulty table: the advantage is largest when good recipes are rare and **disappears when they are common**. |
| **Throughput**, **What this shows** | Autonomous against manual (type the client's own manual figure to update the multiple). Finish on "What this shows": it states plainly what the simulation does **not** show. |

## Part 5 (separately, only if you choose to open it): the 3D viewer
Double-click `reference\robot_cell_viewer_reference.html`. **Say what it is: a reference viewer, not part of the platform.** The platform's own 3D replay viewer has not been built. It **needs the internet** (it loads a 3D library and a font from the web) and is blank without it.

---

## The honest findings: say them, do not hide them
| Finding | What to say | Where it is |
|---|---|---|
| **The literature table: no model beats the baseline** | "With whole drugs held out, no model predicts hardness, friability or disintegration time better than guessing the average. These formulation records do not let a model predict for a drug it has not seen. So we use that table only to test that the software copes with messy real data, and it is labelled 'robustness test only', never an accuracy claim." | Part C of `model_summary_full.md` |
| **Dissolution is not predictable from this data** | "On the real production-batch data, the best model for dissolution explains only about 13% of the variation in its hardest test, and yield about 28%. Hardness and tensile strength are predicted well (tensile is calculated from hardness, so that is one finding, not two). We did not calibrate the weak ones: it would be a precise-looking number for a model that does not predict well enough to matter. Dissolution is the cell's central target, so on real data it can only be proven on the synthetic mocks so far." | Part A of `model_summary_full.md`; Part C of `calibration_summary.md` |
| **The warning is weak under a supplier or date shift** | "Models do not know when they are unsure, so we built warnings: per recipe (distance, range, unseen supplier or product) and for a whole group of recipes. They work for new batches. For a new supplier or a later month there are too few ordinary groups to compare with, so the group check can say 'this is a new group' but not how unusual; we say so in the report. We decided on four improvement options: built two, declined one (it would be after-the-fact tuning), deferred one." | `domain_summary.md`; `docs\decisions.md`, "Open decision, parked" |
| **Recalibration does not travel** | "A correction learned on some suppliers or months does not always carry over to another: it helped for new batches but was worse than none in 5 of 22 supplier cases and 9 of 22 later-month cases." | `calibration_summary.md` |
| **The neural-network ensemble is over-confident** | "Its stated 90% ranges contain the truth only about 33 to 45% of the time on the synthetic tables. Calibration caught it; scaling the range fixes it." | `calibration_summary.md` |
| **Data problems are shown, not hidden** | "118 rows in the literature table do not add up to the tablet weight: we kept them, flagged them, and show scores with and without them." | `literature_quality_report.md`, "Weight check" |

## What is built and what is not (be exact if asked)
- **Built and tested (712 automated checks, all passing as of 2026-10-11: `check_all.bat` gave 712 passed, 0 failed, 1 design warning; the walkthrough's earlier figure of 616 was the count on the evening before the demo):** the proof of concept (cell simulator, virtual lab, adaptive engine, dashboard); the setup app and its checker; reading and cleaning the client's data with quality reports; modelling with grouped validation (never random rows), model comparison, calibration, and the applicability-domain warning.
- **Built since the demo:** the decision-usefulness replay (Stage 3b-3, synthetic mocks only) and the model scorecard (Stage 3b-4; `run_scorecard.bat`); Stage 3b is complete and tagged `stage3b-complete`.
- **Not built yet (updated after the demo):** the upgraded decision engine on real data (Stage 4), the configurable cell simulator, the cell executor and motion planner, and the platform's own 3D replay viewer. **Nothing here has been run on client data.**
- **Decision parked until after the demo:** the four options for improving the warning under supplier and date shifts (`docs\decisions.md`).

## Risks and how to handle them (read the night before)
| Risk | What to do |
|---|---|
| **The 3D viewer needs the internet** and is a reference file, not our viewer | Only open it with a connection, and say what it is. If there is no connection, skip Part 5. |
| **The dashboard is reachable from other computers on the same network** (its start-up message shows a "Network URL"); the setup app is not | On a shared or public Wi-Fi, run the demo with Wi-Fi off or on a trusted network. The page only shows illustrative data, but do not leave it running. |
| **A window says "port 8501 or 8502 is already in use"** | An old window is still running. Close it (or press Ctrl+C in it) and start again, or just use the page that is already open. |
| **Windows may ask about network access** the first time | Choose "Private networks" / allow once: it only talks to itself. |
| **The reports are plain text files** | Open them in VS Code with preview (Ctrl+Shift+V). Notepad may show odd characters for "›" and "÷". |
| **The model summary is long (about 365 lines)** | Do not read it out. Show the top paragraph, one Part A table, and Part C. Use the headings in the VS Code outline. |
| **`check_all.bat` takes about 9 minutes** | Do not run it during the demo. It passed tonight: 616 checks, 0 failed (one old, known warning about the robot's reach margin, the same one the setup app shows). |
| **Many Edge windows are open from earlier days** | Close the old ones before the demo (they use memory). |
| **If a page misbehaves** | Press F5. If the dashboard still fails, present from the offline backups: `runs\stage4\timeline.html`, `runs\stage3\comparison.html`, `docs\scenario.md` (they work offline and contain no web addresses). More in the README, "If the app will not start". |

Closing down: close the browser tab, then click each black window and press **Ctrl+C** (or just close it).
