"""Shared data shapes passed between the parts. Values only."""
from __future__ import annotations

from dataclasses import astuple, dataclass, fields


@dataclass(frozen=True)
class Formulation:
    """One tablet recipe, each ingredient as a percentage."""
    drug: float
    filler: float
    binder: float
    disintegrant: float
    lubricant: float

    def as_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def as_tuple(self) -> tuple[float, ...]:
        return astuple(self)


@dataclass(frozen=True)
class Measurement:
    """What the instruments report for one trial. This is all the decision engine ever sees."""
    trial_id: int
    formulation: Formulation
    dissolution_pct: float
    hardness_kp: float
