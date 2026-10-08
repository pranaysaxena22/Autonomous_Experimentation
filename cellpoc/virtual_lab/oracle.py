"""Knowledge of the hidden truth, for SCORING AND CHECKS ONLY.

This is how we ask "how close did a campaign get to the best possible tablet?".
The decision engine and the dashboard must never import this module; an automated
check (check_stage1.bat) enforces that.
"""
from __future__ import annotations

import random

from ..contracts import Formulation, margin, meets_spec
from ..settings import Settings
from ._truth import true_dissolution_pct, true_hardness_kp


def true_properties(formulation: Formulation) -> tuple[float, float]:
    """(dissolution %, hardness kP) with no measurement noise."""
    return true_dissolution_pct(formulation), true_hardness_kp(formulation)


def true_margin(formulation: Formulation, settings: Settings) -> float:
    """How comfortably the formulation is truly good (positive = meets spec)."""
    dissolution, hardness = true_properties(formulation)
    return margin(dissolution, hardness, settings.specifications)


def truly_meets_spec(formulation: Formulation, settings: Settings) -> bool:
    dissolution, hardness = true_properties(formulation)
    return meets_spec(dissolution, hardness, settings.specifications)


def random_formulation(settings: Settings, rng: random.Random) -> Formulation:
    return Formulation(*[rng.uniform(i.min, i.max) for i in settings.design_space.ingredients])


def feasible_fraction(settings: Settings, samples: int = 20000, seed: int = 1) -> float:
    """Share of the design space that truly meets spec, estimated by random sampling."""
    rng = random.Random(seed)
    good = sum(truly_meets_spec(random_formulation(settings, rng), settings) for _ in range(samples))
    return good / samples


def true_best(settings: Settings, samples: int = 20000, seed: int = 1) -> tuple[Formulation, float]:
    """The best formulation found by a large random search, and its true margin."""
    rng = random.Random(seed)
    best, best_margin = None, float("-inf")
    for _ in range(samples):
        candidate = random_formulation(settings, rng)
        m = true_margin(candidate, settings)
        if m > best_margin:
            best, best_margin = candidate, m
    return best, best_margin  # type: ignore[return-value]
