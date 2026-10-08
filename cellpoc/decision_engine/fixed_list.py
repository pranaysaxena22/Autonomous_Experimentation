"""The baseline strategy: a list of recipes written before the run began, tried in order.

The list is a Latin-hypercube design: each ingredient's range is cut into as many slices as
there are trials and every slice is used exactly once, so the list covers the recipe space
evenly. That makes it a fair baseline, stronger than picking recipes at random. It never
looks at results, which is exactly what the adaptive strategy will be compared against.
"""
from __future__ import annotations

import random
from typing import Sequence

from ..contracts import Formulation, Measurement, Proposal
from ..settings.models import DesignSpace


class FixedListStrategy:
    name = "fixed-list"
    description = "A fixed list of recipes written before the run began, tried in order"

    def __init__(self, design_space: DesignSpace, trials: int, seed: int):
        rng = random.Random(f"fixed-list:{seed}")
        columns = []
        for ingredient in design_space.ingredients:
            slices = list(range(trials))
            rng.shuffle(slices)
            width = (ingredient.max - ingredient.min) / trials
            columns.append([ingredient.min + (s + rng.random()) * width for s in slices])
        self._list = [Formulation(*row) for row in zip(*columns)]

    def propose(self, trial_number: int, history: Sequence[Measurement]) -> Proposal:
        if not 1 <= trial_number <= len(self._list):
            raise IndexError(f"The fixed list has {len(self._list)} recipes, but trial {trial_number} was requested.")
        return Proposal(self._list[trial_number - 1],
                        f"Recipe {trial_number} of {len(self._list)} from the fixed list written before the run began")
