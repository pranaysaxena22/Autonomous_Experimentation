"""Scoring recipes against the hidden truth, AFTER THE FACT.

Used only to judge how well a strategy did once a campaign is over ("was the recipe it
tried truly good?"). The decision engine can never import this: it is not on the engine's
list of allowed parts, and an automated check enforces that.
"""
from __future__ import annotations

from .contracts import Formulation
from .settings import Settings
from .virtual_lab import oracle


def truly_good(formulation: Formulation, settings: Settings) -> bool:
    """Does this recipe really meet the specifications, with no measurement noise?"""
    return oracle.truly_meets_spec(formulation, settings)
