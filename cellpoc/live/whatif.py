"""Try it yourself: the user types their own recipe, the virtual lab measures it, and the decision engine says what it would do next. Separate from the stored demonstration run.

The page only sends the five numbers and shows what comes back; the lab and the engine run here, on the server, as they do for the live run, so the page still calculates nothing. The engine never sees the lab's hidden truth:
it is given measurements only, exactly as in a run. The recipe is measured as trial 7 of a run that began the usual way: the engine has already seen its six starting recipes (measured by the same lab), then it sees yours,
and says what it would try as trial 8. Each try is measured afresh, so the same recipe tried twice reads a little differently, as in a real lab.
"""
from __future__ import annotations

import math
import threading
from dataclasses import replace

from ..contracts import Formulation, Measurement, margin, meets_spec
from ..decision_engine import AdaptiveStrategy
from ..virtual_lab import VirtualLab

FIRST_TRY_ID = 10_000            # the lab's noise depends on this number, so each try gets a new one; it is never shown


def design_of(settings) -> dict:
    """What the page needs to draw the form: each ingredient with its allowed range, and the targets in words."""
    s = settings.specifications
    return {"ingredients": [{"key": i.key, "label": i.label, "min": i.min, "max": i.max, "start": round((i.min + i.max) / 2, 1)} for i in settings.design_space.ingredients],
            "targets": {"dissolution": f"at least {s.dissolution.minimum:g}{s.dissolution.unit}",
                        "hardness": f"between {s.hardness.minimum:g} and {s.hardness.maximum:g} {s.hardness.unit}"}}


class WhatIf:
    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._tries = 0
        self._engine = AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine, settings.run.random_seed)
        self._starting: list[Measurement] | None = None             # the engine's six starting recipes and what the lab measured for them (made the first time they are needed)

    def check(self, value) -> tuple[Formulation | None, str | None]:
        """(the recipe, None) when the numbers are a recipe the lab can measure; (None, a plain sentence) when they are not."""
        ingredients = self.settings.design_space.ingredients
        if not isinstance(value, dict):
            return None, "The recipe was not understood."
        names = ", ".join(i.label for i in ingredients)
        if set(value) != {i.key for i in ingredients}:
            return None, f"A recipe needs one value for each of: {names}."
        numbers: dict[str, float] = {}
        for i in ingredients:
            v = value[i.key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                return None, f"{i.label} must be a number."
            if not i.min <= v <= i.max:
                return None, f"{i.label} must be between {i.min:g} and {i.max:g}%. You wrote {v:g}."
            numbers[i.key] = float(v)
        return Formulation(**numbers), None

    def _start(self) -> list[Measurement]:
        if self._starting is None:
            lab, history = VirtualLab(self.settings), []
            for trial in range(1, self.settings.engine.initial_recipes + 1):
                history.append(lab.measure(trial, self._engine.propose(trial, tuple(history), ()).formulation))
            self._starting = history
        return self._starting

    def try_recipe(self, value) -> dict | str:
        """The lab's reading of the recipe and what the engine would do next; or a plain sentence when the recipe cannot be measured."""
        recipe, problem = self.check(value)
        if problem:
            return problem
        s = self.settings.specifications
        with self._lock:
            starting = self._start()
            self._tries += 1
            reading = VirtualLab(self.settings).measure(FIRST_TRY_ID + self._tries, recipe)
            trial = len(starting) + 1
            yours = replace(reading, trial_id=trial)
            nxt = self._engine.propose(trial + 1, tuple(starting) + (yours,), ())
        good = meets_spec(yours.dissolution_pct, yours.hardness_kp, s)
        return {
            "recipe": recipe.as_dict(), "trial": trial,
            "measured": {"dissolution_pct": round(yours.dissolution_pct, 1), "hardness_kp": round(yours.hardness_kp, 2), "good": good,
                         "dissolution_ok": yours.dissolution_pct >= s.dissolution.minimum, "hardness_ok": s.hardness.minimum <= yours.hardness_kp <= s.hardness.maximum,
                         "margin": round(margin(yours.dissolution_pct, yours.hardness_kp, s), 2)},
            "starting": [{"trial": m.trial_id, "dissolution_pct": round(m.dissolution_pct, 1), "hardness_kp": round(m.hardness_kp, 2), "good": meets_spec(m.dissolution_pct, m.hardness_kp, s)} for m in starting],
            "next": {"trial": trial + 1, "recipe": {k: round(v, 1) for k, v in nxt.formulation.as_dict().items()}, "reason": nxt.reason},
        }
