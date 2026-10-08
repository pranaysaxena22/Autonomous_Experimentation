"""The headline comparison: fixed list vs adaptive vs random, over many repeated campaigns.

Paired by design: campaign i uses the same seed for every strategy, so each strategy faces
the same lab (the same measurement noise for the same trial number) and the differences
between strategies are not luck of the draw.
"""
from __future__ import annotations

import math
from typing import Sequence

from ..contracts import (
    ComparisonResult, MeasureStats, PairedComparison, StrategyComparison, Strategy, meets_spec,
)
from ..decision_engine import AdaptiveStrategy, FixedListStrategy, RandomStrategy
from ..scoring import truly_good
from ..settings import Settings
from ..virtual_lab import VirtualLab
from .campaign import CampaignTrial, run_campaign

STRATEGIES = (
    ("fixed-list", "Fixed list"),
    ("adaptive", "Adaptive"),
    ("random", "Random"),
)


def campaign_seeds(settings: Settings, campaigns: int | None = None) -> list[int]:
    """The default seed and the next ones after it. Fixed by the settings, never chosen after seeing results."""
    count = settings.comparison.campaigns if campaigns is None else campaigns
    return [settings.run.random_seed + i for i in range(count)]


def make_strategy(key: str, settings: Settings, seed: int) -> Strategy:
    trials = settings.comparison.trials_per_campaign
    if key == "fixed-list":
        return FixedListStrategy(settings.design_space, trials, seed)
    if key == "adaptive":
        return AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine, seed)
    if key == "random":
        return RandomStrategy(settings.design_space, seed)
    raise KeyError(key)


def first_trials(settings: Settings, outcome: Sequence[CampaignTrial]) -> tuple[int | None, int | None]:
    """(first trial MEASURED as passing, first trial whose recipe was TRULY good), scored after the fact."""
    measured = truly = None
    for t in outcome:
        if t.measurement is None:
            continue  # a skipped trial made no recipe, so it cannot count as found
        if measured is None and meets_spec(t.measurement.dissolution_pct, t.measurement.hardness_kp,
                                           settings.specifications):
            measured = t.trial
        if truly is None and truly_good(t.formulation, settings):
            truly = t.trial
    return measured, truly


def _stats(firsts: Sequence[int | None], trials: int) -> MeasureStats:
    n = len(firsts)
    cumulative = [100.0 * sum(1 for f in firsts if f is not None and f <= t) / n for t in range(1, trials + 1)]

    def reached(share: float) -> int | None:
        return next((t for t, pct in enumerate(cumulative, start=1) if pct >= share), None)

    found = sum(1 for f in firsts if f is not None)
    return MeasureStats(found, 100.0 * found / n, reached(25), reached(50), reached(75), cumulative)


def _paired(first: StrategyComparison, second: StrategyComparison, measure: str) -> PairedComparison:
    a = getattr(first, measure)
    b = getattr(second, measure)
    never = math.inf
    pairs = [(never if x is None else x, never if y is None else y) for x, y in zip(a, b)]
    first_earlier = sum(1 for x, y in pairs if x < y)
    second_earlier = sum(1 for x, y in pairs if y < x)
    neither = sum(1 for x, y in pairs if x == never and y == never)
    tie = len(pairs) - first_earlier - second_earlier - neither
    sentence = (f"{first.label} found one sooner than {second.label} in {first_earlier} of {len(pairs)} campaigns; "
                f"{second.label} was sooner in {second_earlier}; same trial in {tie}; neither found one in {neither}.")
    return PairedComparison(first.label, second.label, measure, first_earlier, tie, second_earlier, neither, sentence)


def _describe(s: StrategyComparison, trials: int) -> str:
    stats = s.truly_good

    def when(trial: int | None) -> str:
        return f"trial {trial}" if trial is not None else f"not within {trials} trials"

    return (f"{s.label}: half of campaigns had found one by {when(stats.median_trial)} "
            f"(a quarter by {when(stats.trial_by_25pct)}, three quarters by {when(stats.trial_by_75pct)}); "
            f"{stats.found_pct:.0f}% of campaigns found one within {trials} trials.")


def compare(settings: Settings, *, campaigns: int | None = None, with_faults: bool = False) -> ComparisonResult:
    trials = settings.comparison.trials_per_campaign
    seeds = campaign_seeds(settings, campaigns)
    skipped_trials = settings.scripted_faults.skipped_trials if with_faults else frozenset()

    firsts: dict[str, list[tuple[int | None, int | None]]] = {key: [] for key, _ in STRATEGIES}
    for seed in seeds:
        for key, _ in STRATEGIES:
            outcome = run_campaign(VirtualLab(settings, seed=seed), make_strategy(key, settings, seed), trials,
                                   skipped_trials)
            firsts[key].append(first_trials(settings, outcome))

    strategies = []
    for key, label in STRATEGIES:
        measured = [m for m, _ in firsts[key]]
        truly = [t for _, t in firsts[key]]
        strategies.append(StrategyComparison(
            key, label, make_strategy(key, settings, seeds[0]).description, measured, truly,
            _stats(measured, trials), _stats(truly, trials)))
    by_key = {s.key: s for s in strategies}

    n = len(seeds)
    fault_note = (f" Scripted faults were applied identically to every strategy: trial(s) "
                  f"{', '.join(str(t) for t in sorted(skipped_trials))} produced no result in every campaign."
                  if with_faults and skipped_trials else
                  (" Scripted faults were applied, but none of them skips a trial." if with_faults else
                   " No faults were applied, to isolate the effect of learning."))
    notes = [
        "HEADLINE MEASURE: the first trial whose recipe was truly good. It is scored after the fact against the "
        "hidden truth; the decision engine never sees it. Measurement noise cannot flatter it, so it is the "
        "honest measure of whether a strategy really found a working recipe.",
        "SECOND MEASURE: the first trial measured as passing. This is what the cell itself could observe; noise can "
        "make a poor recipe read as passing or a good one read as failing.",
        f"Half of the campaigns found one by the 'median' trial. 'Not within {trials} trials' means fewer than that "
        "share of campaigns found one in time.",
        f"{n} campaigns of {trials} trials each. Every strategy used the same {n} seeds, so the comparison is paired."
        + fault_note,
    ]
    headline = " ".join(_describe(by_key[k], trials) for k in ("adaptive", "fixed-list", "random"))
    return ComparisonResult(
        campaigns=n, trials_per_campaign=trials, seeds=seeds, faults_applied=with_faults,
        skipped_trials=sorted(skipped_trials), headline_measure="truly_good",
        headline_label="First trial whose recipe was truly good (scored after the fact)",
        headline_text=headline, measure_notes=notes, strategies=strategies,
        paired=[_paired(by_key["adaptive"], by_key["fixed-list"], "first_truly_good"),
                _paired(by_key["adaptive"], by_key["random"], "first_truly_good"),
                _paired(by_key["adaptive"], by_key["fixed-list"], "first_measured_pass")])
