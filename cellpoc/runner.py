"""Wires the parts together and runs one simulation. The only place that knows all of them."""
from __future__ import annotations

from .cell_simulator import simulate
from .contracts import RunRecord
from .decision_engine import FixedListStrategy
from .settings import Settings
from .virtual_lab import VirtualLab


def run_fixed_list(settings: Settings, run_id: str = "fixed-list") -> RunRecord:
    """One run of the cell following a pre-written fixed list of recipes."""
    capacity = int(settings.run.duration_hours * 60 // settings.cell.minutes_per_trial)
    strategy = FixedListStrategy(settings.design_space, max(capacity, settings.comparison.trials_per_campaign),
                                 settings.run.random_seed)
    return simulate(settings, VirtualLab(settings), strategy, run_id)
