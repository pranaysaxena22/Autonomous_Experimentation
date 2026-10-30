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
    kind: str                     # "Staffed", "Night", "Weekend" or "Unattended" (for shading)


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
    state: str                    # working, purge or retry: what the station is doing during this stretch
    status_text: str              # the station's status in words, e.g. "Purging after binder dispenser clog (trial 8)"
    look: str                     # how a chart should classify it, e.g. "Trial measured good", "Fault: purge"


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
    queued_for_minute: int | None


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
class StationStatus:
    station: str                  # the station's label, e.g. "Dispense"
    state: str                    # idle, working, purge or retry
    text: str                     # e.g. "Idle", "Blend: trial 8", "Purging after binder dispenser clog (trial 8)"


@dataclass
class PhaseState:
    phase: str                    # Act, Sense, Reason, Adapt
    state: str                    # waiting, active, done or failed
    description: str              # what the phase did / is doing, in words


@dataclass
class Snapshot:
    """Everything to show at one moment of the run, worked out in advance so the dashboard only displays it."""
    index: int
    minute: float
    time: str
    when: str
    staff_present: bool
    staff_text: str
    stations: list[StationStatus]
    trial: int | None             # the trial in progress (None if no trial is running)
    trial_headline: str
    recipe_lines: list[str]       # e.g. "Drug: 17.2%"
    why: str                      # why the decision engine chose this recipe
    active_phase: str | None
    phases: list[PhaseState]
    result_kind: str              # good, not_good, no_result, pending or none
    result_text: str              # empty of numbers until the result is actually known
    trials_finished: int
    results_so_far: int
    good_so_far: int
    best_text: str
    alerts_so_far: list[str]
    just_happened: list[str]      # events at exactly this moment
    recent_events: list[str]      # the last few events, newest first
    is_event: bool                # an event happens at this moment
    previous_event_index: int | None
    next_event_index: int | None


@dataclass
class AboutRecord:
    """Plain-language statements for the 'what this shows and does not show' page."""
    shows: list[str]
    does_not_show: list[str]
    comparison_note: str          # how the advantage of learning changes with difficulty
    throughput_note: str


@dataclass
class PlatformInfo:
    """What a platform run (Stage 8) adds to the record, all of it written out in advance as plain text so the dashboard only displays it.

    A record from the proof of concept has no such section (it is None) and the dashboard shows exactly what it always showed."""
    label: str                    # e.g. "SYNTHETIC platform run ..." (the weakest data status of the inputs)
    setup_name: str
    executor: str                 # which executor ran the plans (the Python stand-in, or later a real one)
    replay_file: str              # the 3D replay file, next to the record
    pipeline: list[str]           # the pieces a trial passes through, one line each
    trial_rows: list[str]         # one line per trial: what was planned and what really happened
    data_lines: list[str]         # the client's data file as the reader found it (data status, row accounting, notes)
    model_lines: list[str]        # what the modelling step made of that data, and what the engine used
    limits: list[str]             # what this platform run does not show


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
    snapshots: list[Snapshot]
    comparison: ComparisonResult | None = None               # the headline strategy comparison (no faults)
    comparison_with_faults: ComparisonResult | None = None   # the same with the scripted faults applied
    about: AboutRecord | None = None
    platform: PlatformInfo | None = None                     # present only for a platform run (Stage 8)
