"""The plainest baseline: every recipe drawn at random from the allowed ranges, ignoring all results."""
from __future__ import annotations

import random
from typing import Sequence

from ..contracts import Formulation, Measurement, Proposal
from ..settings.models import DesignSpace


class RandomStrategy:
    name = "random"
    description = "A random recipe for every trial, ignoring all results"

    def __init__(self, design_space: DesignSpace, seed: int):
        self._space = design_space
        self._seed = seed

    def propose(self, trial_number: int, history: Sequence[Measurement],
                skipped: Sequence[Formulation] = ()) -> Proposal:
        rng = random.Random(f"random:{self._seed}:{trial_number}")
        recipe = Formulation(*[rng.uniform(i.min, i.max) for i in self._space.ingredients])
        return Proposal(recipe, "Random recipe drawn evenly from the allowed ranges, ignoring all results so far")
