"""Writes docs/scenario.md, the one-page plain-English description of the simulated cell.

The page is generated from config/settings.yaml, so its numbers can never go out of date.
Edit the settings, not the page.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

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
- Running one trial at a time, the cell completes {total / trial_hours:g} trials in the run.

## Faults that happen on purpose
{fault_lines}

How a fault plays out in time (these are modelling assumptions, stated so they are never a surprise):
- A failed attempt takes the step's full duration and is found to have failed at the end of it.
- The cell then purges for {s.scripted_faults.purge_minutes:g} minutes and retries the step for its full duration.
- If the retry fails, the candidate is skipped: no later step runs, no cleaning is done, no result exists, and the next candidate starts immediately. An alert is queued for the next time staff are in the lab.
- A trial is started only if all of it, including its scripted delays, fits before the run ends. Nothing is adjusted to reach a particular number of trials, so a small change to a purge time can change how many trials fit.

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
- **Ingredients are not forced to sum to 100%.** Each of the five percentages is varied independently within its own range, so a recipe's ingredients can add up to more or less than 100%. A real design space would normally fix one ingredient (often the filler) as the remainder.
- **The tablet behaviour is a made-up placeholder.** The virtual lab's hidden truth is a smooth illustrative model, not real pharmaceutical data.
- **The hidden truth is smooth,** which favours a strategy that learns a model of it. Real formulation data would be rougher, so the size of the adaptive strategy's lead here is illustrative, not a prediction.
- **A symptom of that smoothness:** in the default 40-campaign comparison the adaptive strategy typically finds its first good recipe within one or two choices after its six starting recipes, so its median and its 75th-percentile trial coincide. A model fitted to six results is already enough to point at the good region of a smooth surface; a rougher real surface would take longer to learn.
- **Charts work offline, fonts may not.** The chart library is bundled into each generated page, but Open Sans is only used if it is installed on the viewing computer; otherwise the browser shows Arial.
- **One trial at a time.** The cell never works on two trials at once.
- **Measurement noise is the only random effect** in the lab. There is no instrument drift, no reagent run-out and no recalibration.

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
