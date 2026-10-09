# Decisions so far, and why

All work is ILLUSTRATIVE / SYNTHETIC until real client data and expert review exist.

## Proof of concept (on `main`)
| Decision | Why |
|---|---|
| Python with Streamlit | what you asked for; runs on this laptop, offline |
| Five parts kept separate: settings, virtual lab, cell simulator, decision engine, dashboard | so each can be changed or replaced without breaking the others; enforced by an automated import check |
| The dashboard only displays; its one calculation is trials per week divided by the manual baseline | keeps the dashboard trustworthy and simple; the exception is documented and guarded |
| The decision engine never sees the lab's hidden truth | otherwise results would flatter the engine; scoring after the fact uses a separate module |
| Settings in one YAML file with plain-English error messages | you can change numbers without reading code |
| One trial at a time; overlapping trials left as a future extension | matches the 4-hour cycle and keeps the first simulator simple |
| About 3% of random recipes truly good | a fixed list should not find a pass almost at once |
| Headline measure: first trial whose recipe is truly good (scored after the fact) | noise cannot flatter it; the measured-pass measure is shown second |
| 40 paired campaigns of 30 trials; seeds fixed in advance (2026 to 2065); no tuning on them | fair comparison; no choosing seeds after seeing results |
| Comparison without faults as the headline, with faults available | isolates the effect of learning |
| Adaptive engine = Gaussian-process model choosing the recipe most likely to pass both targets (a simple Bayesian optimisation) | learns from every result, says how sure it is, explains each choice |
| Scripted faults at the dispense step: trial 8 recovers, trial 19 fails its retry | shows recovery, skipping and an alert for the next working day |
| Cleaning follows a skipped candidate (a setting, on by default) | a clog is when you would clean |
| Trial counts written "about 29 to 30", never a bare number | the count hangs on a 30-minute margin |
| Run first, then replay; the dashboard reads one run-record file | simple, offline, and the dashboard stays logic-free |
| What the page shows must not reveal what is not yet known | a bug showed a result early; a check now guards it |
| Charts bundle their library; Open Sans font bundled | must work in a demo room with no internet |
| Deloitte brand styling, colours only from the palette (checked) | your request; avoids off-brand colours |
| `main` stays the safe PoC; new work on `platform-build` | the working demo cannot be damaged |
| `CLAUDE.md` holds the standing working rules | rules persist across sessions |

## Platform build (on `platform-build`)
| Decision | Why |
|---|---|
| Reference viewer and mock data live in `reference/`, `data/mock/`, `tools/` | keep them apart from the running code |
| Mock data is synthetic and never used to tune models; test on freshly generated seeds | tuning to it would make models look better than they are |
| Setup screens are a **separate small Streamlit app**, with one launcher (`run.bat`) offering both apps | setup must validate input, the dashboard must calculate nothing; a client still sees one product |
| Shared validation module with plain-English messages | the screens and health checks use the same rules |
| Use only scikit-learn, scipy, statsmodels (plus openpyxl and reportlab) | wheels exist for Python 3.14 (dry run); deep learning is unnecessary and heavy |
| The "18%" is the share of historical rows; random recipes pass 6.6% to 11.2% depending on setting and noise | historical rows cluster near good recipes; the measured figures are in `docs/platform_plan.md` |
| "Hard" mock data means harder to model, not rarer to pass | hard has more interactions, noise, drift and gaps; its pass share is slightly higher |
| Validation holds out whole batches, whole suppliers and later dates, never random rows | random rows leak replicates and batch effects and flatter the model |
| A sealed, structurally different second test lab, used only for final acceptance | catches models that only work on the generator they were built against |
| Stage 3 split into 3a (preparation, candidate models, grouped validation) and 3b (calibration, applicability warning, scorecard, decision-usefulness replay) | each part can be checked on its own |
| Plan order: setup and validation, ingestion, modelling (3a, 3b), engine, configurable simulator, executor and motion plan, 3D viewer, dashboard integration, reports, hardening | each stage rests on the one before |
| The motion plan is data; a Python stand-in executor now, Gazebo or hardware later | the same plan can later run on other executors |
| The 3D viewer only replays a plan (no logic) and bundles its library and fonts | keeps the "no logic" rule and works offline |
| Viewer screenshot check uses headless **Chrome** with software rendering; Edge headless is blocked by company policy; if it fails, a by-eye checklist is used | tested on this machine: the reference viewer's 3D scene rendered |
| The PoC and its five checks stay unchanged and are re-run at every stage | "never change existing behaviour without asking" |

## Format review: the fourteen decisions, and the answers to the review points
| Decision | Why |
|---|---|
| Ten action names: move, pick, place, pour, shake, press, stir, scan, read, wait (`read_instrument` becomes `read`; `tap_shake` becomes `shake` with style "tap"; no `event` in plans) | a small fixed vocabulary is easy to validate, plan and animate |
| Two files: the **motion plan** is intent only; the **executed timeline** is what the executor returns (same actions plus actual times, outcomes, faults, recovery actions tagged `planned` or `recovery`); the viewer replays the executed timeline | a plan can be written before anything happens; faults only exist after execution |
| Every action has a `step`; the plan header has `trial_start_minute`; within each step the action durations, waits included, add up to the setup's step time within 1 second | ties every action to the setup's timings and to the run clock |
| One ID per quantity with the unit in the name (`dissolution_30min_pct`, `hardness_kp`, `friability_pct`, ...); lowercase phases; rules in `docs/naming.md`; raw columns map to these in ingestion and PoC names map through the converter | removes the hardness / hardness_kp style confusion |
| `data_status` values: synthetic, illustrative, real, validated; a record takes its weakest input | one honest label that can only get stronger when every input does |
| `batch_size_g` in the setup (illustrative 20 g) | pour amounts need a batch size |
| Targets split into constraints (at least, at most, between) and objectives (maximise, minimise), each with a unit | "must be met" and "push as far as possible" are different |
| Faults get a structured `where` (step, action, ingredient); `chance_per_trial` and `retry_succeeds_chance` are probabilities used only for random faults | the planner must know where a fault belongs |
| A `data:` section in the setup (column mapping, newtons divided by 9.807, below-detection rule, replicates, missing values, failed runs); ingestion tolerates a byte-order mark and Windows line endings | how to read the client's table must live with the setup |
| Layout gets an object list, tool positions, shoulder height and link lengths; reach is checked in 3D | the 3D viewer and the executor need the arm's geometry |
| Machine-readable JSON Schemas for all formats; YAML read with the safe reader only; file references relative, inside the project, no `..` | catches typing mistakes and unsafe files |
| CSV without byte-order mark and with the mock's line endings; companion `.meta.json` with version and synthetic label; a second, messy example from the hard data | a CSV cannot carry its own label; the messy example exercises ingestion |
| Run record: every section present or marked `unchanged_from_poc`; model numbers null with a note | no realistic-looking numbers where no model exists |
| `check_formats.bat`: a permanent script that checks all of the above in plain words | the formats stay correct as the platform grows |

| Review point | Answer |
|---|---|
| Order of `data_status` | synthetic is weakest, then illustrative, real, validated (taken from the order given; approved by committing) |
| Does the example plan use the friability tester? | Yes (3 actions plus the 5-minute tumble). The setup needs it because friability is an objective, so it stays. **Rule: the planner includes friability steps only when the setup needs them**; a check enforces it |
| Fault timing | platform fault timing comes from the executor and will not match the PoC's rule; `main` is unchanged |
| Reach margin | warn below 0.10 m of spare reach, fail below 0.03 m; the example is at 0.080 m (a warning, layout unchanged) |
| Filler waits | every wait has a `reason` naming the real process it stands for (for example "friability drum tumbling the tablet for a fixed number of rotations"); a check enforces it |
| Example files | hand-authored until Stage 6, when the real planner generates plans that must pass the same checks |
| Trial-8 story | `trial8_story.md` is generated by `tools/make_trial_story.py` from the executed timeline and checked against it |
| BOM and CRLF tolerance | a Stage 2 requirement, proven now in the format check's reader |
