"""Wires the parts together and runs simulations. The only place that knows all of them."""
from __future__ import annotations

from .cell_simulator import simulate
from .comparison import compare
from .comparison.difficulty import difficulty_table
from .contracts import DifficultyRow, RunRecord
from .decision_engine import AdaptiveStrategy, FixedListStrategy
from .settings import Settings
from .virtual_lab import VirtualLab


def run_fixed_list(settings: Settings, run_id: str = "fixed-list", with_faults: bool = False) -> RunRecord:
    """One run of the cell following a pre-written fixed list of recipes."""
    capacity = int(settings.run.duration_hours * 60 // settings.cell.minutes_per_trial)
    strategy = FixedListStrategy(settings.design_space, max(capacity, settings.comparison.trials_per_campaign),
                                 settings.run.random_seed)
    return simulate(settings, VirtualLab(settings), strategy, run_id,
                    settings.scripted_faults if with_faults else None)


def run_adaptive(settings: Settings, run_id: str = "adaptive", with_faults: bool = False) -> RunRecord:
    """One run of the cell where each recipe is chosen from all results so far."""
    strategy = AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine,
                                settings.run.random_seed)
    return simulate(settings, VirtualLab(settings), strategy, run_id,
                    settings.scripted_faults if with_faults else None)


def run_closed_loop(settings: Settings, run_id: str = "closed-loop") -> RunRecord:
    """The full unattended run: adaptive engine, whole run window, scripted faults applied.

    This is one run of the cell, not the 40-campaign comparison.
    """
    return run_adaptive(settings, run_id, with_faults=True)


def run_demo(settings: Settings, run_id: str = "adaptive-demo", with_faults: bool = False,
             difficulty: list[DifficultyRow] | None = None) -> RunRecord:
    """An adaptive run carrying the full multi-campaign comparison (all campaigns in the settings).

    `with_faults` chooses whether the COMPARISON applies the scripted faults; the run itself is fault-free.
    """
    record = run_adaptive(settings, run_id)
    record.comparison = compare(settings, with_faults=with_faults)
    record.comparison.difficulty = (difficulty if difficulty is not None
                                    else difficulty_table(settings, record.comparison))
    return record


def run_full_demo(settings: Settings, run_id: str = "demo") -> RunRecord:
    """Everything the dashboard shows: the closed-loop run with faults, plus both comparisons and the difficulty table."""
    record = run_closed_loop(settings, run_id)
    record.comparison = compare(settings, with_faults=False)
    record.comparison.difficulty = difficulty_table(settings, record.comparison)
    record.comparison_with_faults = compare(settings, with_faults=True)
    record.comparison_with_faults.difficulty = record.comparison.difficulty
    return record
