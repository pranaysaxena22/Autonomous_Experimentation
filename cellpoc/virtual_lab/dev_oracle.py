"""Scoring-only access to the development lab's truth (Stage 4-2). PRIVATE to the virtual lab and the scoring: the engine never imports this."""
from __future__ import annotations

import numpy as np

from . import _dev_truth as truth
from ..contracts import TrialContext
from ..contracts.seeds import refuse_sealed_seed
from .dev_lab import PERIOD_STEP_FROM, DevLab, check_recipe


def true_results(lab: DevLab, trial_number: int, recipe: dict, context: TrialContext) -> dict:
    """The noise-free results the recipe would truly have at campaign trial `trial_number` in this context (including the batch's own shift and any true process step)."""
    check_recipe(recipe)
    batch_diss, batch_hard = lab._batch(context.batch_id)
    c = context.categories
    return truth.true_results(recipe, c["binder_supplier"], c["filler_grade"], batch_diss, batch_hard, lab.scenario.rough_dissolution, lab.scenario.step and trial_number >= PERIOD_STEP_FROM, lab.scenario.step_scale, lab.scenario.reshape_scale)


def is_good(results: dict) -> bool:
    """True when every target is truly met."""
    t = truth.TARGETS
    return (results["dissolution_30min_pct"] >= t["dissolution_30min_pct"][1] and t["hardness_kp"][1] <= results["hardness_kp"] <= t["hardness_kp"][2]
            and results["friability_pct"] <= t["friability_pct"][1])


def share_good_after_step(n: int, seed: int, step_scale: float) -> float:
    """The share of `n` random recipes that are truly good after a true process step `step_scale` times the original, in the plainest context (supplier A, grade MCC-101, a batch with no shift of its own).
    Used to confirm a harsher period_shift is still winnable (docs/decisions.md, Finding A)."""
    good = 0
    for recipe in random_recipes(n, seed):
        good += is_good(truth.true_results(recipe, "A", "MCC-101", 0.0, 0.0, False, True, step_scale))
    return good / n


def reshape_statistics(n: int, seed: int, reshape_scale: float) -> dict:
    """What the reshaping does to `n` random recipes in the plainest context (supplier A, grade MCC-101, a batch with no shift of its own): the rank correlation of their true dissolution before and after the change,
    the share that gain more than 3 points, the share that lose more than 3, and the share that are truly good afterwards. Used to qualify a size of the reshaped scenario (docs/decisions.md, N1 and N3)."""
    recipes = random_recipes(n, seed)
    before = [truth.true_results(r, "A", "MCC-101", 0.0, 0.0) for r in recipes]
    after = [truth.true_results(r, "A", "MCC-101", 0.0, 0.0, False, True, 0.0, reshape_scale) for r in recipes]
    d0 = np.array([b["dissolution_30min_pct"] for b in before])
    d1 = np.array([a["dissolution_30min_pct"] for a in after])
    rank = lambda v: np.argsort(np.argsort(v, kind="stable"), kind="stable").astype(float)
    return {"spearman": float(np.corrcoef(rank(d0), rank(d1))[0, 1]), "up_share": float(np.mean(d1 - d0 > 3.0)), "down_share": float(np.mean(d1 - d0 < -3.0)), "good_share_after": float(np.mean([is_good(a) for a in after]))}


def random_recipes(n: int, seed: int) -> list[dict]:
    """Recipes spread uniformly over the allowed design space (filler inside its range), for measuring how rare a good recipe is."""
    refuse_sealed_seed(seed, "the development lab's random-recipe draw")
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n:
        r = {k: float(rng.uniform(*truth.LIM[k])) for k in truth.LIM}
        if truth.FILLER_RANGE[0] <= truth.filler_of(r) <= truth.FILLER_RANGE[1]:
            out.append(r)
    return out
