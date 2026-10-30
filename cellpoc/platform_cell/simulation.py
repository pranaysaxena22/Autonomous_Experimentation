"""The configurable cell simulator (Stage 5): the proof of concept's simulator with the setup's plan, the executor and the setup's faults plugged in.

It reuses the proof of concept's simulation class (the clock, the staffing calendar, the decision log, the events, alerts, handovers, snapshots and the run record) and replaces only HOW A TRIAL IS RUN:
- each trial is planned (the motion planner turns the recipe, the setup and the layout into a plan) and run by an executor, which returns what truly happened; the trial's steps, events and alerts are read from that
  executed timeline, so a step takes the time its actions took, a fault costs what its recovery actions cost (not the proof of concept's "a whole step, a purge and a whole step again"), and the timings come from the setup;
- faults come from the setup, scripted (on a named trial) and random (by chance, from a stream that depends only on the seed and the trial);
- the next trial is started only if all of it, delays included, fits before the run ends: the recipe is chosen, planned and run through the executor without readings to learn how long it will take, and dropped if it does not fit;
- the lab's measurement is taken when the measuring step has finished, and an instrument reading in the timeline comes from it.
The output is an ordinary run record (the existing dashboard can read it) plus the plans and the executed timelines of every trial. It knows nothing about the hidden truth of the lab: it asks the injected lab to measure, as the
proof of concept does. A trial with a fault in the cleaning step is not supported.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..cell_simulator.simulator import _Simulation          # the proof of concept's own simulation class, reused so that nothing in the record's meaning changes
from ..contracts import AlertRecord, Formulation, Lab, Measurement, Proposal, RunRecord, Strategy, StepInterval, meets_spec
from ..executor import Executor, Fault, ReadingProvider, fault_for_trial
from ..planner import plan_trial
from ..settings import Settings
from ..settings.models import ScriptedFaults

POC_INGREDIENTS = {"drug_pct": "drug", "filler_pct": "filler", "binder_pct": "binder", "disintegrant_pct": "disintegrant", "lubricant_pct": "lubricant"}      # the setup's ingredient ids and the proof of concept's names
POC_STEP_NAMES = {"mix": "blend"}                                                                                                                         # the setup says 'mix', the proof of concept 'blend'
PLATFORM_STEP_NAMES = {v: k for k, v in POC_STEP_NAMES.items()}


def alert_text(cause: str, trial: int, retry_succeeds: bool) -> str:
    outcome = "purged and retried successfully" if retry_succeeds else "retry failed, candidate skipped"
    return f"{cause[:1].upper() + cause[1:]} on trial {trial} - {outcome}"


def scan_alert_text(cause: str, trial: int, retry_succeeds: bool) -> str:
    """The alert for a fault at the barcode scan: nothing is purged (no powder is involved); the vial is turned and read again, or, for a different vial, put back."""
    if retry_succeeds:
        return f"{cause[:1].upper() + cause[1:]} on trial {trial} - the vial was turned and rescanned successfully"
    if "wrong" in cause:
        return f"{cause[:1].upper() + cause[1:]} on trial {trial} - a different vial was in the gripper, so the candidate was skipped: a person must check the rack"
    return f"{cause[:1].upper() + cause[1:]} on trial {trial} - the label could not be read even after rescanning, so the candidate was skipped"


@dataclass
class PlatformRun:
    """A run record plus what the platform adds to it: every trial's plan and executed timeline."""
    record: RunRecord
    plans: list[dict] = field(default_factory=list)
    executed: list[dict] = field(default_factory=list)
    layout: dict = field(default_factory=dict)
    setup: dict = field(default_factory=dict)


class LabReadings:
    """Instrument numbers for one trial, taken from the injected lab the first time one is needed (once, so every reading belongs to the same measurement)."""

    real = True                                                          # these readings belong to a real run of a trial (the run without readings, which only learns how long a trial will take, has no such mark)

    def __init__(self, lab: Lab, trial: int, formulation: Formulation):
        self._lab, self._trial, self._formulation = lab, trial, formulation
        self._m: Measurement | None = None

    def measurement(self) -> Measurement:
        if self._m is None:
            self._m = self._lab.measure(self._trial, self._formulation)
        return self._m

    def reading(self, quantity: str) -> float | None:
        m = self.measurement()
        return {"dissolution_30min_pct": m.dissolution_pct, "hardness_kp": m.hardness_kp}.get(quantity)          # the proof of concept's lab does not measure friability


class PlatformSimulation(_Simulation):
    def __init__(self, settings: Settings, setup: dict, layout: dict, lab: Lab, strategy: Strategy, run_id: str, executor: Executor, world=None):
        """`world`, when given (the connected loop, cellpoc/connected), supplies a proposal's whole recipe, the process settings too, with `recipe_for(formulation)`, and a trial's readings with `readings(trial, formulation)`.
        Without it a trial's recipe is the proposal's five ingredients with the process settings at the middle of their ranges, and its readings come from the injected lab."""
        clean = bool(setup["faults"]["clean_after_skip"])
        super().__init__(settings, lab, strategy, run_id, ScriptedFaults(setup["faults"]["purge_min"], (), clean))
        self.setup, self.layout, self.executor, self.clean_after_skip, self.world = setup, layout, executor, clean, world
        self.seed = int(setup["seeds"]["run"])
        self.plans: list[dict] = []
        self.executed: list[dict] = []
        self._needed: float | None = None
        self._middle = {p["id"]: (p["min"] + p["max"]) / 2 for p in setup["process_factors"]}
        self._step_label = {PLATFORM_STEP_NAMES.get(s.name, s.name): s.label for s in self.steps}

    # ------------------------------------------------------------------ the recipe, the plan and the fault
    def recipe_of(self, formulation: Formulation) -> dict:
        """The platform recipe for a proof-of-concept formulation: the five percentages, and the middle of each process setting (the proof of concept's strategies do not choose them)."""
        if self.world is not None:
            return self.world.recipe_for(formulation)
        percent = formulation.as_dict()
        recipe = {platform_id: percent[poc] for platform_id, poc in POC_INGREDIENTS.items()}
        recipe.update(self._middle)
        return recipe

    def fault_for(self, trial: int) -> Fault | None:
        return fault_for_trial(self.setup, trial, self.seed)

    def plan_and_run(self, trial: int, start_minute: float, formulation: Formulation, why: str, readings: ReadingProvider, fault: Fault | None) -> tuple[dict, dict]:
        plan = plan_trial(self.setup, self.layout, self.recipe_of(formulation), trial, start_minute, why, rescale=True)      # the proof of concept's ingredient levels do not add up to 100%: the planner scales them to a batch and says so
        return plan, self.executor.execute(plan, self.setup, self.layout, fault, readings, self.clean_after_skip, plan_file=f"plans/{plan['plan_id']}.json")

    @staticmethod
    def seconds(executed: dict) -> int:
        last = executed["actions"][-1]
        return last["actual_start_s"] + last["actual_duration_s"]

    # ------------------------------------------------------------------ the next trial must fit before the run ends
    def fits(self, start: float, trial: int) -> bool:                        # the real test is in decide(): it needs the recipe
        return True

    def planned_minutes(self, trial: int) -> float:
        return self._needed if self._needed is not None else self.settings.cell.minutes_per_trial

    def decide(self, trial: int, at: float, note: str = "") -> None:
        """Choose the next recipe, run it through the planner and the executor without readings to learn how long it will take, and keep it only if it fits before the run ends. `at` is when the decision is made;
        the trial starts at `at` unless the cleaning step is still to finish (decide_after handles that case)."""
        self.decide_after(trial, at, at, note)

    def decide_after(self, trial: int, at: float, start: float, note: str = "") -> None:
        proposal = self.strategy.propose(trial, tuple(self.history), tuple(self.skipped))
        _, dry = self.plan_and_run(trial, start, proposal.formulation, proposal.reason, _NoNumbers(), self.fault_for(trial))
        minutes = self.seconds(dry) / 60
        if start + minutes <= self.duration:
            self.pending = proposal
            self.log(at, "decision", f"Trial {trial}: {proposal.reason}. Recipe: {self.recipe_text(proposal.formulation)}.{note}", trial)
        else:
            self.pending, self._needed = None, minutes

    # ------------------------------------------------------------------ one trial, read from the executed timeline
    def run_trial(self, trial: int, proposal: Proposal) -> None:
        start = self.minute
        fault = self.fault_for(trial)
        readings = self.world.readings(trial, proposal.formulation) if self.world is not None else LabReadings(self.lab, trial, proposal.formulation)
        plan, executed = self.plan_and_run(trial, start, proposal.formulation, proposal.reason, readings, fault)
        self.plans.append(plan)
        self.executed.append(executed)
        at = lambda seconds: start + seconds / 60.0
        intervals: list[StepInterval] = []
        notes: list[str] = []
        measurement: Measurement | None = None
        reason_interval = adapt_interval = None
        skipped = executed["outcome"] == "skipped"
        actions = executed["actions"]

        for step in self.steps:
            name = PLATFORM_STEP_NAMES.get(step.name, step.name)
            mine = [a for a in actions if a["step"] == name]
            if not mine:
                continue                                                      # a step that never ran (the candidate was skipped before it)
            s, e = at(mine[0]["actual_start_s"]), at(mine[-1]["actual_start_s"] + mine[-1]["actual_duration_s"])
            faulted = bool(executed["faults"]) and executed["faults"][0]["where"]["step"] == name
            if name == self.cfg.reason_adapt_step:
                reason_interval, adapt_interval = self.clean_step(trial, step, s, e, skipped)
                intervals.append(self.interval(step, step.label, "step", "completed", s, e, "working",
                                               f"Cleaning after the skipped candidate (trial {trial})" if skipped else f"{step.label}: trial {trial}"))
                self.minute = e
                continue
            if faulted:
                self.faulted_step(trial, step, s, e, mine, executed, intervals, notes)
            else:
                self.log(s, "step_started", f"Trial {trial}: {step.label} started.", trial, step.name)
                intervals.append(self.interval(step, step.label, "step", "completed", s, e, "working", f"{step.label}: trial {trial}"))
                self.log(e, "step_finished", f"Trial {trial}: {step.label} finished.", trial, step.name)
            self.minute = e
            if step.name == self.settings.cell.measurement_step and not skipped:
                measurement = readings.measurement()
                self.history.append(measurement)
                good = meets_spec(measurement.dissolution_pct, measurement.hardness_kp, self.settings.specifications)
                self.log(e, "measurement", f"Trial {trial} measured: dissolution {measurement.dissolution_pct:.1f}%, hardness {measurement.hardness_kp:.2f} kP - {'GOOD' if good else 'not good'}.", trial, step.name)
        self.minute = at(self.seconds(executed))
        if skipped:
            self.finish_skipped(trial, proposal, start, intervals, notes, reason_interval, adapt_interval)
        else:
            assert measurement is not None                                    # the plan always has a test step with its reads
            self.finish_completed(trial, proposal, start, intervals, notes, measurement, reason_interval, adapt_interval)

    def clean_step(self, trial: int, step, s: float, e: float, after_skip: bool):
        """The last step: the first part is Reason (the next recipe is chosen), the rest is Adapt."""
        reason_end = s + self.cfg.reason_minutes
        self.log(s, "step_started", f"Trial {trial}: {step.label} started" + (" (after the skipped candidate)." if after_skip else "."), trial, step.name)
        self.decide_after(trial + 1, reason_end, e)
        self.log(e, "step_finished", f"Trial {trial}: {step.label} finished.", trial, step.name)
        return (s, reason_end), (reason_end, e)

    def faulted_step(self, trial: int, step, s: float, e: float, mine: list[dict], executed: dict, intervals: list[StepInterval], notes: list[str]) -> None:
        """A step with a fault: the failed attempt, the recovery (tap and shake, put back, purge) and the retry with the rest of the step, in the proof of concept's three kinds of stretch."""
        fault = executed["faults"][0]
        cause, label = fault["cause"], step.label
        start = s - mine[0]["actual_start_s"] / 60.0                          # the trial's start minute
        failed = next(a for a in mine if a["id"] == fault["action_id"])
        if failed["type"] == "scan":                                          # a barcode fault has no purge: the vial is turned and read again (or put back)
            self.faulted_scan_step(trial, step, s, e, start, failed, mine, fault, intervals, notes)
            return
        recovery = [a for a in mine if a["origin"] == "recovery"]
        tf = start + (failed["actual_start_s"] + failed["actual_duration_s"]) / 60.0
        purge = next(a for a in recovery if a["type"] == "wait")
        pe = start + (purge["actual_start_s"] + purge["actual_duration_s"]) / 60.0
        purge_min = self.setup["faults"]["purge_min"]
        retry_ok = fault["recovered"]
        self.log(s, "step_started", f"Trial {trial}: {label} started.", trial, step.name)
        intervals.append(self.interval(step, f"{label} - failed attempt", "failed_attempt", "failed", s, tf, "working", f"{label}: trial {trial}"))
        self.log(tf, "fault", f"Trial {trial}: FAULT - {cause} at {label}. The attempt failed.", trial, step.name)
        self.log(tf, "purge_started", f"Trial {trial}: purging and resetting {label.lower()} ({purge_min:g} min).", trial, step.name)
        intervals.append(self.interval(step, "Purge", "purge", "completed", tf, pe, "purge", f"Purging after {cause}: trial {trial}"))
        self.log(pe, "purge_finished", f"Trial {trial}: purge finished.", trial, step.name)
        self.log(pe, "step_started", f"Trial {trial}: {label} retry started.", trial, step.name)
        text = alert_text(cause, trial, retry_ok)
        if retry_ok:
            intervals.append(self.interval(step, f"{label} - retry", "retry", "completed", pe, e, "retry", f"{label} retry after the purge: trial {trial}"))
            retry = next(a for a in reversed(recovery) if a["outcome"] == "ok")
            re_ = start + (retry["actual_start_s"] + retry["actual_duration_s"]) / 60.0
            self.log(re_, "recovery", f"Trial {trial}: RECOVERED - the {label.lower()} retry succeeded. {text}.", trial, step.name)
            notes.append(f"{cause.capitalize()} at {label}: purged for {purge_min:g} min and retried successfully.")
            self.alerts.append(AlertRecord(re_, self.clock.iso(re_), self.clock.when(re_), trial, "Recovered", f"{cause.capitalize()} (recovered)", text, False, None, None))
            self.log(e, "step_finished", f"Trial {trial}: {label} finished.", trial, step.name)
            return
        intervals.append(self.interval(step, f"{label} - retry failed", "retry", "failed", pe, e, "retry", f"{label} retry after the purge: trial {trial}"))
        self.log(e, "retry_failed", f"Trial {trial}: the {label.lower()} retry also FAILED.", trial, step.name)
        self.log(e, "candidate_skipped", f"Trial {trial}: candidate SKIPPED - no tablets were made and no result exists.", trial, step.name)
        arrives = self.clock.next_staffed_start(e)
        when = self.clock.when(arrives) if arrives is not None else "the next working day (after this run ends)"
        notes.append(f"{cause.capitalize()} at {label}: purged for {purge_min:g} min but the retry also failed. The candidate was skipped and has no result. Alert queued for {when}.")
        self.alerts.append(AlertRecord(e, self.clock.iso(e), self.clock.when(e), trial, "Needs attention", f"{cause.capitalize()} (candidate skipped)", text, True, when, arrives))
        self.log(e, "alert_queued", f"Trial {trial}: ALERT queued for {when}: {text}.", trial, step.name)

    def faulted_scan_step(self, trial: int, step, s: float, e: float, start: float, failed: dict, mine: list[dict], fault: dict, intervals: list[StepInterval], notes: list[str]) -> None:
        """A step whose barcode scan went wrong: the failed attempt, then either the rescan that worked, or (an unreadable label that stayed unreadable, or a different vial) the candidate skipped. No purge."""
        cause, label, retry_ok = fault["cause"], step.label, fault["recovered"]
        tf = start + (failed["actual_start_s"] + failed["actual_duration_s"]) / 60.0
        text = scan_alert_text(cause, trial, retry_ok)
        rescanned = any(a["origin"] == "recovery" and a["type"] == "scan" for a in mine)
        self.log(s, "step_started", f"Trial {trial}: {label} started.", trial, step.name)
        intervals.append(self.interval(step, f"{label} - failed attempt", "failed_attempt", "failed", s, tf, "working", f"{label}: trial {trial}"))
        self.log(tf, "fault", f"Trial {trial}: FAULT - {cause} at {label}. The vial's label was not accepted.", trial, step.name)
        if retry_ok:
            self.log(tf, "step_started", f"Trial {trial}: turning the vial and scanning again.", trial, step.name)
            intervals.append(self.interval(step, f"{label} - rescan", "retry", "completed", tf, e, "retry", f"Turning the vial and scanning again: trial {trial}"))
            again = next(a for a in reversed([x for x in mine if x["origin"] == "recovery"]) if a["type"] == "scan" and a["outcome"] == "ok")
            re_ = start + (again["actual_start_s"] + again["actual_duration_s"]) / 60.0
            self.log(re_, "recovery", f"Trial {trial}: RECOVERED - the rescan read the right label. {text}.", trial, step.name)
            notes.append(f"{cause.capitalize()} at {label}: the vial was turned and rescanned successfully.")
            self.alerts.append(AlertRecord(re_, self.clock.iso(re_), self.clock.when(re_), trial, "Recovered", f"{cause.capitalize()} (recovered)", text, False, None, None))
            self.log(e, "step_finished", f"Trial {trial}: {label} finished.", trial, step.name)
            return
        intervals.append(self.interval(step, f"{label} - " + ("rescan failed" if rescanned else "vial put back"), "retry", "failed", tf, e, "retry", (f"Turning the vial and scanning again: trial {trial}" if rescanned else f"Putting the wrong vial back: trial {trial}")))
        if rescanned:
            self.log(e, "retry_failed", f"Trial {trial}: the rescan also FAILED.", trial, step.name)
        self.log(e, "candidate_skipped", f"Trial {trial}: candidate SKIPPED - no tablets were made and no result exists.", trial, step.name)
        arrives = self.clock.next_staffed_start(e)
        when = self.clock.when(arrives) if arrives is not None else "the next working day (after this run ends)"
        notes.append(f"{cause.capitalize()} at {label}: the candidate was skipped and has no result. Alert queued for {when}.")
        self.alerts.append(AlertRecord(e, self.clock.iso(e), self.clock.when(e), trial, "Needs attention", f"{cause.capitalize()} (candidate skipped)", text, True, when, arrives))
        self.log(e, "alert_queued", f"Trial {trial}: ALERT queued for {when}: {text}.", trial, step.name)

    # ------------------------------------------------------------------ the whole run
    def run_platform(self) -> PlatformRun:
        record = self.run()
        record.meta.faults_applied = any(x["faults"] for x in self.executed)
        return PlatformRun(record, self.plans, self.executed, self.layout, self.setup)


class _NoNumbers:
    """No instrument numbers: used only to learn how long a trial will take."""

    def reading(self, quantity: str) -> float | None:
        return None
