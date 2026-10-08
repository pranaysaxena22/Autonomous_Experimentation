"""One campaign: a strategy proposes, the lab measures, trial after trial. Counts trials, not hours."""
from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Formulation, Lab, Measurement, Strategy


@dataclass(frozen=True)
class CampaignTrial:
    trial: int
    formulation: Formulation
    measurement: Measurement | None    # None = the trial was skipped and produced no result


def run_campaign(lab: Lab, strategy: Strategy, trials: int,
                 skipped_trials: frozenset[int] = frozenset()) -> list[CampaignTrial]:
    """Run `trials` trials. Trials in `skipped_trials` fail: the recipe is never made and no result exists."""
    history: list[Measurement] = []
    skipped: list[Formulation] = []
    outcome: list[CampaignTrial] = []
    for trial in range(1, trials + 1):
        proposal = strategy.propose(trial, tuple(history), tuple(skipped))
        if trial in skipped_trials:
            skipped.append(proposal.formulation)
            outcome.append(CampaignTrial(trial, proposal.formulation, None))
            continue
        measurement = lab.measure(trial, proposal.formulation)
        history.append(measurement)
        outcome.append(CampaignTrial(trial, proposal.formulation, measurement))
    return outcome
