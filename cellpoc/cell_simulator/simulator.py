"""The cell simulator: runs trials one after another in simulated time and writes the run record.

It knows nothing about how recipes are chosen or how the tablet really behaves. It asks the
strategy for the next recipe, walks the trial through each step on the clock, asks the lab
for the measurement when the measuring step finishes, and logs everything.
"""
from __future__ import annotations

from ..contracts import (
    EventRecord, Formulation, Lab, Measurement, RunMeta, RunRecord, StepInfo, StepInterval, Strategy,
    Summary, TrialRecord, margin, meets_spec,
)
from ..settings import Settings
from .clock import RunClock


def simulate(settings: Settings, lab: Lab, strategy: Strategy, run_id: str) -> RunRecord:
    clock = RunClock(settings.run, settings.people)
    labels = {i.key: i.label for i in settings.design_space.ingredients}
    steps = settings.cell.steps
    trial_minutes = settings.cell.minutes_per_trial
    specs = settings.specifications

    events: list[EventRecord] = []
    trials: list[TrialRecord] = []
    history: list[Measurement] = []
    skipped: list[Formulation] = []  # recipes of trials that produced no result (filled in Stage 4)

    def log(minute: float, kind: str, message: str, trial: int | None = None, station: str | None = None) -> None:
        events.append(EventRecord(minute, clock.iso(minute), clock.when(minute), kind, trial, station,
                                  clock.attended(minute), message))

    minute = 0.0
    log(minute, "run_started", f"Run started. Strategy: {strategy.description}.")

    trial = 1
    while minute + trial_minutes <= clock.duration_minutes:
        proposal = strategy.propose(trial, tuple(history), tuple(skipped))
        recipe = proposal.formulation.as_dict()
        recipe_text = ", ".join(f"{labels[k]} {v:.1f}%" for k, v in recipe.items())
        log(minute, "decision", f"Trial {trial}: {proposal.reason}. Recipe: {recipe_text}.", trial)

        trial_start = minute
        intervals: list[StepInterval] = []
        measurement: Measurement | None = None
        for step in steps:
            step_start, step_end = minute, minute + step.duration_minutes
            log(step_start, "step_started", f"Trial {trial}: {step.label} started.", trial, step.name)
            intervals.append(StepInterval(step.name, step.label, step_start, step_end, clock.iso(step_start),
                                          clock.iso(step_end), clock.attended(step_start)))
            minute = step_end
            log(step_end, "step_finished", f"Trial {trial}: {step.label} finished.", trial, step.name)
            if step.name == settings.cell.measurement_step:
                measurement = lab.measure(trial, proposal.formulation)
                history.append(measurement)
                good = meets_spec(measurement.dissolution_pct, measurement.hardness_kp, specs)
                log(step_end, "measurement",
                    f"Trial {trial} measured: dissolution {measurement.dissolution_pct:.1f}%, "
                    f"hardness {measurement.hardness_kp:.2f} kP - {'GOOD' if good else 'not good'}.",
                    trial, step.name)
        assert measurement is not None  # settings validation guarantees the measuring step exists

        m = margin(measurement.dissolution_pct, measurement.hardness_kp, specs)
        good = meets_spec(measurement.dissolution_pct, measurement.hardness_kp, specs)
        previous = trials[-1] if trials else None
        trials.append(TrialRecord(
            trial=trial, recipe=recipe, reason=proposal.reason, steps=intervals,
            start_minute=trial_start, end_minute=minute, start=clock.iso(trial_start), end=clock.iso(minute),
            dissolution_pct=measurement.dissolution_pct, hardness_kp=measurement.hardness_kp,
            outcome="Good" if good else "Not good", margin=m,
            best_margin_so_far=max(m, previous.best_margin_so_far) if previous else m,
            good_so_far=(previous.good_so_far if previous else 0) + int(good)))
        log(minute, "trial_completed", f"Trial {trial} completed.", trial)
        trial += 1

    if minute < clock.duration_minutes:
        log(clock.duration_minutes, "run_finished",
            f"Run window ended. Another trial needs {trial_minutes:g} minutes and only "
            f"{clock.duration_minutes - minute:g} remained, so it was not started.")
    else:
        log(clock.duration_minutes, "run_finished", "Run window ended.")

    calendar = clock.calendar()
    summary = _summarise(settings, trials, calendar, clock)
    meta = RunMeta(run_id, settings.display.banner, strategy.name, strategy.description,
                   settings.run.random_seed, clock.iso(0), clock.iso(clock.duration_minutes),
                   clock.duration_minutes)
    return RunRecord(meta, labels, [StepInfo(s.name, s.label, s.duration_minutes) for s in steps],
                     calendar, trials, events, summary)


def _summarise(settings: Settings, trials: list[TrialRecord], calendar, clock: RunClock) -> Summary:
    run_hours = clock.duration_minutes / 60
    unattended_hours = sum(b.end_minute - b.start_minute for b in calendar if not b.staffed) / 60
    per_week = len(trials) / (run_hours / 168)
    baseline = settings.comparison.manual_baseline_trials_per_week
    speedup = per_week / baseline
    good = [t for t in trials if t.outcome == "Good"]
    best = max(trials, key=lambda t: t.margin) if trials else None
    return Summary(
        trials_completed=len(trials),
        trials_good=len(good),
        first_good_trial=good[0].trial if good else None,
        best_trial=best.trial if best else None,
        best_margin=best.margin if best else None,
        run_hours=run_hours,
        unattended_hours=unattended_hours,
        trials_started_unattended=sum(1 for t in trials if not clock.attended(t.start_minute)),
        trials_per_week=round(per_week, 1),
        manual_baseline_trials_per_week=baseline,
        speedup_vs_manual=round(speedup, 1),
        headline=f"{per_week:.1f} trials per week vs {baseline:g} manual ({speedup:.1f}x)",
    )
