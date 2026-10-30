"""The two strategies the governed engine is compared with in Stage 4-4. Both see exactly the same information as the governed engine: the history, the measurements so far and the context.

UNGOVERNED: the same code as the governed engine with every governance rule switched off, so the comparison isolates what the governance adds. A model for EVERY target (the model Stage 3 chose for a
carried target; a quadratic ridge for a target Stage 3 did not carry), no range widening, no warnings (so no unvouched recipes and no exploratory picks), no bridging trials for a new context value, no
staleness watch. Each pick is the candidate with the highest chance of meeting every target. Same refit cadence and candidate counts.

RANDOM: a recipe drawn uniformly from the allowed ranges, with the filler inside its range. The floor.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from ..contracts import STATUS_CARRIED, Decision, EngineBrief, TargetBrief, TrialContext
from ..contracts.seeds import refuse_sealed_seed
from ..modelling.models import FULL, Settings
from .governed import GovernedStrategy, _stream

DEFAULT_MODEL, DEFAULT_MODEL_LABEL = "quadratic", "Quadratic regression (ridge)"      # for a target Stage 3 did not carry, so the ungoverned engine has something to use


class UngovernedStrategy(GovernedStrategy):
    name = "ungoverned"
    description = "The same models and candidates without any of the governance rules"

    def __init__(self, brief: EngineBrief, targets: dict, history: pd.DataFrame, space: dict, ingredients, balance: tuple, seed: int, settings: Settings = FULL, group_column: str = "batch_id"):
        refuse_sealed_seed(seed, "the ungoverned engine", allow_acceptance=True)      # first, so a sealed seed is refused before anything else is looked at
        donor = next((t for t in brief.targets if t.usable_for_decisions), None)
        if donor is None:
            raise ValueError("the ungoverned engine needs at least one carried target to take the model inputs from")
        every = tuple(TargetBrief(t.result, t.label, STATUS_CARRIED, t.model_key or DEFAULT_MODEL, t.model_label or DEFAULT_MODEL_LABEL, None, None, 1.0, "no widening: the ungoverned engine does not use the brief",
                                  "", (), donor.numeric_inputs, donor.categorical_inputs) for t in brief.targets if t.result in targets)
        super().__init__(replace(brief, targets=every), targets, history, space, ingredients, balance, seed, settings, group_column)

    def _pending_context(self, context: TrialContext, done) -> tuple:           # no bridging
        return ()

    def _stale(self, done) -> tuple:                                           # no staleness watch
        return ()

    def _warnings(self, frame: pd.DataFrame) -> dict:                           # no warnings, so nothing is unvouched
        n = len(frame)
        return {"distance": np.zeros(n, bool), "range": np.zeros(n, bool), "category": np.zeros(n, bool)}


class RandomRecipes:
    name = "random"
    description = "A recipe drawn uniformly from the allowed ranges"

    def __init__(self, space: dict, ingredients, balance: tuple, seed: int):
        refuse_sealed_seed(seed, "the random-recipe strategy", allow_acceptance=True)
        self.keys = list(space)
        self._low = np.array([space[k][0] for k in self.keys], float)
        self._span = np.array([space[k][1] - space[k][0] for k in self.keys], float)
        self.ingredients, self.balance, self.seed = tuple(ingredients), balance, seed

    def propose(self, trial_number: int, context: TrialContext, measurements) -> Decision:
        g = _stream(self.seed, "random", trial_number)
        while True:
            values = self._low + g.random(len(self.keys)) * self._span
            recipe = {k: float(v) for k, v in zip(self.keys, values)}
            filler = 100.0 - sum(recipe[i] for i in self.ingredients)
            if self.balance[1][0] <= filler <= self.balance[1][1]:
                return Decision(trial_number, recipe, "random", "A recipe drawn at random from the allowed ranges (the floor the other strategies are compared with).")
