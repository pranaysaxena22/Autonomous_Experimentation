"""The strategy comparison, already worked out for display. Part of the run record."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MeasureStats:
    """How one strategy fared on one measure across all campaigns."""
    found_count: int                  # campaigns that found one within the campaign length
    found_pct: float                  # the same as a percentage
    trial_by_25pct: int | None        # first trial by which 25% of campaigns had found one (None = never)
    median_trial: int | None          # ... 50% of campaigns
    trial_by_75pct: int | None        # ... 75% of campaigns
    cumulative_pct: list[float]       # for each trial 1..N: % of campaigns that had found one by then


@dataclass
class StrategyComparison:
    key: str                          # "fixed-list", "adaptive", "random"
    label: str
    description: str
    first_measured_pass: list[int | None]   # per campaign: first trial MEASURED as passing (None = never)
    first_truly_good: list[int | None]      # per campaign: first trial whose recipe was TRULY good
    measured_pass: MeasureStats
    truly_good: MeasureStats


@dataclass
class PairedComparison:
    """Campaign by campaign (same seed), which strategy found one first."""
    first: str
    second: str
    measure: str
    first_earlier: int
    tie: int
    second_earlier: int
    neither_found: int
    sentence: str


@dataclass
class ComparisonResult:
    campaigns: int
    trials_per_campaign: int
    seeds: list[int]
    faults_applied: bool
    skipped_trials: list[int]         # trials that produced no result in every campaign (empty without faults)
    headline_measure: str             # "truly_good"
    headline_label: str
    headline_text: str
    measure_notes: list[str]
    strategies: list[StrategyComparison]
    paired: list[PairedComparison]
