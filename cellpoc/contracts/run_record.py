"""The run record: everything the dashboard needs to show a finished run, already worked out.

Written by the cell simulator, read by the dashboard. Times are given three ways so that
nothing downstream has to calculate: `minute` (minutes since the run began), `time`
(ISO date-time, for charts) and `when` (a label for people, e.g. "Fri 09 Oct 18:00").
"""
from __future__ import annotations

from dataclasses import dataclass

from .comparison_record import ComparisonResult


@dataclass
class RunMeta:
    run_id: str
    banner: str                   # e.g. "Simulation with illustrative values"
    strategy_name: str
    strategy_description: str
    random_seed: int
    start: str
    end: str
    duration_minutes: int
    faults_applied: bool


@dataclass
class StepInfo:
    name: str
    label: str
    duration_minutes: float


@dataclass
class CalendarBlock:
    """A stretch of the run when the lab is staffed or empty (for night/weekend shading)."""
    start_minute: int
    end_minute: int
    start: str
    end: str
    staffed: bool
    label: str                    # "Staffed" or "Unattended"


@dataclass
class StepInterval:
    """One stretch of work at one station. A fault adds a failed attempt, a purge and a retry."""
    step: str                     # the station / step name
    label: str                    # e.g. "Dispense", "Dispense - failed attempt", "Purge", "Dispense - retry"
    kind: str                     # step, failed_attempt, purge, retry
    outcome: str                  # completed or failed
    start_minute: float
    end_minute: float
    start: str
    end: str
    attended: bool                # was someone in the lab when it began


@dataclass
class PhaseInterval:
    """Sense / Reason / Act / Adapt for one trial, with when it happened and what it did."""
    phase: str                    # Act, Sense, Reason, Adapt
    start_minute: float
    end_minute: float
    start: str
    end: str
    status: str                   # completed or failed
    description: str


@dataclass
class TrialRecord:
    trial: int
    recipe: dict[str, float]      # ingredient key -> percent
    reason: str                   # why the decision engine chose this recipe
    status: str                   # Completed or Skipped
    steps: list[StepInterval]
    phases: list[PhaseInterval]
    start_minute: float
    end_minute: float
    start: str
    end: str
    dissolution_pct: float | None  # None when the trial was skipped (no result)
    hardness_kp: float | None
    outcome: str                  # Good, Not good, or No result
    margin: float | None          # how comfortably good (negative = failed)
    best_margin_so_far: float | None
    good_so_far: int              # good trials up to and including this one
    notes: list[str]              # faults and recoveries, in words


@dataclass
class EventRecord:
    minute: float
    time: str
    when: str
    kind: str                     # run_started, decision, step_started, step_finished, measurement, trial_completed,
                                  # fault, purge_started, purge_finished, recovery, retry_failed, candidate_skipped,
                                  # alert_queued, run_finished
    trial: int | None
    station: str | None
    attended: bool
    message: str


@dataclass
class AlertRecord:
    minute: float
    time: str
    when: str
    trial: int
    severity: str                 # Recovered, or Needs attention
    title: str
    message: str
    needs_human: bool
    queued_for: str | None        # when staff will next be in, e.g. "Tue 13 Oct 08:00" (None = nobody is needed)


@dataclass
class HandoverSummary:
    """What happened while nobody was in the lab, written ready to read out when staff arrive."""
    start_minute: int
    end_minute: int
    start: str
    end: str
    title: str
    text: str
    trials_started: int
    trials_with_result: int
    trials_skipped: int
    trials_good: int
    faults: int
    alerts_for_staff: int


@dataclass
class Summary:
    trials_attempted: int
    trials_with_result: int
    trials_skipped: int
    trials_good: int
    first_good_trial: int | None
    best_trial: int | None
    best_margin: float | None
    run_hours: float
    unattended_hours: float
    trials_started_unattended: int
    faults_recovered: int
    alerts_for_staff: int
    trials_per_week: float        # trials WITH A RESULT, scaled to a 168-hour week
    manual_baseline_trials_per_week: float
    speedup_vs_manual: float
    headline: str
    attempts_text: str            # e.g. "30 attempted: 29 with a result, 1 skipped"


@dataclass
class RunRecord:
    meta: RunMeta
    ingredient_labels: dict[str, str]
    steps: list[StepInfo]
    calendar: list[CalendarBlock]
    trials: list[TrialRecord]
    events: list[EventRecord]
    alerts: list[AlertRecord]
    handovers: list[HandoverSummary]
    summary: Summary
    comparison: ComparisonResult | None = None               # the headline strategy comparison (no faults)
    comparison_with_faults: ComparisonResult | None = None   # the same with the scripted faults applied
