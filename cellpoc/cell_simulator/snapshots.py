"""Works out, in advance, what the dashboard shows at every moment of the run.

The dashboard's time slider only picks one of these snapshots and displays it, so all the
reasoning about "what is happening at this moment" lives here, not in the dashboard.
Snapshots exist every `grid_minutes` and at every instant something is logged, so that
"next event" and "previous event" land exactly on events.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right

from ..contracts import (
    AlertRecord, EventRecord, PhaseState, Snapshot, StationStatus, StepInfo, TrialRecord,
)
from .clock import RunClock

PHASES = ("Act", "Sense", "Reason", "Adapt")
RECENT = 5


def _result_known_at(trial: TrialRecord) -> float:
    """The moment this trial's outcome (a result, or the news that there will be none) becomes known."""
    wanted = "Sense" if trial.status == "Completed" else "Act"
    return next(p.end_minute for p in trial.phases if p.phase == wanted)


def build_snapshots(clock: RunClock, steps: list[StepInfo], labels: dict[str, str], trials: list[TrialRecord],
                    events: list[EventRecord], alerts: list[AlertRecord], grid_minutes: int = 15) -> list[Snapshot]:
    duration = clock.duration_minutes
    event_minutes = sorted({e.minute for e in events})
    minutes = sorted({float(m) for m in range(0, duration + 1, grid_minutes)} | set(event_minutes))
    index_of = {m: i for i, m in enumerate(minutes)}
    event_set = set(event_minutes)
    stretches = [(i.start_minute, i.end_minute, i.step, i) for t in trials for i in t.steps]
    known_at = {t.trial: _result_known_at(t) for t in trials}

    snapshots: list[Snapshot] = []
    for index, m in enumerate(minutes):
        stations = []
        for step in steps:
            hit = next((iv for s, e, name, iv in stretches if name == step.name and s <= m < e), None)
            stations.append(StationStatus(step.label, hit.state, hit.status_text) if hit
                            else StationStatus(step.label, "idle", "Idle"))

        trial = next((t for t in trials if t.start_minute <= m < t.end_minute), None)
        results = [t for t in trials if t.status == "Completed" and known_at[t.trial] <= m]
        best = max(results, key=lambda t: t.margin) if results else None  # type: ignore[arg-type,return-value]
        so_far = [e for e in events if e.minute <= m]
        before = bisect_left(event_minutes, m)
        after = bisect_right(event_minutes, m)

        if trial is not None:
            headline = f"Trial {trial.trial}"
            recipe = [f"{labels[k]}: {v:.1f}%" for k, v in trial.recipe.items()]
            phases = _phase_states(trial, m)
            active = next((p.phase for p in phases if p.state == "active"), None)
            kind, text = _result(trial, m, known_at[trial.trial], clock)
            why = trial.reason
        else:
            ended = m >= duration
            headline = ("Run finished: the window has closed" if ended
                        else "No trial is running: no further trial fits before the run ends")
            recipe, why, active = [], "", None
            phases = [PhaseState(p, "waiting", "Not running") for p in PHASES]
            kind, text = "none", ""

        snapshots.append(Snapshot(
            index=index, minute=m, time=clock.iso(m), when=clock.when(m),
            staff_present=clock.attended(m),
            staff_text=("Someone is in the lab" if clock.attended(m)
                        else "Nobody is in the lab: the cell is running on its own"),
            stations=stations, trial=trial.trial if trial else None, trial_headline=headline,
            recipe_lines=recipe, why=why, active_phase=active, phases=phases, result_kind=kind, result_text=text,
            trials_finished=sum(1 for t in trials if t.end_minute <= m), results_so_far=len(results),
            good_so_far=sum(1 for t in results if t.outcome == "Good"),
            best_text=(f"Best result so far: trial {best.trial} (dissolution {best.dissolution_pct:.1f}%, "
                       f"hardness {best.hardness_kp:.2f} kP)" if best else "No result yet"),
            alerts_so_far=[_alert_text(a, m) for a in alerts if a.minute <= m],
            just_happened=[e.message for e in so_far if e.minute == m],
            recent_events=[f"{e.when} - {e.message}" for e in reversed(so_far)][:RECENT],
            is_event=m in event_set,
            previous_event_index=index_of[event_minutes[before - 1]] if before > 0 else None,
            next_event_index=index_of[event_minutes[after]] if after < len(event_minutes) else None))
    return snapshots


# What a phase says about itself while it is still going on. The full description (which states the
# outcome: the measured numbers, a fault, the next recipe) is shown only once the phase is over.
_WHILE_ACTIVE = {
    "Act": "Making the tablets.",
    "Sense": "Measuring the tablets. The result arrives when the test finishes.",
    "Reason": "Reviewing every result so far to choose the next recipe.",
    "Adapt": "Finishing the cleaning step and getting ready for the next recipe.",
}


def _phase_states(trial: TrialRecord, m: float) -> list[PhaseState]:
    by_name = {p.phase: p for p in trial.phases}
    states = []
    for name in PHASES:
        p = by_name.get(name)
        if p is None:
            states.append(PhaseState(name, "not_reached", "Not reached: this trial produced no result"))
        elif m >= p.end_minute:
            states.append(PhaseState(name, "failed" if p.status == "failed" else "done", p.description))
        elif m >= p.start_minute:
            states.append(PhaseState(name, "active", _WHILE_ACTIVE[name]))
        else:
            states.append(PhaseState(name, "waiting", "Not started yet"))
    return states


def _result(trial: TrialRecord, m: float, known_at: float, clock: RunClock) -> tuple[str, str]:
    """(kind, text). The numbers appear only once the result is actually known."""
    if m < known_at:
        when = clock.when(known_at)
        return "pending", (f"Not known yet. The result arrives when the test finishes at {when}."
                           if trial.status == "Completed" else "Not known yet.")
    if trial.status == "Skipped":
        return "no_result", "No result: this candidate was skipped, so no tablets were made."
    verdict = "GOOD: meets both specifications" if trial.outcome == "Good" else "Not good: misses a specification"
    kind = "good" if trial.outcome == "Good" else "not_good"
    return kind, (f"Dissolution {trial.dissolution_pct:.1f}% and hardness {trial.hardness_kp:.2f} kP. {verdict}.")


def _alert_text(a: AlertRecord, m: float) -> str:
    if not a.needs_human:
        return f"{a.when} - RECOVERED - {a.message}."
    if a.queued_for_minute is None:
        return f"{a.when} - NEEDS ATTENTION - {a.message}. Waiting for staff (nobody is due before the run ends)."
    if m >= a.queued_for_minute:
        return f"{a.when} - NEEDS ATTENTION - {a.message}. Staff arrived at {a.queued_for} and the alert is in front of them."
    return f"{a.when} - NEEDS ATTENTION - {a.message}. Waiting for staff, queued for {a.queued_for}."
