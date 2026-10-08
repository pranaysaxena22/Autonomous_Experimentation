"""The two plug-in points of the cell simulator. It depends on these shapes, never on a concrete lab or engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .models import Formulation, Measurement


@dataclass(frozen=True)
class Proposal:
    """The next recipe to try, with the reason in plain English."""
    formulation: Formulation
    reason: str


class Lab(Protocol):
    """Anything that can measure a recipe: the virtual lab now, real instruments one day."""

    def measure(self, trial_id: int, formulation: Formulation) -> Measurement: ...


class Strategy(Protocol):
    """A decision engine. It sees only past measurements - never the lab's hidden truth.

    `history` holds the measurements so far. A trial that produced no result (a skipped
    candidate) is absent from it, so history can be shorter than trial_number - 1; the
    recipes of such trials are passed in `skipped` so they are not simply proposed again.
    """

    name: str
    description: str

    def propose(self, trial_number: int, history: Sequence[Measurement],
                skipped: Sequence[Formulation] = ()) -> Proposal: ...
