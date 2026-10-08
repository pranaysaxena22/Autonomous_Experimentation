"""The shape of the settings, once read and checked. Values only - no behaviour."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True)
class Display:
    banner: str
    accent_colour: str
    font: str


@dataclass(frozen=True)
class Ingredient:
    key: str
    label: str
    min: float
    max: float


@dataclass(frozen=True)
class DesignSpace:
    ingredients: tuple[Ingredient, ...]

    def get(self, key: str) -> Ingredient:
        for ingredient in self.ingredients:
            if ingredient.key == key:
                return ingredient
        raise KeyError(key)


@dataclass(frozen=True)
class DissolutionSpec:
    label: str
    unit: str
    minimum: float
    margin_scale: float


@dataclass(frozen=True)
class HardnessSpec:
    label: str
    unit: str
    minimum: float
    maximum: float


@dataclass(frozen=True)
class Specifications:
    dissolution: DissolutionSpec
    hardness: HardnessSpec


@dataclass(frozen=True)
class Step:
    name: str
    label: str
    duration_minutes: float


@dataclass(frozen=True)
class Phases:
    """Which steps belong to which of Sense / Reason / Act / Adapt."""
    act: tuple[str, ...]
    sense: tuple[str, ...]
    reason_adapt_step: str
    reason_minutes: float


@dataclass(frozen=True)
class Cell:
    steps: tuple[Step, ...]
    measurement_step: str
    phases: Phases

    @property
    def minutes_per_trial(self) -> float:
        return sum(step.duration_minutes for step in self.steps)


@dataclass(frozen=True)
class Run:
    start: datetime
    duration_hours: float
    random_seed: int


@dataclass(frozen=True)
class People:
    staffed_weekdays: tuple[int, ...]  # Monday = 0 ... Sunday = 6
    staffed_from: time
    staffed_until: time


@dataclass(frozen=True)
class Noise:
    dissolution_sd: float
    hardness_sd: float


@dataclass(frozen=True)
class ScriptedFault:
    trial: int
    station: str
    cause: str
    retry_succeeds: bool
    alert: str


@dataclass(frozen=True)
class ScriptedFaults:
    purge_minutes: float
    events: tuple[ScriptedFault, ...]
    clean_after_skip: bool = True

    @property
    def skipped_trials(self) -> frozenset[int]:
        """Trials whose retry also fails: no recipe is made and no result exists."""
        return frozenset(e.trial for e in self.events if not e.retry_succeeds)


@dataclass(frozen=True)
class EngineSettings:
    initial_recipes: int
    candidates_per_decision: int


@dataclass(frozen=True)
class Comparison:
    campaigns: int
    trials_per_campaign: int
    manual_baseline_trials_per_week: float


@dataclass(frozen=True)
class Settings:
    display: Display
    design_space: DesignSpace
    specifications: Specifications
    cell: Cell
    run: Run
    people: People
    noise: Noise
    scripted_faults: ScriptedFaults
    comparison: Comparison
    engine: EngineSettings
