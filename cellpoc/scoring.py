"""Scoring recipes against the hidden truth, AFTER THE FACT.

Used only to judge how well a strategy did once a campaign is over ("was the recipe it
tried truly good?"). The decision engine can never import this: it is not on the engine's
list of allowed parts, and an automated check enforces that.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import Formulation, TrialContext
from .settings import Settings
from .virtual_lab import dev_oracle, oracle
from .virtual_lab.dev_lab import DevLab


def truly_good(formulation: Formulation, settings: Settings, dissolution_offset: float = 0.0) -> bool:
    """Does this recipe really meet the specifications, with no measurement noise?"""
    return oracle.truly_meets_spec(formulation, settings, dissolution_offset)


def truly_good_share(settings: Settings, dissolution_offset: float = 0.0, samples: int = 50000) -> float:
    """The share of random recipes that are truly good (how hard the problem is), 0-1."""
    return oracle.feasible_fraction(settings, samples=samples, dissolution_offset=dissolution_offset)

# ---------------------------------------------------------------- the development lab (Stage 4-4)
@dataclass(frozen=True)
class TrialScore:
    """One development-lab trial scored against the truth. The truth is the noise-free result in the trial's own context (the batch's own shift and any true process step included), so a lucky or unlucky
    measurement cannot flatter or punish a strategy."""
    trial: int
    good: bool                      # every target truly met
    met: dict                       # for each target, whether it was truly met
    measured_pass: bool             # whether the MEASUREMENT happened to meet every target


def score_dev_trial(lab: DevLab, specs: dict, trial: int, recipe: dict, context: TrialContext, measured: dict) -> TrialScore:
    truth = dev_oracle.true_results(lab, trial, recipe, context)
    return TrialScore(trial, dev_oracle.is_good(truth), {r: specs[r].met(truth[r]) for r in specs}, all(specs[r].met(measured[r]) for r in specs))
