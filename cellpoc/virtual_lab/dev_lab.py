"""The development lab (Stage 4-2): the world the decision engine is developed and compared against, with fresh seeds. SYNTHETIC. Not the sealed acceptance lab.

It answers any recipe in the allowed ranges (five ingredients with the filler as the balance, plus compression force and blend time) in a context (supplier, filler grade, tester, batch and time)
with noisy dissolution, hardness and friability, and it can generate a history of past experiments in the mock data's 21 columns (observations only, so a history goes through the same ingestion and
Stage 3 path as any data). Four fixed scenarios (SCENARIOS) combine the features the engine's rules are meant for:
- baseline: everything predictable, nothing shifts;
- new_supplier: in the history, each campaign centre favours a supplier and the mix of centres drifts with the date (so supplier and date move the recipes); in the campaign an UNSEEN supplier, D,
  takes over from trial NEW_SUPPLIER_FROM;
- period_shift: the same history shift, and from trial PERIOD_STEP_FROM of the campaign the product truly changes (a step in dissolution and hardness that no input shows);
- unpredictable_dissolution: dissolution has a rough surface that Stage 3 should not carry, nothing shifts.
The engine sees only measurements and the context. It never sees the truth: that lives in _dev_truth.py, reached only through dev_oracle.py by the scoring.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..contracts import TargetSpec, TrialContext
from ..contracts.seeds import refuse_sealed_seed
from . import _dev_truth as truth

NEW_SUPPLIER_FROM = 8                      # the campaign trial from which the unseen supplier D is in use (fixed in advance)
PERIOD_STEP_FROM = 6                       # the campaign trial from which the true process step applies (fixed in advance)
BATCH_TRIALS = 10                          # a campaign batch is this many trials long
SUPPLIERS_IN_HISTORY, GRADES, INSTRUMENTS = ("A", "B", "C"), ("MCC-101", "MCC-102"), ("DT-1", "DT-2")
CENTRES = np.array([[0.25, 0.60, 0.45, 0.35, 0.30], [0.55, 0.35, 0.65, 0.20, 0.50], [0.40, 0.50, 0.30, 0.55, 0.70]])      # campaign centres in the unit design space (drug, binder, disintegrant, lubricant, force)
CENTRE_TIME, CENTRE_WIDTH = np.array([0.15, 0.50, 0.85]), 0.20
CENTRE_SUPPLIER = np.array([[0.80, 0.10, 0.10], [0.10, 0.80, 0.10], [0.10, 0.10, 0.80]])
CENTRE_GRADE = np.array([0.80, 0.30, 0.60])                          # the chance of grade MCC-101 at each centre
COLUMNS = ["experiment_id", "replicate_no", "date", "batch_id", "drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "binder_supplier", "filler_grade",
           "compression_force_kN", "blend_time_min", "dissolution_instrument", "dissolution_30min_pct", "hardness", "hardness_unit", "friability_pct", "friability_note", "status", "failure_reason"]


@dataclass(frozen=True)
class DevScenario:
    name: str
    history_shift: bool = False               # supplier and date move the recipes in the history
    new_supplier: bool = False                # an unseen supplier takes over during the campaign
    step: bool = False                        # a true process step during the campaign
    rough_dissolution: bool = False           # an unlearnable dissolution surface
    step_scale: float = 1.0                   # how many times the original step (-6 dissolution, +0.8 hardness) the true process step is; 1.0 for every scenario in SCENARIOS
    reshape_scale: float = 0.0                # how far the relationship between recipe and dissolution changes shape after the change (the binder's effect reverses; 0.0 for every scenario in SCENARIOS)


SCENARIOS = {s.name: s for s in (DevScenario("baseline"), DevScenario("new_supplier", history_shift=True, new_supplier=True), DevScenario("period_shift", history_shift=True, step=True),
                                 DevScenario("unpredictable_dissolution", rough_dissolution=True))}


def period_shift_v2(step_scale: float) -> DevScenario:
    """Period shift, version 2: the same history and the same kind of step as `period_shift`, `step_scale` times as large (docs/decisions.md, Finding A). Not in SCENARIOS: it is not part of the four-scenario comparison."""
    return DevScenario("period_shift_v2", history_shift=True, step=True, step_scale=step_scale)


def reshaped(reshape_scale: float) -> DevScenario:
    """The reshaped scenario (docs/decisions.md, "the second scenario"): same history, same brief and same moment as period_shift, but no uniform step; instead, from the same trial, the binder's effect on dissolution reverses
    (`reshape_scale` x 24 x (binder share - 0.5)), so the ranking of recipes the model learned becomes wrong. Not in SCENARIOS."""
    return DevScenario("reshaped", history_shift=True, step=True, step_scale=0.0, reshape_scale=reshape_scale)


CONTEXT_COLUMNS = ("binder_supplier", "filler_grade", "dissolution_instrument")      # the columns that hold the context in a history


def make_context(supplier: str, grade: str, instrument: str, batch_id: str, day_fraction: float) -> TrialContext:
    """What is known about where and when a trial is run (the shared shape the engine reads; it is not the truth). The time is 0 to 1 over the history and above 1 for the campaign that follows it."""
    return TrialContext({"binder_supplier": supplier, "filler_grade": grade, "dissolution_instrument": instrument}, batch_id, day_fraction)


def _stream(*key) -> np.random.Generator:
    """A random stream that depends only on its key, never on the order things are asked in."""
    return np.random.default_rng([zlib.crc32(str(k).encode()) for k in key])


def check_recipe(recipe: dict) -> None:
    for key, (low, high) in truth.LIM.items():
        if not low <= recipe[key] <= high:
            raise ValueError(f"{key} is {recipe[key]}, outside the allowed range {low} to {high}.")
    filler = truth.filler_of(recipe)
    if not truth.FILLER_RANGE[0] <= filler <= truth.FILLER_RANGE[1]:
        raise ValueError(f"the filler would be {filler:.1f}%, outside the allowed range {truth.FILLER_RANGE[0]} to {truth.FILLER_RANGE[1]}%.")


class DevLab:
    def __init__(self, scenario: DevScenario, seed: int):
        refuse_sealed_seed(seed, "the development lab")                  # the code itself refuses a sealed acceptance seed
        self.scenario = scenario
        self.seed = int(seed)

    # ------------------------------------------------------------------ the campaign's context
    def context(self, trial_number: int) -> TrialContext:
        """The context of campaign trial `trial_number` (1, 2, ...): supplier A in the first batches, then D if the scenario brings the unseen supplier in."""
        supplier = "D" if self.scenario.new_supplier and trial_number >= NEW_SUPPLIER_FROM else "A"
        return make_context(supplier, "MCC-101", "DT-1", f"C{(trial_number - 1) // BATCH_TRIALS + 1:03d}", 1.0 + 0.01 * trial_number)

    # ------------------------------------------------------------------ what an instrument reports
    def _batch(self, batch_id: str) -> tuple[float, float]:
        g = _stream("dev-batch", self.seed, batch_id)
        return float(g.normal(0.0, 1.5)), float(g.normal(0.0, 0.25))

    def _observe(self, key, recipe: dict, ctx: TrialContext, step: bool) -> dict:
        check_recipe(recipe)
        batch_diss, batch_hard = self._batch(ctx.batch_id)
        c = ctx.categories
        t = truth.true_results(recipe, c["binder_supplier"], c["filler_grade"], batch_diss, batch_hard, self.scenario.rough_dissolution, step, self.scenario.step_scale, self.scenario.reshape_scale)
        g = _stream("dev-measure", self.seed, key)
        drift = truth.INSTRUMENT_DRIFT * ctx.day_fraction if c["dissolution_instrument"] == "DT-2" else 0.0
        diss = t["dissolution_30min_pct"] + drift + g.normal(0.0, 1.2 * (1 + 0.5 * (t["dissolution_30min_pct"] < 70)))
        return {"dissolution_30min_pct": min(100.0, max(0.0, diss)), "hardness_kp": max(0.0, t["hardness_kp"] + g.normal(0.0, 0.25)),
                "friability_pct": max(0.02, t["friability_pct"] + g.normal(0.0, 0.05))}

    def measure(self, trial_id: int, recipe: dict, context: TrialContext) -> dict:
        """One noisy measurement for campaign trial `trial_id`. The noise depends only on (seed, trial_id), so a trial always reads the same whatever order trials are run in."""
        return self._observe(("campaign", trial_id), recipe, context, self.scenario.step and trial_id >= PERIOD_STEP_FROM)

    # ------------------------------------------------------------------ past experiments (observations only)
    def history(self, n_experiments: int) -> pd.DataFrame:
        """Past experiments in the mock CSV's 21 columns. With history_shift, each batch draws a campaign centre whose mix drifts with the date and which favours a supplier and a grade."""
        g = _stream("dev-history", self.seed, n_experiments)
        n_batches = max(4, n_experiments // 50)
        days = pd.bdate_range("2025-01-06", periods=int(n_batches * 1.6))
        batch_days = np.sort(g.choice(len(days), n_batches, replace=False))
        keys = ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kn")
        lows = np.array([truth.LIM[k][0] for k in keys])
        spans = np.array([truth.LIM[k][1] - truth.LIM[k][0] for k in keys])
        rows, previous = [], -1
        for e in range(n_experiments):
            b = e * n_batches // n_experiments
            frac = batch_days[b] / len(days)
            if b != previous:                                                       # a new batch: draw its centre, supplier, grade and tester
                previous = b
                if self.scenario.history_shift:
                    w = np.exp(-((frac - CENTRE_TIME) ** 2) / (2 * CENTRE_WIDTH ** 2))
                    centre = int(g.choice(3, p=w / w.sum()))
                    supplier, grade = SUPPLIERS_IN_HISTORY[int(g.choice(3, p=CENTRE_SUPPLIER[centre]))], GRADES[0 if g.random() < CENTRE_GRADE[centre] else 1]
                else:
                    centre = int(g.integers(3))
                    supplier, grade = SUPPLIERS_IN_HISTORY[int(g.choice(3, p=[0.5, 0.3, 0.2]))], GRADES[0 if g.random() < 0.7 else 1]
                instrument = INSTRUMENTS[b % 2]
            u = np.clip(CENTRES[centre] + g.normal(0.0, 0.07, 5), 0, 1) if g.random() < 0.70 else g.random(5)
            drug, binder, dis, lube, force = lows + u * spans
            recipe = {"drug_pct": float(drug), "binder_pct": float(binder), "disintegrant_pct": float(dis), "lubricant_pct": float(lube), "compression_force_kn": float(force),
                      "blend_time_min": float(g.uniform(*truth.LIM["blend_time_min"]))}
            filler = truth.filler_of(recipe)
            if not truth.FILLER_RANGE[0] <= filler <= truth.FILLER_RANGE[1]:
                continue
            ctx = make_context(supplier, grade, instrument, f"B{b + 1:03d}", float(frac))
            for rep in range(1, (1 if g.random() > 0.15 else int(g.integers(2, 4))) + 1):
                m = self._observe(("history", e, rep), recipe, ctx, False)
                rows.append({"experiment_id": f"E{e + 1:05d}", "replicate_no": rep, "date": days[batch_days[b]].date().isoformat(), "batch_id": ctx.batch_id,
                             "drug_pct": round(drug, 2), "filler_pct": round(filler, 2), "binder_pct": round(binder, 2), "disintegrant_pct": round(dis, 2), "lubricant_pct": round(lube, 2),
                             "binder_supplier": supplier, "filler_grade": grade, "compression_force_kN": round(force, 1), "blend_time_min": round(recipe["blend_time_min"], 0),
                             "dissolution_instrument": instrument, "dissolution_30min_pct": round(m["dissolution_30min_pct"], 1), "hardness": round(m["hardness_kp"], 2), "hardness_unit": "kP",
                             "friability_pct": round(m["friability_pct"], 2), "friability_note": "", "status": "ok", "failure_reason": ""})
        return pd.DataFrame(rows, columns=COLUMNS)


# ---------------------------------------------------------------- what is public about the lab (the design space and the targets are set up facts, not truth)
HISTORY_SEEDS = {"baseline": 10101, "new_supplier": 10102, "period_shift": 10103, "unpredictable_dissolution": 10104}      # fresh seeds, fixed in advance, outside every campaign block
HISTORY_EXPERIMENTS = 3000
DESIGN_SPACE = dict(truth.LIM)                                                   # each controllable input's (lowest, highest)
FILLER_RANGE = truth.FILLER_RANGE
INGREDIENTS = ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct")    # the percentages; the balance ingredient is 100 minus them
LABELS = {"dissolution_30min_pct": "Dissolution at 30 min", "hardness_kp": "Hardness", "friability_pct": "Friability"}


def target_specs() -> dict:
    """The targets as the setup states them (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0), in the shared shape the engine reads."""
    out = {}
    for result, (goal, *limits) in truth.TARGETS.items():
        low = limits[0] if goal in ("at_least", "between") else None
        high = limits[1] if goal == "between" else limits[0] if goal == "at_most" else None
        out[result] = TargetSpec(result, LABELS[result], goal, low, high)
    return out


def cleaned_history(lab: DevLab, n_experiments: int = HISTORY_EXPERIMENTS) -> pd.DataFrame:
    """A history with the column names the modelling table uses (the engine's brief names its inputs by them)."""
    return lab.history(n_experiments).rename(columns={"compression_force_kN": "compression_force_kn", "hardness": "hardness_kp"})