# Model comparison (Stage 3a): what it does and how to read it

All results here are **illustrative**: the mock tables are **synthetic** (made by a program) and the two public tables are **real public data, not client data**.
Nothing in this stage is a claim about real tablets or any client.

## What it does, in plain words
It asks one question for each table: **how well can each kind of model predict a result for a group of experiments it has never seen?**
Seen from the outside, that is the honest test, because a new batch, a new supplier or a later week is what a real study meets.

- **It never tests on random rows.** Random rows would let a model "learn" a batch's quirks from its sibling rows and look better than it is.
  Instead, whole groups are held out: **whole batches**, **whole suppliers**, and **later dates** (train on earlier, test on later). Every test date is later than every training date.
  A hold-out that a table cannot support is skipped, with the reason, never replaced by random rows. `make_fold_maps.bat` shows every fold.
- **Every model is shown beside two naive answers**: the training mean, and a lookup of the nearest training row. A model that does not beat both is not useful.
- **Models:** linear regression and quadratic regression (ridge penalty chosen inside each training fold, never on the held-out fold), gradient-boosted trees with conformal ranges,
  random forest, a small neural-network ensemble, and a Gaussian process (plus a joint version). Every setting is fixed in advance and none was tuned to a table.
- **How each model is fitted across results (a stated limitation):** only the joint Gaussian process shares anything across results. Every other model is fitted independently, one model per result.
- **A model is never handed the answer.** Columns that are copies of a result, or calculated from it (tensile strength from hardness, diameter and thickness), are never used to predict it.
  A held-out score that is too good (R-squared above 0.99) is flagged "CHECK FOR LEAKAGE" instead of celebrated.

## The three kinds of table, and why they are kept apart
| Kind | Tables | What it can support |
|---|---|---|
| **Main comparison** | the three synthetic mocks; the real batch data without the two impurity columns (977 of 1,005 batches) | a model is chosen by the rule below |
| **Exploratory** | the real batch data restricted to batches that have both impurity measurements (633 batches) | information only. It is a smaller, non-random sample (the missing values all belong to one API source, confirmed in the source paper's Missing data section) and is never part of the headline comparison or the scorecard. Every heading says so |
| **Robustness only** | the literature table (1,982 formulations) | whether the code copes with a messy real table. It has no batch, supplier or date, so the only hold-out is "whole APIs" (inferred from identical molecular descriptors). It cannot support a claim about learning accuracy |

## How a model is chosen (main comparisons only)
A model's score is its **worst** hold-out type: its error divided by the result's spread (1.0 means no better than guessing the training mean). To be chosen it must beat **both** naive answers in
**every** hold-out type that can be run. Ties within 5% go to the simpler or faster model. If nothing qualifies, the answer is "no model beats the baseline".

## How to read a table
- **Error ÷ spread:** lower is better; 1.0 is no better than guessing the mean; above 1.0 is worse.
- **90% range hit rate:** how often the model's "90% range" contained the true value on held-out groups. About 0.90 is right. Far below means the model is overconfident. Stage 3a only reports it; Stage 3b judges and recalibrates.
- **Fitted:** "jointly across results" or "independently, one model per result".

## What the reports do not show
How any model does on real tablets or a client's data; whether a score is good enough to act on (Stage 3b and a formulation expert); anything about suppliers where the supplier split is a stand-in.
For the real batch data the supplier split uses `api_code`, a column the file does not explain, and it is labelled **"proxy, not a confirmed supplier"** wherever it appears.
Results that are calculated from each other (hardness and tensile strength; batch yield and tablet yield, which correlate at 0.95) are not independent findings and must not be presented as such.

## Calibration: is the stated uncertainty honest? (Stage 3b-1)
Every model states a 90% range. Calibration counts how often that range really contained the truth on groups the model never saw. **About 0.90 is honest.** Well below means over-confident (do not trust the range);
well above means wider than needed. Which results are worth calibrating is decided by a rule fixed in advance: only main comparisons whose best model beats both baselines and whose error is at most 0.70 of the spread are
**carried**; 0.70 to 0.80 is **carried but exploratory**; anything weaker is **not assessed** and gets no calibration number. Recalibration is a scale factor learned from the OTHER folds only (for time hold-outs, only earlier steps).
Run it with `run_calibration.bat`; read `runs\modelling\calibration_summary.md`.

## The applicability-domain warning: is this recipe far from the data? (Stage 3b-2)
A model cannot tell you when it is unsure (see calibration), so this warning looks only at the inputs. A recipe is warned if its distance to the nearest training rows is unusually large (compared with how far a whole new group
normally sits from the rest), if a numeric input is well outside the range seen in training, or if a category was never seen. The threshold is worked out from the training rows of each fold only, and is steady across folds.
It reports **four separate statuses, never one combined flag:** (1) distance, (2) numeric range, (3) an unseen supplier or product (the value is named), and (4) a whole-group check: is this whole batch, supplier or time period unfamiliar? The group check compares the average of the group with ordinary groups, so it spots a shift in a few inputs that no single recipe shows. It is reliable when there are at least ten ordinary training groups to compare with (batches); for a supplier or a time period there are only a few, so it can only say "new group" and flags them all, and the report says so ("chance alone"). Run it with `run_domain.bat`; read `runs\modelling\domain_summary.md`.

## The decision-usefulness replay: would a model have chosen better recipes than chance? (Stage 3b-3)
Synthetic mocks only. Each forward-in-time step of Stage 3a is a decision: the model was trained on rows dated before it and on nothing else (the replay reads those saved predictions and checks every step again for a leak).
Recipes in the step are ranked by the model's own probability of meeting the target (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0, as stated in the mock's setup), and the top 10% are picked.
They are compared with picking at random and with the perfect ranking, with an error bar that resamples whole batches. A target that nearly every recipe meets anyway (friability) gets "no room to improve", not a verdict.
It also asks whether warned picks did worse, for each of the three per-recipe statuses separately, and only when at least 30 picks were warned (they were not, so it says so). Because the replay is forward in time it can only
speak for the later-dates shift; the whole-batch and whole-supplier readings of the warning come from the saved Stage 3a hold-outs and are shown beside it, each with its own word ("picks out the large errors", "mixed", "does not", "cannot be judged"),
never merged. The mocks cannot show real input drift or a real supplier change (their recipes do not move with the date or the supplier), so a good later-dates result here is the easy case. Run it with `run_replay.bat`; read `runs\modelling\replay_summary.md`.

## The scorecard: one page per table (Stage 3b-4)
`run_scorecard.bat` writes `runs\scorecard\index.html` and one page per table from the saved answers (nothing refitted). Top to bottom a page has: the data-status banner; the unifying statement ("Everything built so far recognizes
batch-level variation well, but struggles specifically when the shift is a new supplier or a later time period."); the safeguard panel; a table of readings per kind of shift; on synthetic pages the limitation of the test data itself;
the results as carried, carried but exploratory and not assessed (each with its own look); the replay (synthetic pages); and what the page does not show. **Reading a kind of shift:** the per-recipe distance warning is judged for each
result separately and never averaged. "Picks out the large errors" needs a lift above 1 in every result and at least 30 warned rows in each; it is the only reliable reading. "Mixed" (above 1 in some results), "cannot be judged"
(fewer than 30 warned rows) and "does not" (never above 1) are three different findings and all three are not reliable. The word is never shown alone: each result's rows warned, lift and error ratio sit beside it, because the lift alone can
make a weak warning look good (on real API codes the lifts are 2.0 and 1.5 while warned rows' errors are only 1.1 and 1.3 times unwarned rows').

## How long it takes
Fast mode about 3 minutes; the full comparison about 10 minutes on a laptop with 8 cores (6 folds at a time); the health check `check_models.bat` about 3 minutes.

## Files
- `docs\modelling_messages.md`: every message the modelling part can show, each with the test that proves it. `docs\decisions.md` (section "Stage 3a"): every decision and why.
- Reports (not saved in git): `runs\modelling\model_summary_<mode>.md`, `model_report_<mode>_<table>.md`, `fold_map_<table>.md`.
- The test tables are described in `cellpoc\modelling\fixtures.py`; the real public data is never in git (see `data\public\SOURCES.md`).