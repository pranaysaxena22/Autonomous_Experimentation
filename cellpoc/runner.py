"""Wires the parts together and runs simulations. The only place that knows all of them.

Run `python -m cellpoc.runner` (or double-click build_demo.bat) to build the run record the dashboard shows.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from . import run_store
from .about_text import build_about
from .cell_simulator import simulate
from .comparison import compare
from .comparison.difficulty import difficulty_table
from .contracts import DifficultyRow, RunRecord
from .decision_engine import AdaptiveStrategy, FixedListStrategy
from .settings import Settings, load_settings
from .virtual_lab import VirtualLab

DEMO_FOLDER = Path(__file__).resolve().parents[1] / "runs" / "demo"


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


def run_other_cleaning(settings: Settings, run_id: str = "closed-loop-other-cleaning") -> RunRecord:
    """The same closed-loop run with the cleaning-after-skip setting flipped, to show how the trial count depends on it."""
    flipped = dataclasses.replace(settings.scripted_faults, clean_after_skip=not settings.scripted_faults.clean_after_skip)
    return run_closed_loop(dataclasses.replace(settings, scripted_faults=flipped), run_id)


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
    """Everything the dashboard shows: the closed-loop run with faults, plus both comparisons, the difficulty table
    and the plain-language notes."""
    record = run_closed_loop(settings, run_id)
    record.comparison = compare(settings, with_faults=False)
    record.comparison.difficulty = difficulty_table(settings, record.comparison)
    record.comparison_with_faults = compare(settings, with_faults=True)
    record.comparison_with_faults.difficulty = record.comparison.difficulty
    record.about = build_about(settings, record, run_other_cleaning(settings), record.comparison)
    return record


def build_demo(settings: Settings | None = None, folder: Path | str = DEMO_FOLDER) -> Path:
    """Run everything and save the record the dashboard reads. Takes about two minutes."""
    record = run_full_demo(settings or load_settings())
    return run_store.save(record, folder)


if __name__ == "__main__":
    print("Building the demonstration run record (about two minutes)...", flush=True)
    print(f"Saved: {build_demo()}")
