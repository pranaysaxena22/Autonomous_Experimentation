"""The same comparison on an easier and a harder version of the hidden truth.

Difficulty is how rare a truly good recipe is. The offsets below shift the hidden dissolution
surface so that about 1% / 3% / 10% of random recipes are truly good; the health check
measures the real share at each level and fails if it drifts from its target.
Nothing else changes: same engine, same seeds, no faults.
"""
from __future__ import annotations

from ..contracts import ComparisonResult, DifficultyRow, DifficultyStrategyResult
from ..scoring import truly_good_share
from ..settings import Settings
from .compare import compare

# (name, target share of random recipes that are truly good, dissolution offset)
LEVELS = (
    ("Harder", 0.01, -2.5),
    ("Default", 0.03, 0.0),
    ("Easier", 0.10, 4.0),
)


def _lead(strategies: list[DifficultyStrategyResult]) -> tuple[float, str, float, str]:
    """Adaptive's lead over the best of the other strategies, and which baseline that is (both, when they tie)."""
    adaptive = next(s for s in strategies if s.label == "Adaptive")
    others = [s for s in strategies if s.label != "Adaptive"]
    best = max(s.found_pct for s in others)
    names = [s.label for s in others if s.found_pct == best]
    against = " and ".join(names)
    points = adaptive.found_pct - best
    text = (f"{points:+.0f} points over {against} ({best:.0f}% found one)" if len(names) == 1
            else f"{points:+.0f} points over {against} (tied: {best:.0f}% found one)")
    return points, against, best, text


def _row(level: str, share: float, result: ComparisonResult) -> DifficultyRow:
    strategies = [
        DifficultyStrategyResult(s.label, s.truly_good.found_pct, s.truly_good.median_trial,
                                 s.truly_good.trial_by_25pct, s.truly_good.trial_by_75pct)
        for s in result.strategies if s.key in ("adaptive", "fixed-list", "random")]
    points, against, against_pct, text = _lead(strategies)
    return DifficultyRow(level, round(100 * share, 1), strategies, points, against, against_pct, text)


def difficulty_table(settings: Settings, default_result: ComparisonResult | None = None) -> list[DifficultyRow]:
    """One row per level. Pass an existing no-fault comparison to reuse it for the Default row."""
    rows = []
    for level, _, offset in LEVELS:
        share = truly_good_share(settings, offset)
        if offset == 0.0 and default_result is not None and not default_result.faults_applied:
            result = default_result
        else:
            result = compare(settings, with_faults=False, dissolution_offset=offset)
        rows.append(_row(level, share, result))
    return rows
