"""Judging a result against the specifications. One definition of "good", used everywhere."""
from __future__ import annotations

from ..settings.models import Specifications


def meets_spec(dissolution_pct: float, hardness_kp: float, specs: Specifications) -> bool:
    """True when dissolution is high enough and hardness is inside its window."""
    return (dissolution_pct >= specs.dissolution.minimum
            and specs.hardness.minimum <= hardness_kp <= specs.hardness.maximum)


def margin(dissolution_pct: float, hardness_kp: float, specs: Specifications) -> float:
    """How comfortably a result is good. Positive = meets spec, negative = fails.

    Each property's distance from its nearest limit is scaled so that 1.0 means
    "comfortably inside"; the result is the worst of the three limits.
    """
    half_window = (specs.hardness.maximum - specs.hardness.minimum) / 2
    return min(
        (dissolution_pct - specs.dissolution.minimum) / specs.dissolution.margin_scale,
        (hardness_kp - specs.hardness.minimum) / half_window,
        (specs.hardness.maximum - hardness_kp) / half_window,
    )
