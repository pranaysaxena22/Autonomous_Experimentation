"""Wires the parts together and runs simulations. The only place that knows all of them."""
from __future__ import annotations

from .cell_simulator import simulate
from .comparison import compare
from .contracts import RunRecord
from .decision_engine import AdaptiveStrategy, FixedListStrategy
from .settings import Settings
from .virtual_lab import VirtualLab


def run_fixed_list(settings: Settings, run_id: str = "fixed-list") -> RunRecord:
    """One run of the cell following a pre-written fixed list of recipes."""
    capacity = int(settings.run.duration_hours * 60 // settings.cell.minutes_per_trial)
    strategy = FixedListStrategy(settings.design_space, max(capacity, settings.comparison.trials_per_campaign),
                                 settings.run.random_seed)
    return simulate(settings, VirtualLab(settings), strategy, run_id)


def run_adaptive(settings: Settings, run_id: str = "adaptive") -> RunRecord:
    """One run of the cell where each recipe is chosen from all results so far."""
    strategy = AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine,
                                settings.run.random_seed)
    return simulate(settings, VirtualLab(settings), strategy, run_id)


def run_demo(settings: Settings, run_id: str = "adaptive-demo", with_faults: bool = False) -> RunRecord:
    """The demonstration run (adaptive, default seed) carrying the full multi-campaign comparison.

    The comparison covers all the campaigns in the settings, not just this run; this run is
    simply campaign 1 of them, shown in detail.
    """
    record = run_adaptive(settings, run_id)
    record.comparison = compare(settings, with_faults=with_faults)
    return record
