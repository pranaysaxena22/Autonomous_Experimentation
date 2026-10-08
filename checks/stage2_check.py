"""Stage 2 health check: the cell simulator running a fixed list of recipes.

Prints a PASS/FAIL list in plain words and writes files you can open in runs/stage2/:
  timeline.html   a chart of every step of every trial, with unattended time shaded grey
  event_log.csv   the full event log (open in Excel)
  trials.csv      one row per trial: recipe, result, good or not
  record.json     the run record the dashboard will read
"""
from __future__ import annotations

import csv
import dataclasses
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.cell_simulator import simulate  # noqa: E402
from cellpoc.contracts import Formulation  # noqa: E402
from cellpoc.decision_engine import FixedListStrategy  # noqa: E402
from cellpoc.runner import run_fixed_list  # noqa: E402
from cellpoc.settings import SettingsError, load_settings  # noqa: E402
from cellpoc.settings.models import Cell  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, write_chart_page  # noqa: E402

OUT = ROOT / "runs" / "stage2"
FMT = "%Y-%m-%d %H:%M"
checklist = Checklist("STAGE 2 CHECK - cell simulator with a fixed list of recipes")
record = checklist.record


def staffed_at(settings, moment: datetime) -> bool:
    """Is anyone in the lab at this moment? Worked out afresh from the settings, as the cross-check."""
    p = settings.people
    return moment.weekday() in p.staffed_weekdays and p.staffed_from <= moment.time() < p.staffed_until


def check_run(settings, run):
    s = settings
    per_trial = s.cell.minutes_per_trial
    expected_trials = int(s.run.duration_hours * 60 // per_trial)
    trials = run.trials

    record(len(trials) == expected_trials, "The cell completes as many whole trials as fit in the run",
           f"{len(trials)} completed; {s.run.duration_hours:g} h at {per_trial / 60:g} h per trial allows {expected_trials}")
    record(bool(trials) and trials[0].steps[0].start == s.run.start.strftime(FMT),
           "The first step starts exactly when the run starts",
           f"{trials[0].steps[0].start if trials else 'no trials'}")
    end = s.run.start + timedelta(hours=s.run.duration_hours)
    last_end = trials[-1].steps[-1].end if trials else ""
    record(last_end == end.strftime(FMT) if expected_trials * per_trial == s.run.duration_hours * 60 else last_end <= end.strftime(FMT),
           "The last trial finishes by the end of the run", f"last step ends {last_end}; run ends {end.strftime(FMT)}")

    record(all(t.end_minute - t.start_minute == per_trial for t in trials),
           "Every trial takes exactly the sum of its steps", f"{per_trial:g} minutes each")
    steps_ok = all([i.step for i in t.steps] == [x.name for x in s.cell.steps]
                   and all(i.end_minute - i.start_minute == x.duration_minutes for i, x in zip(t.steps, s.cell.steps))
                   for t in trials)
    record(steps_ok, "Every trial goes through the steps in order, each lasting what the settings say",
           " > ".join(f"{x.label} {x.duration_minutes:g}" for x in s.cell.steps) + " (minutes)")

    intervals = sorted((i.start_minute, i.end_minute, i.step, t.trial) for t in trials for i in t.steps)
    one_at_a_time = all(b[0] >= a[1] for a, b in zip(intervals, intervals[1:]))
    record(one_at_a_time, "Only one step is ever running at a time (one trial at a time, no overlaps)")
    double_booked = []
    for step in {x[2] for x in intervals}:
        mine = sorted(x for x in intervals if x[2] == step)
        double_booked += [(a, b) for a, b in zip(mine, mine[1:]) if b[0] < a[1]]
    record(not double_booked, "No station is ever used by two trials at once")
    record(all(b.start_minute == a.end_minute for a, b in zip(trials, trials[1:])),
           "The cell never sits idle between trials: each starts the minute the last one ends")
    times = [e.minute for e in run.events]
    record(times == sorted(times), "The event log is in time order", f"{len(run.events)} events")

    kinds = [e.kind for e in run.events]
    record(kinds.count("decision") == len(trials) and kinds.count("measurement") == len(trials)
           and kinds[0] == "run_started" and kinds[-1] == "run_finished",
           "The event log has one decision and one measurement per trial, and opens and closes the run")

    lab = VirtualLab(s)
    again = [lab.measure(t.trial, Formulation(**t.recipe)) for t in trials]
    record(all(m.dissolution_pct == t.dissolution_pct and m.hardness_kp == t.hardness_kp for m, t in zip(again, trials)),
           "Every recorded result is exactly what the lab reports for that recipe and trial number")
    ranges_ok = all(i.min <= t.recipe[i.key] <= i.max for t in trials for i in s.design_space.ingredients)
    record(ranges_ok, "Every recipe tried is inside the allowed ingredient ranges")


def check_fixed_list_ignores_results(settings, run):
    """A fixed list must not react to results: change the lab's noise and the recipes must stay put."""
    capacity = len(run.trials)
    other_lab = VirtualLab(settings, seed=settings.run.random_seed + 99)
    other = simulate(settings, other_lab, FixedListStrategy(settings.design_space, max(capacity, settings.comparison.trials_per_campaign),
                                                           settings.run.random_seed), "other-lab-seed")
    same_recipes = [t.recipe for t in run.trials] == [t.recipe for t in other.trials]
    different_results = [t.dissolution_pct for t in run.trials] != [t.dissolution_pct for t in other.trials]
    record(same_recipes and different_results,
           "The fixed list ignores results: a different lab seed changes the readings but not the recipes tried")
    again = run_fixed_list(settings, run_id=run.meta.run_id)
    record(again == run, "Running the same settings twice gives an identical run record")


def check_calendar(settings, run):
    cal = run.calendar
    total = sum(b.end_minute - b.start_minute for b in cal)
    contiguous = all(b.start_minute == a.end_minute for a, b in zip(cal, cal[1:]))
    record(cal[0].start_minute == 0 and cal[-1].end_minute == run.meta.duration_minutes and contiguous and total == run.meta.duration_minutes,
           "The staffed/unattended calendar covers the whole run with no gaps", f"{len(cal)} blocks")
    staffed_ok = True
    for b in cal:
        if b.staffed:
            first = datetime.strptime(b.start, FMT)
            last = datetime.strptime(b.end, FMT)
            staffed_ok &= (first.weekday() in settings.people.staffed_weekdays
                           and first.time() >= settings.people.staffed_from and last.time() <= settings.people.staffed_until)
    record(staffed_ok, "Staffed time falls only on the staffed days and hours in the settings")
    staffed_hours = sum(b.end_minute - b.start_minute for b in cal if b.staffed) / 60
    record(abs(run.summary.unattended_hours - (run.summary.run_hours - staffed_hours)) < 1e-9,
           "Unattended hours = run hours minus staffed hours",
           f"{run.summary.unattended_hours:g} unattended of {run.summary.run_hours:g} h")

    start = settings.run.start
    expected = sum(1 for t in run.trials if not staffed_at(settings, start + timedelta(minutes=t.start_minute)))
    record(run.summary.trials_started_unattended == expected,
           "The count of trials started with nobody in the lab matches a fresh count from the settings",
           f"{expected} of {len(run.trials)} trials started unattended")


def check_headline(settings, run):
    expected = len(run.trials) / (settings.run.duration_hours / 168)
    record(abs(run.summary.trials_per_week - expected) < 0.05
           and run.summary.manual_baseline_trials_per_week == settings.comparison.manual_baseline_trials_per_week,
           "The trials-per-week figure is trials completed scaled to a 168-hour week, against the manual baseline",
           run.summary.headline)
    checklist.headline(run.summary.headline)


def check_what_if(settings):
    """Stretch the blend step and confirm the cell copes: fewer trials fit and the log explains why."""
    steps = tuple(dataclasses.replace(x, duration_minutes=90) if x.name == "blend" else x for x in settings.cell.steps)
    slower = dataclasses.replace(settings, cell=Cell(steps, settings.cell.measurement_step))
    run = run_fixed_list(slower)
    per_trial = slower.cell.minutes_per_trial
    expected = int(slower.run.duration_hours * 60 // per_trial)
    final = run.events[-1].message
    record(len(run.trials) == expected and expected < int(settings.run.duration_hours * 60 // settings.cell.minutes_per_trial),
           "What-if: with the blend step stretched to 90 minutes, fewer trials fit",
           f"{len(run.trials)} trials of {per_trial:g} minutes (was {int(settings.run.duration_hours * 60 // settings.cell.minutes_per_trial)})")
    record("not started" in final, "What-if: the log explains why the last trial was not started", final)
    record(max(t.end_minute for t in run.trials) <= run.meta.duration_minutes,
           "What-if: no trial runs past the end of the run")


def write_files(settings, run):
    OUT.mkdir(parents=True, exist_ok=True)
    path = run_store.save(run, OUT)
    record(run_store.load(path) == run, "The run record saved to disk reads back identical", str(path.relative_to(ROOT)))

    labels = run.ingredient_labels
    with open(OUT / "event_log.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["When", "Trial", "Step", "Someone in the lab?", "Event"])
        for e in run.events:
            writer.writerow([e.when, e.trial or "", e.station or "", "yes" if e.attended else "no", e.message])
    with open(OUT / "trials.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Trial", "Started", "Finished"] + [f"{v} %" for v in labels.values()]
                        + ["Dissolution %", "Hardness kP", "Outcome", "Good so far"])
        for t in run.trials:
            writer.writerow([t.trial, t.start, t.end] + [round(t.recipe[k], 2) for k in labels]
                            + [round(t.dissolution_pct, 1), round(t.hardness_kp, 2), t.outcome, t.good_so_far])

    import altair as alt
    import pandas as pd

    green, grey, font = settings.display.accent_colour, "#9AA5B1", settings.display.font
    bars = pd.DataFrame([{"Station": i.label, "Trial": t.trial, "Start": i.start, "End": i.end, "Result": t.outcome,
                          "Someone in the lab when it began": "yes" if i.attended else "no"}
                         for t in run.trials for i in t.steps])
    shade = pd.DataFrame([{"Start": b.start, "End": b.end, "State": b.label} for b in run.calendar])
    order = [x.label for x in run.steps]
    background = alt.Chart(shade).mark_rect(opacity=0.35).encode(
        x=alt.X("Start:T", title="Date and time"), x2="End:T",
        color=alt.Color("State:N", scale=alt.Scale(domain=["Unattended", "Staffed"], range=["#D5D9DE", "#FFFFFF"]),
                        legend=alt.Legend(title="Lab")))
    foreground = alt.Chart(bars).mark_bar(height=18).encode(
        x="Start:T", x2="End:T", y=alt.Y("Station:N", sort=order, title=None),
        color=alt.Color("Result:N", scale=alt.Scale(domain=["Good", "Not good"], range=[green, grey]),
                        legend=alt.Legend(title="Trial result")),
        tooltip=["Trial", "Station", "Start", "End", "Result", "Someone in the lab when it began"])
    timeline = (background + foreground).properties(
        width=1000, height=200, title="Every step of every trial. Grey background = nobody in the lab")
    progress = pd.DataFrame([{"Trial": t.trial, "Good trials so far": t.good_so_far} for t in run.trials])
    line = alt.Chart(progress).mark_line(interpolate="step-after", color=green, point=True).encode(
        x=alt.X("Trial:Q", scale=alt.Scale(zero=False), axis=alt.Axis(tickMinStep=1)),
        y=alt.Y("Good trials so far:Q", axis=alt.Axis(tickMinStep=1)),
        tooltip=["Trial", "Good trials so far"]).properties(
        width=1000, height=140, title="Good recipes found so far (fixed list)")
    chart = alt.vconcat(timeline, line).configure(font=font).configure_title(font=font, color="#333", fontSize=14)
    write_chart_page(chart, OUT / "timeline.html", settings.display.banner, green, font)
    record((OUT / "timeline.html").exists() and (OUT / "event_log.csv").exists() and (OUT / "trials.csv").exists(),
           "The timeline chart, event log and trials spreadsheet were written", str(OUT.relative_to(ROOT)))


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as error:
        record(False, "The settings file loads without problems", "\n        ".join(error.problems))
        return checklist.print()
    run = run_fixed_list(settings, run_id="stage2-fixed-list")
    check_run(settings, run)
    check_fixed_list_ignores_results(settings, run)
    check_calendar(settings, run)
    check_headline(settings, run)
    check_what_if(settings)
    architecture.check(checklist)
    write_files(settings, run)
    return checklist.print()


if __name__ == "__main__":
    sys.exit(main())
