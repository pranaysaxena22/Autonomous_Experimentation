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
        f"- **Trial {e.trial}** fails at the {e.station} step. "
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

## The run
- Starts **{DAY_NAMES[s.run.start.weekday()]} {s.run.start:%d %B %Y}, {s.run.start:%H:%M}** and lasts **{s.run.duration_hours:g} hours**, ending {DAY_NAMES[end.weekday()]} {end:%d %B %Y}, {end:%H:%M}.
- People are in the lab only on **{staffed_days}, {s.people.staffed_from:%H:%M}-{s.people.staffed_until:%H:%M}**.
- That leaves the cell **unattended for {unattended:g} of the {total:g} hours** of the run.
- Running one trial at a time, the cell completes {total / trial_hours:g} trials in the run.

## Faults that happen on purpose
{fault_lines}

## The headline comparison
- **Adaptive vs fixed list:** {s.comparison.campaigns} repeated campaigns of {s.comparison.trials_per_campaign} trials each, to show the cell's learning beats a pre-written list of experiments.
- **Trials per week vs manual work:** compared against a manual baseline of **{s.comparison.manual_baseline_trials_per_week:g} trials per week** (editable in the settings).

## The five parts, kept apart
1. **Settings file** - every number above, in one place.
2. **Virtual lab** - plays the role of reality. It holds the hidden true behaviour of the tablet and returns noisy measurements.
3. **Cell simulator** - runs the clock, the steps, the faults and the event log.
4. **Decision engine** - chooses the next recipe. It sees only measurements, never the hidden truth.
5. **Dashboard** - displays what happened. It does no calculation of its own.
"""


def write(settings: Settings) -> Path:
    path = ROOT / "docs" / "scenario.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(build(settings), encoding="utf-8")
    return path
