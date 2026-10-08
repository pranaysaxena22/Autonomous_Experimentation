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
    step: str
    label: str
    start_minute: float
    end_minute: float
    start: str
    end: str
    attended: bool                # was someone in the lab when the step began


@dataclass
class TrialRecord:
    trial: int
    recipe: dict[str, float]      # ingredient key -> percent
    reason: str                   # why the decision engine chose this recipe
    steps: list[StepInterval]
    start_minute: float
    end_minute: float
    start: str
    end: str
    dissolution_pct: float
    hardness_kp: float
    outcome: str                  # "Good" or "Not good"
    margin: float                 # how comfortably good (negative = failed)
    best_margin_so_far: float
    good_so_far: int              # number of good trials up to and including this one


@dataclass
class EventRecord:
    minute: float
    time: str
    when: str
    kind: str                     # run_started, decision, step_started, step_finished, measurement, trial_completed, run_finished
    trial: int | None
    station: str | None
    attended: bool
    message: str


@dataclass
class Summary:
    trials_completed: int
    trials_good: int
    first_good_trial: int | None
    best_trial: int | None
    best_margin: float | None
    run_hours: float
    unattended_hours: float
    trials_started_unattended: int
    trials_per_week: float
    manual_baseline_trials_per_week: float
    speedup_vs_manual: float
    headline: str


@dataclass
class RunRecord:
    meta: RunMeta
    ingredient_labels: dict[str, str]
    steps: list[StepInfo]
    calendar: list[CalendarBlock]
    trials: list[TrialRecord]
    events: list[EventRecord]
    summary: Summary
    comparison: ComparisonResult | None = None   # the multi-campaign strategy comparison, when one was run
