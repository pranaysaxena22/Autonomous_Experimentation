"""The connected world: what the cell simulator talks to when the loop is connected. It plays three roles for the simulator and nothing else.

- As the STRATEGY it asks the adopted decision engine (the recalibrated engine, Stage 4) for the next recipe, giving it only what an engine may see: the experiment table read from the client's file (its history), the measurements made so far and the
  context a trial runs in. It never sees the lab's truth; a trial with no result (a skipped candidate) is simply absent from what it is given, as the engine was built to expect.
- As the LAB it measures a recipe in the development lab (the synthetic world the file's history came from) and keeps the measurement for the engine.
- As the SOURCE OF RECIPES it gives the planner the engine's whole recipe, the process settings (compression force, blend time) included, which the proof of concept's strategies never chose.

The engine, the lab, the planner and the executor are the existing ones, unchanged.
"""
from __future__ import annotations

from ..contracts import Formulation, Measurement, Observation, Proposal
from ..decision_engine.recalibrated import RecalibratedStrategy
from ..virtual_lab.dev_lab import DESIGN_SPACE, FILLER_RANGE, INGREDIENTS, SCENARIOS, DevLab, target_specs
from .chain import Chain

PLATFORM_IDS = ("drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct")
FORMULATION_OF = {"drug_pct": "drug", "filler_pct": "filler", "binder_pct": "binder", "disintegrant_pct": "disintegrant", "lubricant_pct": "lubricant"}
PROCESS = ("compression_force_kn", "blend_time_min")


def _key(formulation: Formulation) -> tuple:
    return formulation.as_tuple()


class ConnectedReadings:
    """A trial's instrument numbers, taken from the connected lab the first time one is needed. The cell reads dissolution and hardness; friability is modelled by the engine but not read by this cell's instruments."""

    real = True

    def __init__(self, world: "ConnectedWorld", trial: int, formulation: Formulation):
        self._world, self._trial, self._formulation = world, trial, formulation
        self._m: Measurement | None = None

    def measurement(self) -> Measurement:
        if self._m is None:
            self._m = self._world.measure(self._trial, self._formulation)
        return self._m

    def reading(self, quantity: str) -> float | None:
        m = self.measurement()
        return {"dissolution_30min_pct": m.dissolution_pct, "hardness_kp": m.hardness_kp}.get(quantity)


class ConnectedWorld:
    name = "recalibrated"
    description = "The adopted decision engine (Stage 4), choosing each recipe from the client's experiment table, what Stage 3 concluded about it and the measurements so far"

    def __init__(self, chain: Chain, seed: int):
        self.chain, self.seed = chain, int(seed)
        self.lab = DevLab(SCENARIOS[chain.scenario], self.seed)
        self.engine = RecalibratedStrategy(chain.brief, target_specs(), chain.history, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), self.seed)
        self.observations: list[Observation] = []
        self.decisions: dict[int, object] = {}               # trial number -> the engine's Decision
        self._pending: dict[tuple, tuple] = {}               # a proposal's formulation -> (decision, context, trial number)

    # ---- as the strategy
    def propose(self, trial_number: int, history, skipped=()) -> Proposal:
        context = self.lab.context(trial_number)
        decision = self.engine.propose(trial_number, context, tuple(self.observations))
        r = decision.recipe
        filler = 100.0 - sum(r[k] for k in INGREDIENTS)
        formulation = Formulation(r["drug_pct"], filler, r["binder_pct"], r["disintegrant_pct"], r["lubricant_pct"])
        self._pending[_key(formulation)] = (decision, context, trial_number)
        self.decisions[trial_number] = decision
        return Proposal(formulation, decision.why.rstrip(". "))

    # ---- as the source of recipes for the planner
    def recipe_for(self, formulation: Formulation) -> dict:
        decision = self._pending[_key(formulation)][0]
        recipe = {pid: getattr(formulation, FORMULATION_OF[pid]) for pid in PLATFORM_IDS}
        recipe.update({k: decision.recipe[k] for k in PROCESS})
        return recipe

    def readings(self, trial: int, formulation: Formulation) -> ConnectedReadings:
        return ConnectedReadings(self, trial, formulation)

    # ---- as the lab
    def measure(self, trial_id: int, formulation: Formulation) -> Measurement:
        decision, context, number = self._pending[_key(formulation)]
        results = self.lab.measure(number, decision.recipe, context)
        self.observations.append(Observation(number, decision.recipe, context, results))
        return Measurement(trial_id, formulation, results["dissolution_30min_pct"], results["hardness_kp"])
