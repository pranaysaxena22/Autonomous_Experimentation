"""Writes docs/scenario.md, the one-page plain-English description of the simulated cell.

The page is generated from config/settings.yaml, so its numbers can never go out of date.
Edit the settings, not the page.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from cellpoc.about_text import limitations, trial_count_phrase
from cellpoc.runner import run_closed_loop, run_other_cleaning
from cellpoc.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def unattended_hours(settings: Settings) -> tuple[float, float]:
    """(hours when nobody is in the lab, total run hours), counted minute by minute."""
    people, run = settings.people, settings.run
    total = int(run.duration_hours * 60)
    staffed = 0
    for minute in range(total):
        moment = run.start + timedelta(minutes=minute)
        if (moment.weekday() in people.staffed_weekdays
                and people.staffed_from <= moment.time() < people.staffed_until):
            staffed += 1
    return (total - staffed) / 60, total / 60


def build(settings: Settings) -> str:
    s = settings
    end = s.run.start + timedelta(hours=s.run.duration_hours)
    unattended, total = unattended_hours(s)
    trial_hours = s.cell.minutes_per_trial / 60
    day_list = [DAY_NAMES[d] for d in s.people.staffed_weekdays]
    staffed_days = (" and ".join([", ".join(day_list[:-1]), day_list[-1]]) if len(day_list) > 1
                    else (day_list[0] if day_list else "no days"))

    default_run, other_run = run_closed_loop(s), run_other_cleaning(s)   # the numbers below come from real runs
    trials_phrase = trial_count_phrase(default_run, other_run)
    limitation_lines = "\n".join(f"- {text}" for text in limitations(s, default_run, other_run))
    cleaning = ("the cell still does a full cleaning step, with Reason and Adapt as usual, before moving on"
                if s.scripted_faults.clean_after_skip else "the next candidate starts immediately, with no cleaning")

    ingredient_rows = "\n".join(
        f"| {i.label} | {i.min:g}% | {i.max:g}% |" for i in s.design_space.ingredients)
    step_rows = "\n".join(
        f"| {n} | {step.label} | {step.duration_minutes:g} min |" for n, step in enumerate(s.cell.steps, 1))
    fault_lines = "\n".join(
        f"- **Trial {e.trial}** fails at the {e.station} step ({e.cause}). "
        + (f"The cell purges for {s.scripted_faults.purge_minutes:g} minutes, retries, and carries on."
           if e.retry_succeeds else
           f"The cell purges for {s.scripted_faults.purge_minutes:g} minutes and retries, but the retry "
           "also fails, so that candidate is skipped and an alert is logged.")
        for e in s.scripted_faults.events) or "- None."

    return f"""<!-- Generated from config/settings.yaml by checks/stage1_check.py. Edit the settings, not this page. -->
# Scenario: autonomous tablet formulation cell

> **{s.display.banner}.** All values are illustrative placeholders, to be replaced by a client's real design space.

## What this is
A simulated cell that designs, makes and tests tablet formulations without human help, over a
multi-day run. There is no physical robot: the cell and the lab are both simulated. The cell
decides which recipe to try next from the results it has already seen, and learns as it goes.

## The recipe space
Five ingredients are varied, each as a percentage of the tablet:

| Ingredient | Lowest | Highest |
|---|---|---|
{ingredient_rows}

## What "good" means
A tablet is good when **both** hold:
- {s.specifications.dissolution.label}: at least **{s.specifications.dissolution.minimum:g}{s.specifications.dissolution.unit}**
- {s.specifications.hardness.label}: between **{s.specifications.hardness.minimum:g}** and **{s.specifications.hardness.maximum:g} {s.specifications.hardness.unit}**

## What happens to each trial
Every trial passes through these steps, one after another:

| # | Step | Duration |
|---|---|---|
{step_rows}

One trial therefore takes **{trial_hours:g} hours** from start to finish.

The cell describes each trial in four phases (Sense, Reason, Act, Adapt):
- **Act** - making the tablets: {", ".join(s.cell.phases.act)}.
- **Sense** - measuring them: {", ".join(s.cell.phases.sense)}.
- **Reason** - the first {s.cell.phases.reason_minutes:g} minutes of the {s.cell.phases.reason_adapt_step} step: the decision engine reviews every result so far and chooses the next recipe.
- **Adapt** - the rest of the {s.cell.phases.reason_adapt_step} step: the cell finishes up and loads the next recipe.

## The run
- Starts **{DAY_NAMES[s.run.start.weekday()]} {s.run.start:%d %B %Y}, {s.run.start:%H:%M}** and lasts **{s.run.duration_hours:g} hours**, ending {DAY_NAMES[end.weekday()]} {end:%d %B %Y}, {end:%H:%M}.
- People are in the lab only on **{staffed_days}, {s.people.staffed_from:%H:%M}-{s.people.staffed_until:%H:%M}**.
- That leaves the cell **unattended for {unattended:g} of the {total:g} hours** of the run.
- Running one trial at a time, {trials_phrase} fit in the run once the scripted faults' delays are counted. With the default settings this run attempts {default_run.summary.trials_attempted} ({default_run.summary.trials_with_result} with a result, {default_run.summary.trials_skipped} skipped), which is {default_run.summary.trials_per_week:g} trials with results per week.

## Faults that happen on purpose
{fault_lines}

How a fault plays out in time (these are modelling assumptions, stated so they are never a surprise):
- A failed attempt takes the step's full duration and is found to have failed at the end of it.
- The cell then purges for {s.scripted_faults.purge_minutes:g} minutes and retries the step for its full duration.
- If the retry fails, the candidate is skipped: no later step runs and no result exists. An alert is queued for the next time staff are in the lab. After the skip {cleaning} (setting `clean_after_skip`; a clog is when you would clean).
- A trial is started only if all of it, including its scripted delays, fits before the run ends. Nothing is adjusted to reach a particular number of trials, so a small change to a purge time or the cleaning setting changes how many trials fit.

## The headline comparison
- **Adaptive vs fixed list:** {s.comparison.campaigns} repeated campaigns of {s.comparison.trials_per_campaign} trials each, to show the cell's learning beats a pre-written list of experiments.
- **Trials per week vs manual work:** compared against a manual baseline of **{s.comparison.manual_baseline_trials_per_week:g} trials per week** (editable in the settings).

## The five parts, kept apart
1. **Settings file** - every number above, in one place.
2. **Virtual lab** - plays the role of reality. It holds the hidden true behaviour of the tablet and returns noisy measurements.
3. **Cell simulator** - runs the clock, the steps, the faults and the event log.
4. **Decision engine** - chooses the next recipe. It sees only measurements, never the hidden truth.
5. **Dashboard** - displays what happened. It does no calculation of its own.

## Limitations
{limitation_lines}

## Future extensions
- **Overlapping trials:** let a new trial start dispensing while the previous one is being tested, to raise the number of trials per run.
- Instrument drift, reagent run-outs and recalibration.
- Stop and resume, and runs longer than 120 hours.
- Running the simulation in a separate process so the dashboard can watch it live.
"""


def write(settings: Settings) -> Path:
    path = ROOT / "docs" / "scenario.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(build(settings), encoding="utf-8")
    return path
