"""The cell executor interface (docs/platform_plan.md, section 6).

The motion plan is data. A planner turns a recipe, the setup and the layout into a plan; an EXECUTOR runs the plan and returns what happened (an executed timeline: actual times, outcomes, instrument readings, faults and
the recovery actions it added). Three implementations of this one interface are planned: a Python stand-in (built), a Gazebo adapter (later) and real hardware (later). Each declares which actions it supports, and a plan it cannot
run is refused with a plain message. The simulator and the decision engine never know which executor ran.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ExecutorRefusal(Exception):
    """The executor will not run this plan or this fault. The message says why, in plain words."""


@dataclass(frozen=True)
class Fault:
    """A fault to apply to one trial: which action in which step goes wrong, why, and whether the single retry works."""
    step: str
    action: str
    cause: str
    retry_succeeds: bool
    ingredient: str | None = None                  # which ingredient's bottle, when the fault is at a pour
    source: str = "scripted"                       # scripted (on purpose, on a named trial) or random (by chance)

    @property
    def where(self) -> dict:
        w = {"step": self.step, "action": self.action}
        if self.ingredient:
            w["ingredient"] = self.ingredient
        return w


class ReadingProvider(Protocol):
    """Where an instrument's number comes from: the virtual lab now, the real instruments one day. The executor never sees how it is produced."""

    def reading(self, quantity: str) -> float | None: ...


class NoReadings:
    """A provider with no numbers, for working out only how long a trial takes."""

    def reading(self, quantity: str) -> float | None:
        return None


class Executor(Protocol):
    name: str
    supported_actions: frozenset[str]

    def check(self, plan: dict, layout: dict) -> list[str]: ...

    def execute(self, plan: dict, setup: dict, layout: dict, fault: Fault | None, readings: ReadingProvider, clean_after_skip: bool = True, plan_file: str | None = None) -> dict: ...
