"""The hidden truth of the DEVELOPMENT lab (Stage 4-2). PRIVATE to the virtual lab and the scoring.

Nothing outside cellpoc/virtual_lab and the scoring may import this file: the engine must discover the behaviour by experiment. This is the lab the engine is developed against, with fresh seeds;
it is NOT the sealed acceptance lab (which is structurally different and is never named by any code outside its own folder).

It is built from the mock data generator's formula (tools/make_mock_data.py, the 'easy' setting with no non-linear term): the same dissolution and hardness surfaces and the same supplier and
grade effects, so models developed on the mocks meet the same kind of world. A check compares this file with the generator on random recipes. What it ADDS to the generator:
- friability is a real constraint (the generator's friability passes more than 99% of the time and constrains nothing);
- a fourth supplier, D, that the history never contains (for a "new supplier" scenario);
- a true process step from a given trial (a "later period" that behaves differently, invisible in the inputs);
- an optional ROUGH dissolution surface: the same smooth formula, compressed, plus a high-frequency term. An oracle could still find the good recipes, but a smooth model cannot learn it
  from a few thousand experiments, so Stage 3 should not carry it (an "unpredictable by design" result).
"""
from __future__ import annotations

import math

# the ranges of the design space (the generator's own)
LIM = {"drug_pct": (10.0, 30.0), "binder_pct": (2.0, 6.0), "disintegrant_pct": (1.0, 8.0), "lubricant_pct": (0.25, 2.0), "compression_force_kn": (5.0, 20.0), "blend_time_min": (5.0, 30.0)}
FILLER_RANGE = (54.0, 86.75)                                            # the balance ingredient, 100 minus the others
SUPPLIER_EFFECT = {"A": (0.0, 0.0), "B": (-3.0, 0.35), "C": (1.5, -0.20), "D": (-6.0, 0.9)}      # (dissolution, hardness); A, B and C are the generator's own, D is new
GRADE_EFFECT = {"MCC-101": (0.0, 0.0), "MCC-102": (1.0, 0.30)}
INSTRUMENT_DRIFT = 3.0                                                  # the generator's 'easy' drift on tester DT-2, per unit of time
PERIOD_STEP = (-6.0, 0.8)                                               # a true process step (dissolution, hardness) from the scenario's step trial
ROUGH_SCALE, ROUGH_AMPLITUDE = 0.35, 20.0                               # the rough surface: how much the smooth part is compressed, and the size of the high-frequency term
# How many cycles the rough term makes across the range of drug load, binder, disintegrant and force. The first version used (3, 3.5, 2.5, 3): Stage 3's Gaussian process still learned it well enough to CARRY
# it (worst error 0.65 of the spread), so the lab missed its design. Second version, written down before it was tested: more than double the frequency, success = Stage 3 does not carry it.
ROUGH_CYCLES = (9.0, 7.0, 8.0, 7.0)
TARGETS = {"dissolution_30min_pct": ("at_least", 85.0), "hardness_kp": ("between", 6.0, 10.0), "friability_pct": ("at_most", 1.0)}


def filler_of(recipe: dict) -> float:
    return 100.0 - recipe["drug_pct"] - recipe["binder_pct"] - recipe["disintegrant_pct"] - recipe["lubricant_pct"]


def smooth_truth(recipe: dict) -> tuple[float, float]:
    """Dissolution and hardness exactly as tools/make_mock_data.py's truth() with inter=1 and no non-linear term."""
    drug, binder, dis, lube = recipe["drug_pct"], recipe["binder_pct"], recipe["disintegrant_pct"], recipe["lubricant_pct"]
    force, blend, filler = recipe["compression_force_kn"], recipe["blend_time_min"], filler_of(recipe)
    d, b, s, l = (drug - 10) / 20, (binder - 2) / 4, (dis - 1) / 7, (lube - 0.25) / 1.75
    f, fo, bt = (filler - 54) / (86.75 - 54), (force - 5) / 15, (blend - 5) / 25
    diss = (70 + 26 * s ** 0.65 - 12 * b - 10 * l - 8 * d ** 2 + 6 * math.exp(-(((f - 0.55) / 0.30) ** 2)) + 6 * s * (1 - b) - 6 * fo + 2 * bt - 4 * fo * b)
    hard = 5.2 + 4.6 * b + 2.0 * f - 3.2 * s - 1.8 * l - 1.0 * d + 1.8 * b * f + 3.5 * fo - 0.8 * bt * fo
    return diss, hard


def rough_term(recipe: dict) -> float:
    """A high-frequency surface over the design space (several cycles across each range): easy for an oracle to read, impossible for a smooth model to learn from a few thousand rows."""
    u = [(recipe[k] - LIM[k][0]) / (LIM[k][1] - LIM[k][0]) for k in ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kn")]
    c = ROUGH_CYCLES
    return (math.sin(2 * math.pi * (c[0] * u[0] + 1.7)) * math.sin(2 * math.pi * (c[2] * u[2] + 0.4))
            + 0.7 * math.sin(2 * math.pi * (c[1] * u[1] + 0.9)) * math.sin(2 * math.pi * (c[3] * u[4] + 0.2)))


def friability_of(recipe: dict, hardness: float) -> float:
    """Friability in %: falls as the tablet gets harder, rises with lubricant (weak surface bonding) and with drug load. A real constraint, unlike the generator's."""
    l = (recipe["lubricant_pct"] - 0.25) / 1.75
    d = (recipe["drug_pct"] - 10) / 20
    return max(0.02, FRIABILITY_BASE - FRIABILITY_SLOPE * hardness + FRIABILITY_LUBE * l * l + FRIABILITY_DRUG * d)


FRIABILITY_BASE, FRIABILITY_SLOPE, FRIABILITY_LUBE, FRIABILITY_DRUG = 2.3, 0.24, 0.8, 0.3


RESHAPE = 24.0                                                          # the size of the binder reversal (see true_results): at reshape_scale 1 the binder's effect on dissolution, -12 per unit, becomes +12


def true_results(recipe: dict, supplier: str, grade: str, batch_diss: float, batch_hard: float, rough: bool = False, step: bool = False, step_scale: float = 1.0, reshape_scale: float = 0.0) -> dict:
    """Noise-free results for a recipe in a context. `batch_diss` and `batch_hard` are the batch's own shifts; `step` (the moment after the change) applies the true process step, `step_scale` times its size
    (1.0 is the original period_shift), and the reshaping, `reshape_scale` x 24 x (binder share - 0.5): recipes with little binder lose dissolution, recipes with much binder gain it (0.0 is no reshaping)."""
    diss, hard = smooth_truth(recipe)
    if rough:
        diss = 70.0 + ROUGH_SCALE * (diss - 70.0) + ROUGH_AMPLITUDE * rough_term(recipe)
    sd, sh = SUPPLIER_EFFECT[supplier]
    gd, gh = GRADE_EFFECT[grade]
    diss, hard = diss + sd + gd + batch_diss, hard + sh + gh + batch_hard
    if step:
        diss, hard = diss + PERIOD_STEP[0] * step_scale, hard + PERIOD_STEP[1] * step_scale
        if reshape_scale:
            low, high = LIM["binder_pct"]
            diss += RESHAPE * reshape_scale * ((recipe["binder_pct"] - low) / (high - low) - 0.5)
    hard = max(0.0, hard)
    return {"dissolution_30min_pct": min(100.0, max(0.0, diss)), "hardness_kp": hard, "friability_pct": friability_of(recipe, hard)}
