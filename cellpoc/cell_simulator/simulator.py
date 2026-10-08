"""The cell simulator: runs trials one after another in simulated time and writes the run record.

It knows nothing about how recipes are chosen or how the tablet really behaves. It asks the
strategy for the next recipe, walks the trial through each step on the clock, asks the lab
for the measurement when the measuring step finishes, applies any scripted faults, and logs
everything in plain English.

Timing rules for a scripted fault (stated here so they are never a surprise):
  * a failed attempt at a step takes that step's full duration, and is found to have failed at the end;
  * the cell then purges for the settings' purge time, then retries the step for its full duration;
  * if the retry works the trial carries on; if not, the candidate is skipped: no later step runs and
    no result exists. When the settings' `clean_after_skip` is on (the default) the cell then still does
    the full cleaning step, with Reason and Adapt as usual; when it is off the next candidate starts at once;
  * a trial is started only if all of it (including its scripted delays) fits before the run ends.
Nothing is adjusted to reach a particular number of trials: the run simply attempts what fits.
"""
from __future__ import annotations

from ..contracts import (
    AlertRecord, EventRecord, Formulation, Lab, Measurement, PhaseInterval, Proposal, RunMeta, RunRecord,
    StepInfo, StepInterval, Strategy, Summary, TrialRecord, margin, meets_spec,
)
from ..settings import Settings
from ..settings.models import ScriptedFault, ScriptedFaults, Step
from .clock import RunClock
from .handover import build_handovers
from .snapshots import build_snapshots


def simulate(settings: Settings, lab: Lab, strategy: Strategy, run_id: str,
             faults: ScriptedFaults | None = None) -> RunRecord:
    """Run the cell for the whole run window. Pass `faults` to apply the scripted faults."""
    return _Simulation(settings, lab, strategy, run_id, faults).run()


class _Simulation:
    def __init__(self, settings: Settings, lab: Lab, strategy: Strategy, run_id: str, faults: ScriptedFaults | None):
        self.settings, self.lab, self.strategy, self.run_id, self.faults = settings, lab, strategy, run_id, faults
        self.clock = RunClock(settings.run, settings.people)
        self.labels = {i.key: i.label for i in settings.design_space.ingredients}
        self.steps = settings.cell.steps
        self.cfg = settings.cell.phases
        self.fault_by_trial = {e.trial: e for e in faults.events} if faults else {}
        self.purge = faults.purge_minutes if faults else 0.0
        self.duration = self.clock.duration_minutes

        self.minute = 0.0
        self.history: list[Measurement] = []
        self.skipped: list[Formulation] = []
        self.trials: list[TrialRecord] = []
        self.events: list[EventRecord] = []
        self.alerts: list[AlertRecord] = []
        self.pending: Proposal | None = None

    # ------------------------------------------------------------------ planning
    def planned_minutes(self, trial: int) -> float:
        """How long the cell will be occupied by this trial, scripted delays included."""
        nominal = self.settings.cell.minutes_per_trial
        fault = self.fault_by_trial.get(trial)
        if fault is None:
            return nominal
        step = self._step(fault.station)
        if fault.retry_succeeds:
            return nominal + self.purge + step.duration_minutes
        before = sum(s.duration_minutes for s in self.steps[: self.steps.index(step)])
        cleaning = self._step(self.cfg.reason_adapt_step).duration_minutes if self.faults.clean_after_skip else 0.0
        return before + step.duration_minutes + self.purge + step.duration_minutes + cleaning

    def fits(self, start: float, trial: int) -> bool:
        return start + self.planned_minutes(trial) <= self.duration

    def _step(self, name: str) -> Step:
        return next(s for s in self.steps if s.name == name)

    # ------------------------------------------------------------------ logging
    def log(self, minute: float, kind: str, message: str, trial: int | None = None, station: str | None = None) -> None:
        self.events.append(EventRecord(minute, self.clock.iso(minute), self.clock.when(minute), kind, trial, station,
                                       self.clock.attended(minute), message))

    def interval(self, step: Step, label: str, kind: str, outcome: str, start: float, end: float,
                 state: str, status_text: str) -> StepInterval:
        return StepInterval(step.name, label, kind, outcome, start, end, self.clock.iso(start), self.clock.iso(end),
                            self.clock.attended(start), state, status_text, look="")

    @staticmethod
    def classify(intervals: list[StepInterval], outcome: str) -> None:
        """Tell charts how to colour each stretch, once the trial's outcome is known."""
        for iv in intervals:
            if iv.kind == "failed_attempt":
                iv.look = "Fault: failed attempt"
            elif iv.kind == "purge":
                iv.look = "Fault: purge"
            elif iv.kind == "retry":
                iv.look = "Fault: retry recovered" if iv.outcome == "completed" else "Fault: retry failed"
            else:
                iv.look = {"Good": "Trial measured good", "Not good": "Trial measured not good"}.get(
                    outcome, "Cleaning after a skipped candidate")

    def recipe_text(self, formulation: Formulation) -> str:
        return ", ".join(f"{self.labels[k]} {v:.1f}%" for k, v in formulation.as_dict().items())

    def decide(self, trial: int, at: float, note: str = "") -> None:
        self.pending = self.strategy.propose(trial, tuple(self.history), tuple(self.skipped))
        self.log(at, "decision", f"Trial {trial}: {self.pending.reason}. Recipe: {self.recipe_text(self.pending.formulation)}.{note}",
                 trial)

    # ------------------------------------------------------------------ the run
    def run(self) -> RunRecord:
        self.log(0, "run_started", f"Run started. Strategy: {self.strategy.description}.")
        if self.fits(0, 1):
            self.decide(1, 0)

        trial = 1
        while self.pending is not None:
            proposal, self.pending = self.pending, None
            self.run_trial(trial, proposal)
            trial += 1

        if self.minute < self.duration:
            needed = self.planned_minutes(trial)
            self.log(self.duration, "run_finished",
                     f"Run window ended. Another trial needs {needed:g} minutes and only "
                     f"{self.duration - self.minute:g} remained, so it was not started.")
        else:
            self.log(self.duration, "run_finished", "Run window ended.")

        calendar = self.clock.calendar()
        handovers = build_handovers(self.clock, calendar, self.trials, self.alerts)
        meta = RunMeta(self.run_id, self.settings.display.banner, self.strategy.name, self.strategy.description,
                       self.settings.run.random_seed, self.clock.iso(0), self.clock.iso(self.duration), self.duration,
                       bool(self.faults and self.faults.events))
        step_info = [StepInfo(s.name, s.label, s.duration_minutes) for s in self.steps]
        snapshots = build_snapshots(self.clock, step_info, self.labels, self.trials, self.events, self.alerts)
        return RunRecord(meta, self.labels, step_info, calendar, self.trials, self.events, self.alerts, handovers,
                         self._summarise(calendar), snapshots)

    def run_trial(self, trial: int, proposal: Proposal) -> None:
        start = self.minute
        intervals: list[StepInterval] = []
        notes: list[str] = []
        measurement: Measurement | None = None
        skipped = False
        reason_interval = adapt_interval = None

        for step in self.steps:
            fault = self.fault_by_trial.get(trial)
            if fault is not None and fault.station == step.name:
                if not self.faulty_step(trial, step, fault, intervals, notes):
                    skipped = True
                    break
                measurement = self.measure_if_due(trial, step, self.minute, proposal.formulation) or measurement
            elif step.name == self.cfg.reason_adapt_step:
                reason_interval, adapt_interval = self.think_step(trial, step, intervals)
            else:
                measurement = self.plain_step(trial, step, intervals, proposal.formulation) or measurement

        if skipped:
            if self.faults is not None and self.faults.clean_after_skip:
                reason_interval, adapt_interval = self.think_step(
                    trial, self._step(self.cfg.reason_adapt_step), intervals, after_skip=True)
            self.finish_skipped(trial, proposal, start, intervals, notes, reason_interval, adapt_interval)
        else:
            assert measurement is not None  # settings validation guarantees the measuring step exists
            self.finish_completed(trial, proposal, start, intervals, notes, measurement, reason_interval, adapt_interval)

    # ------------------------------------------------------------------ steps
    def plain_step(self, trial: int, step: Step, intervals: list[StepInterval], formulation: Formulation) -> Measurement | None:
        s, e = self.minute, self.minute + step.duration_minutes
        self.log(s, "step_started", f"Trial {trial}: {step.label} started.", trial, step.name)
        intervals.append(self.interval(step, step.label, "step", "completed", s, e, "working",
                                       f"{step.label}: trial {trial}"))
        self.minute = e
        self.log(e, "step_finished", f"Trial {trial}: {step.label} finished.", trial, step.name)
        return self.measure_if_due(trial, step, e, formulation)

    def measure_if_due(self, trial: int, step: Step, at: float, formulation: Formulation) -> Measurement | None:
        """If this is the measuring step, take the measurement now that it has finished."""
        if step.name != self.settings.cell.measurement_step:
            return None
        m = self.lab.measure(trial, formulation)
        self.history.append(m)
        good = meets_spec(m.dissolution_pct, m.hardness_kp, self.settings.specifications)
        self.log(at, "measurement", f"Trial {trial} measured: dissolution {m.dissolution_pct:.1f}%, "
                 f"hardness {m.hardness_kp:.2f} kP - {'GOOD' if good else 'not good'}.", trial, step.name)
        return m

    def faulty_step(self, trial: int, step: Step, fault: ScriptedFault, intervals: list[StepInterval],
                    notes: list[str]) -> bool:
        """Failed attempt, purge, retry. Returns True if the retry worked, False if the candidate is skipped."""
        cause = fault.cause
        s = self.minute
        self.log(s, "step_started", f"Trial {trial}: {step.label} started.", trial, step.name)
        e = s + step.duration_minutes
        intervals.append(self.interval(step, f"{step.label} - failed attempt", "failed_attempt", "failed", s, e,
                                       "working", f"{step.label}: trial {trial}"))
        self.minute = e
        self.log(e, "fault", f"Trial {trial}: FAULT - {cause} at {step.label}. The attempt failed.", trial, step.name)

        p_end = e + self.purge
        self.log(e, "purge_started", f"Trial {trial}: purging and resetting {step.label.lower()} ({self.purge:g} min).",
                 trial, step.name)
        intervals.append(self.interval(step, "Purge", "purge", "completed", e, p_end, "purge",
                                       f"Purging after {cause}: trial {trial}"))
        self.minute = p_end
        self.log(p_end, "purge_finished", f"Trial {trial}: purge finished.", trial, step.name)

        r_end = p_end + step.duration_minutes
        self.log(p_end, "step_started", f"Trial {trial}: {step.label} retry started.", trial, step.name)
        self.minute = r_end
        if fault.retry_succeeds:
            intervals.append(self.interval(step, f"{step.label} - retry", "retry", "completed", p_end, r_end, "retry",
                                           f"{step.label} retry after the purge: trial {trial}"))
            self.log(r_end, "recovery", f"Trial {trial}: RECOVERED - the {step.label.lower()} retry succeeded. {fault.alert}.",
                     trial, step.name)
            notes.append(f"{cause.capitalize()} at {step.label}: purged for {self.purge:g} min and retried successfully.")
            self.alerts.append(AlertRecord(r_end, self.clock.iso(r_end), self.clock.when(r_end), trial, "Recovered",
                                           f"{cause.capitalize()} (recovered)", fault.alert, False, None, None))
            self.log(r_end, "step_finished", f"Trial {trial}: {step.label} finished.", trial, step.name)
            return True

        intervals.append(self.interval(step, f"{step.label} - retry failed", "retry", "failed", p_end, r_end, "retry",
                                       f"{step.label} retry after the purge: trial {trial}"))
        self.log(r_end, "retry_failed", f"Trial {trial}: the {step.label.lower()} retry also FAILED.", trial, step.name)
        self.log(r_end, "candidate_skipped",
                 f"Trial {trial}: candidate SKIPPED - no tablets were made and no result exists.", trial, step.name)
        arrives = self.clock.next_staffed_start(r_end)
        when = self.clock.when(arrives) if arrives is not None else "the next working day (after this run ends)"
        notes.append(f"{cause.capitalize()} at {step.label}: purged for {self.purge:g} min but the retry also failed. "
                     f"The candidate was skipped and has no result. Alert queued for {when}.")
        self.alerts.append(AlertRecord(r_end, self.clock.iso(r_end), self.clock.when(r_end), trial, "Needs attention",
                                       f"{cause.capitalize()} (candidate skipped)", fault.alert, True, when, arrives))
        self.log(r_end, "alert_queued", f"Trial {trial}: ALERT queued for {when}: {fault.alert}.", trial, step.name)
        return False

    def think_step(self, trial: int, step: Step, intervals: list[StepInterval],
                   after_skip: bool = False) -> tuple[tuple[float, float], tuple[float, float]]:
        """The final step (cleaning): the first part is Reason (choose the next recipe), the rest is Adapt."""
        s, e = self.minute, self.minute + step.duration_minutes
        reason_end = s + self.cfg.reason_minutes
        self.log(s, "step_started", f"Trial {trial}: {step.label} started" + (" (after the skipped candidate)." if after_skip else "."),
                 trial, step.name)
        text = (f"{step.label}: cleaning after the skipped candidate (trial {trial})" if after_skip
                else f"{step.label}: trial {trial}")
        intervals.append(self.interval(step, step.label, "step", "completed", s, e, "working", text))
        if self.fits(e, trial + 1):
            self.decide(trial + 1, reason_end)
        self.minute = e
        self.log(e, "step_finished", f"Trial {trial}: {step.label} finished.", trial, step.name)
        return (s, reason_end), (reason_end, e)

    # ------------------------------------------------------------------ closing a trial
    def phase(self, name: str, start: float, end: float, status: str, text: str) -> PhaseInterval:
        return PhaseInterval(name, start, end, self.clock.iso(start), self.clock.iso(end), status, text)

    def finish_completed(self, trial, proposal, start, intervals, notes, m: Measurement, reason_iv, adapt_iv) -> None:
        specs = self.settings.specifications
        good = meets_spec(m.dissolution_pct, m.hardness_kp, specs)
        mar = margin(m.dissolution_pct, m.hardness_kp, specs)
        previous = next((t for t in reversed(self.trials) if t.margin is not None), None)
        best_so_far = max(mar, previous.best_margin_so_far) if previous else mar
        good_so_far = (self.trials[-1].good_so_far if self.trials else 0) + int(good)

        def span(names):
            chosen = [i for i in intervals if i.step in names]
            return min(i.start_minute for i in chosen), max(i.end_minute for i in chosen)

        act = span(self.cfg.act)
        sense = span(self.cfg.sense)
        act_labels = ", ".join(self._step(n).label.lower() for n in self.cfg.act)
        act_text = f"Made the tablets ({act_labels})." + ("".join(" " + n for n in notes))
        nxt = self.pending
        n_results = len(self.history)
        if nxt is not None:
            reason_text = f"Reviewed {n_results} result(s) and chose the recipe for trial {trial + 1}. {nxt.reason}."
            adapt_text = (f"Finished the {self.cfg.reason_adapt_step} step and loaded the recipe for trial {trial + 1}: "
                          f"{self.recipe_text(nxt.formulation)}.")
        else:
            reason_text = f"Reviewed {n_results} result(s). No further trial fits before the run ends."
            adapt_text = f"Finished the {self.cfg.reason_adapt_step} step. The run window is closing."
        phases = [
            self.phase("Act", *act, "completed", act_text),
            self.phase("Sense", *sense, "completed",
                       f"Measured dissolution {m.dissolution_pct:.1f}% and hardness {m.hardness_kp:.2f} kP: "
                       f"{'good' if good else 'not good'}."),
            self.phase("Reason", *reason_iv, "completed", reason_text),
            self.phase("Adapt", *adapt_iv, "completed", adapt_text),
        ]
        self.classify(intervals, "Good" if good else "Not good")
        self.trials.append(TrialRecord(
            trial=trial, recipe=proposal.formulation.as_dict(), reason=proposal.reason, status="Completed",
            steps=intervals, phases=phases, start_minute=start, end_minute=self.minute,
            start=self.clock.iso(start), end=self.clock.iso(self.minute),
            dissolution_pct=m.dissolution_pct, hardness_kp=m.hardness_kp, outcome="Good" if good else "Not good",
            margin=mar, best_margin_so_far=best_so_far, good_so_far=good_so_far, notes=notes))
        self.log(self.minute, "trial_completed", f"Trial {trial} completed.", trial)

    def finish_skipped(self, trial, proposal, start, intervals, notes, reason_iv=None, adapt_iv=None) -> None:
        self.skipped.append(proposal.formulation)
        last = next((t for t in reversed(self.trials) if t.margin is not None), None)
        think = self.cfg.reason_adapt_step
        act_end = max(i.end_minute for i in intervals if i.step != think)
        phases = [self.phase("Act", start, act_end, "failed", "Tried to make the tablets. " + " ".join(notes))]
        if reason_iv is not None:  # cleaning followed the skip, so Reason and Adapt happen as usual
            nxt = self.pending
            n_results = len(self.history)
            if nxt is not None:
                reason_text = (f"Trial {trial} gave no result to learn from. Reviewed {n_results} result(s) and chose the "
                               f"recipe for trial {trial + 1}. {nxt.reason}.")
                adapt_text = (f"Finished the {think} step and loaded the recipe for trial {trial + 1}: "
                              f"{self.recipe_text(nxt.formulation)}.")
            else:
                reason_text = f"Reviewed {n_results} result(s). No further trial fits before the run ends."
                adapt_text = f"Finished the {think} step. The run window is closing."
            phases += [self.phase("Reason", *reason_iv, "completed", reason_text),
                       self.phase("Adapt", *adapt_iv, "completed", adapt_text)]
        self.classify(intervals, "No result")
        self.trials.append(TrialRecord(
            trial=trial, recipe=proposal.formulation.as_dict(), reason=proposal.reason, status="Skipped",
            steps=intervals, phases=phases, start_minute=start, end_minute=self.minute,
            start=self.clock.iso(start), end=self.clock.iso(self.minute),
            dissolution_pct=None, hardness_kp=None, outcome="No result", margin=None,
            best_margin_so_far=last.best_margin_so_far if last else None,
            good_so_far=self.trials[-1].good_so_far if self.trials else 0, notes=notes))
        self.log(self.minute, "trial_completed", f"Trial {trial} ended without a result (candidate skipped).", trial)
        if reason_iv is None and self.fits(self.minute, trial + 1):  # no cleaning: decide straight away
            self.decide(trial + 1, self.minute,
                        f" (Decided straight away: trial {trial} produced no result to learn from.)")

    # ------------------------------------------------------------------ summary
    def _summarise(self, calendar) -> Summary:
        trials = self.trials
        with_result = [t for t in trials if t.status == "Completed"]
        good = [t for t in with_result if t.outcome == "Good"]
        best = max(with_result, key=lambda t: t.margin) if with_result else None  # type: ignore[arg-type,return-value]
        run_hours = self.duration / 60
        unattended_hours = sum(b.end_minute - b.start_minute for b in calendar if not b.staffed) / 60
        per_week = len(with_result) / (run_hours / 168)
        baseline = self.settings.comparison.manual_baseline_trials_per_week
        speedup = per_week / baseline
        for_staff = sum(1 for a in self.alerts if a.needs_human)
        return Summary(
            trials_attempted=len(trials), trials_with_result=len(with_result),
            trials_skipped=len(trials) - len(with_result), trials_good=len(good),
            first_good_trial=good[0].trial if good else None,
            best_trial=best.trial if best else None, best_margin=best.margin if best else None,
            run_hours=run_hours, unattended_hours=unattended_hours,
            trials_started_unattended=sum(1 for t in trials if not self.clock.attended(t.start_minute)),
            faults_recovered=sum(1 for a in self.alerts if not a.needs_human), alerts_for_staff=for_staff,
            trials_per_week=round(per_week, 1), manual_baseline_trials_per_week=baseline,
            speedup_vs_manual=round(speedup, 1),
            headline=f"{per_week:.1f} trials with results per week vs {baseline:g} manual ({speedup:.1f}x)",
            attempts_text=f"{len(trials)} attempted: {len(with_result)} with a result, {len(trials) - len(with_result)} skipped")
