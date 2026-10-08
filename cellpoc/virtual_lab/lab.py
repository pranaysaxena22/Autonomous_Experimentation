"""The virtual lab: the only way to learn how a formulation behaves is to measure it here."""
from __future__ import annotations

import random

from ..contracts import Formulation, Measurement
from ..settings import Settings
from ._truth import true_dissolution_pct, true_hardness_kp


class VirtualLab:
    """Simulated instruments. Each measurement carries noise drawn from the settings.

    Noise depends only on (seed, trial_id), so a given trial always reads the same
    whatever order trials are run in, and a different seed gives a different lab day.
    """

    def __init__(self, settings: Settings, seed: int | None = None):
        self._settings = settings
        self._seed = settings.run.random_seed if seed is None else seed

    def measure(self, trial_id: int, formulation: Formulation) -> Measurement:
        self._check_inside_design_space(formulation)
        noise = random.Random(f"virtual-lab:{self._seed}:{trial_id}")
        dissolution = true_dissolution_pct(formulation) + noise.gauss(0, self._settings.noise.dissolution_sd)
        hardness = true_hardness_kp(formulation) + noise.gauss(0, self._settings.noise.hardness_sd)
        return Measurement(trial_id, formulation, min(100.0, max(0.0, dissolution)), max(0.0, hardness))

    def _check_inside_design_space(self, formulation: Formulation) -> None:
        for ingredient in self._settings.design_space.ingredients:
            value = formulation.as_dict()[ingredient.key]
            if not ingredient.min <= value <= ingredient.max:
                raise ValueError(
                    f"{ingredient.label} is {value}%, outside the allowed range "
                    f"{ingredient.min}-{ingredient.max}%.")
