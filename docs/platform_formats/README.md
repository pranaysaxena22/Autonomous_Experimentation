# Proposed platform file formats - examples

**All files here are ILLUSTRATIVE or SYNTHETIC examples. They are a proposal, not yet used by any program.**
Open them in Excel (the .csv files), Notepad or VS Code (the others). Run `check_formats.bat` (in the project folder) to check them all.
Naming rules and mappings: `docs/naming.md`.

| File | What it is | Written by | Read by |
|---|---|---|---|
| `experiments_example.csv` + `experiments_example.meta.json` | A clean experiment table (first 12 rows of the synthetic mock data) and its version / synthetic label | the client | data ingestion, modelling |
| `experiments_messy_example.csv` + `.meta.json` | A deliberately messy table from the hard mock data: failed runs, values in newtons, missing values, below-detection values, replicates, four batches | the client | data ingestion tests |
| `setup_example.yaml` | Everything the client fills in on the setup screens, including how to read the experiment table (`data:`) | the setup app | every part |
| `cell_layout_example.json` | Stations, bottle slots, tool holders, objects, robot arm dimensions (3D reach is checked) | the setup app | executor, 3D viewer |
| `motion_plan_example.json` | **Intent only**: a full trial as a timed list of actions (move, pick, place, pour, shake, press, stir, scan, read, wait) | the motion planner | the executor |
| `executed_timeline_example.json` | **What happened** for the same trial (T008): the same actions with actual times and outcomes, a binder-bottle jam, and its recovery actions | the executor | the 3D viewer, the run record |
| `trial8_story.md` | A plain-language table of the executed timeline: time, action, object, station or slot, planned or recovery, and why. **Generated** by `tools/make_trial_story.py` and checked against the timeline | the script | people reading the example |
| `run_record_v2_example.json` | The run record with the new data, model and motion-plan sections; unchanged sections are marked | the cell simulator | the dashboard, reports |
| `schemas/*.schema.json` | Machine-readable rules (JSON Schema): required and optional fields and allowed values, one per format | us | `check_formats.bat`, the setup screens |

The plan and the executed timeline describe the same trial. The plan is the same for any trial of that recipe; the executed timeline
is where a fault shows up, because the plan never contains faults.

## Important notes
- **The example files are hand-authored until Stage 6.** At Stage 6 the real planner will generate plans, and those generated plans must pass the same checks that `check_formats.bat` runs on these examples (step totals within 1 second, every wait with a reason, friability steps only when the setup needs them, and so on).
- **Platform fault timing comes from the executor and will not match the PoC's.** The PoC charges a failed attempt the whole step, then a purge, then the whole step again (dispense would take 7,200 s). In the platform the executed timeline decides: the fault costs what its recovery actions cost (dispense takes 5,635 s in the example). The PoC and `main` are unchanged.
- **`trial8_story.md` is generated, not written.** Run `python tools/make_trial_story.py` after changing the executed timeline; `check_formats.bat` fails if the story and the timeline disagree.
- **Reach:** the example layout has 0.080 m of spare reach at its tightest spot, which `check_formats.bat` reports as a warning (policy: warn below 0.10 m, fail below 0.03 m).
- **The friability tester is used** by the example plan (the setup has friability as an objective). The planner includes friability steps only when the setup needs them.