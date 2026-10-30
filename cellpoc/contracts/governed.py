"""Shared data shapes for the governed decision engine (Stage 4-3) and the labs it is developed against. Values only: no logic that decides anything.

The engine sees measurements and the context a trial ran in; it never sees a lab's truth. A lab turns a recipe and a context into a measurement; the engine turns a history of measurements into the next recipe.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrialContext:
    """Where and when a trial runs: the values of the categorical inputs (for example the supplier, the filler grade and the tester, by the name of the column that holds them), the batch and the time."""
    categories: dict
    batch_id: str
    day_fraction: float


@dataclass(frozen=True)
class TargetSpec:
    """One target exactly as the setup states it: 'at_least' a value, 'at_most' a value, or 'between' two."""
    result: str
    label: str
    goal: str
    low: float | None = None
    high: float | None = None

    def met(self, value: float) -> bool:
        return (self.low is None or value >= self.low) and (self.high is None or value <= self.high)


@dataclass(frozen=True)
class Observation:
    """What the instruments reported for one campaign trial."""
    trial_number: int
    recipe: dict
    context: TrialContext
    results: dict


@dataclass(frozen=True)
class Decision:
    """The engine's choice for one trial, with everything it claimed when it made it."""
    trial_number: int
    recipe: dict
    kind: str                                       # starting, exploit, exploratory, bridging, space_filling, local_search or stale_exploration
    why: str                                        # plain words
    chances: dict = field(default_factory=dict)     # the stated chance of meeting each target the engine MODELLED for this pick; unmodelled targets are never in it
    unmodelled: tuple = ()                          # targets the engine made no claim about (not carried, or stale), with their reasons in `why`
    stale: tuple = ()                               # targets whose stated range stopped holding (the staleness watch)
    stated_ranges: dict = field(default_factory=dict)   # for each modelled target, the 90% range stated for this recipe (already widened); the watch checks the measurement against it
    warnings: dict = field(default_factory=dict)    # the per-recipe warning statuses for this recipe, each on its own: distance, range, category
    new_context: tuple = ()                         # context values never seen before (name, value) that made this a bridging trial
