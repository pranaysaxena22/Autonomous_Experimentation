"""The shapes the job queue shares between the scheduler, the simulation and the console: a job, the ingredients on the shelf, the queue as a whole, and the one way a job can stop for want of an ingredient.

A job is one campaign for one drug: one setup, run from its first trial to its last. The cell does one job at a time, so jobs are never simultaneous; the queue lists them in order and says where each one stands.
Everything here is illustrative: the shelf is a mock, and how the real scheduler will choose what to run next is not decided yet (see cellpoc/scheduler/policy.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

PENDING, IN_PROGRESS, COMPLETED, BLOCKED = "pending", "in progress", "completed", "blocked"
JOB_STATUSES = (PENDING, IN_PROGRESS, COMPLETED, BLOCKED)


class IngredientMissing(Exception):
    """An ingredient on the shelf cannot cover what the next batch needs. The job stops here and says so in plain words; it never fails silently."""

    def __init__(self, ingredient: str, label: str, needed_g: float, left_g: float):
        self.ingredient, self.label, self.needed_g, self.left_g = ingredient, label, needed_g, left_g
        super().__init__(self.message)

    @property
    def message(self) -> str:
        return f"{self.label} is missing: the next batch needs {self.needed_g:.2f} g and only {self.left_g:.2f} g is left."


@dataclass
class SupplyRecord:
    """One ingredient on the shelf."""
    ingredient: str                   # the setup's ingredient id, for example binder_pct
    label: str                        # what people call it, for example Binder
    left_g: float
    full_g: float                     # what a restock brings it back to (the bar's full length)


@dataclass
class JobRecord:
    """One job and where it stands. `reason` says why a blocked job stopped, in plain words; it is empty for every other status."""
    id: str
    drug: str                         # the name the queue shows, for example Drug 1
    setup_id: str                     # which setup it runs (the console's own list of choices)
    setup_label: str
    status: str                       # pending, in progress, completed or blocked
    reason: str = ""
    trials_started: int = 0
    trials_with_result: int = 0
    good: int = 0
    folder: str = ""                  # where the finished (or stopped) job's own run record was saved, relative to the project


@dataclass
class QueueRecord:
    """The whole queue at one moment: what the page shows."""
    jobs: list[JobRecord] = field(default_factory=list)
    supplies: list[SupplyRecord] = field(default_factory=list)
    automated: bool = False           # True while the queue runs itself, one job after another
    active: str | None = None         # the id of the job in progress, if any
