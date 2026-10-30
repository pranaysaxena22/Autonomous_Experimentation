"""THE SEALED ACCEPTANCE LAB. *** SYNTHETIC: it says nothing about real tablets. ***

A second virtual lab with a STRUCTURALLY DIFFERENT truth from the development lab (cellpoc/virtual_lab/_truth.py) and from the mock generator (tools/make_mock_data.py), used only to prove, at
the end of a stage, that a model or decision engine was not tuned to the lab it was developed against. It is sealed (see acceptance/README.md): its fingerprint is recorded in docs/decisions.md,
no development code or check may import, open or read it, and it is run only by the dedicated acceptance runner. Any other use is a violation and a new lab must be written.

How it differs in structure (not only in numbers):
- Dissolution is a MECHANISM: a Weibull release curve whose time scale comes from porosity (set by compression force), disintegrant swelling, binder and lubricant film, and drug load. The
  development lab's is a polynomial; the mock generator's is a polynomial plus a bump.
- Hardness follows a RYSHKEWITCH law: tensile strength falls exponentially with porosity, then converts to kP. The others use linear terms and interactions.
- Friability is a function of the true hardness AND of over-lubrication and lamination at very high force (a U-shape in force), so it is a real constraint (the mock generator's friability passes
  more than 99% of the time and constrains nothing).
- Batch and supplier effects act on the LATENT parameters (time scale, bonding strength, binder potency, compressibility), not as offsets added to the answers.
- Noise is heteroscedastic: dissolution scatter is largest mid-curve, hardness scatter grows with hardness, friability scatter is multiplicative.
- The history this lab can generate (see `history`) lets the supplier and the date SHIFT THE RECIPES: each batch draws a campaign centre, the mix of centres drifts with the date, and each
  centre favours certain suppliers and filler grades. So input-based warnings can be tested under a supplier or date shift (the development mocks cannot do that).

Interface (all the acceptance runner needs): `SealedLab(seed)` with `measure` (what an instrument would report, noisy), `history` (past experiments in the mock CSV's 21 columns, observations
only) and, for scoring AFTER the fact only, `truth` and `is_good`.
"""
from __future__ import annotations

import math
import zlib

import numpy as np
import pandas as pd

VERSION = 1
SEALED_SEEDS = tuple(range(7_000_101, 7_000_141))          # the 40 acceptance campaigns (version 2: moved from 7,000,001-7,000,040, see README); never generated, run or examined before sealing
TARGETS = {"dissolution_30min_pct": ("at_least", 85.0), "hardness_kp": ("between", 6.0, 10.0), "friability_pct": ("at_most", 1.0)}
RANGES = {"drug_pct": (10.0, 30.0), "binder_pct": (2.0, 6.0), "disintegrant_pct": (1.0, 8.0), "lubricant_pct": (0.25, 2.0),
          "compression_force_kn": (5.0, 20.0), "blend_time_min": (5.0, 30.0)}
FILLER_RANGE = (54.0, 86.75)                               # the balance ingredient: 100 minus the others
SUPPLIERS, GRADES, INSTRUMENTS = ("A", "B", "C"), ("MCC-101", "MCC-102"), ("DT-1", "DT-2")
SUPPLIER_BINDER = {"A": 1.00, "B": 0.88, "C": 1.12}         # how potent each supplier's binder is
GRADE_COMPRESSIBILITY = {"MCC-101": 1.00, "MCC-102": 1.14}

# the mechanism's constants
EPS_MIN, EPS_MAX, KAPPA = 0.07, 0.42, 0.13
STRENGTH_0, BOND_SLOPE, POROSITY_SLOPE, KP_PER_MPA = 9.0, 0.22, 6.0, 3.4
TAU_0, TAU_POROSITY = 22.0, 8.0
CENTRES = np.array([[0.20, 0.30, 0.35, 0.60, 0.40], [0.40, 0.45, 0.70, 0.30, 0.75], [0.60, 0.60, 0.20, 0.45, 0.60], [0.80, 0.75, 0.85, 0.70, 0.30]])
CENTRE_TIME = np.array([0.10, 0.40, 0.70, 1.00])
CENTRE_SUPPLIER = np.array([[0.85, 0.08, 0.07], [0.07, 0.85, 0.08], [0.08, 0.07, 0.85], [0.34, 0.33, 0.33]])
CENTRE_GRADE = np.array([0.85, 0.20, 0.60, 0.35])           # the chance of grade MCC-101 at each centre
COLUMNS = ["experiment_id", "replicate_no", "date", "batch_id", "drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "binder_supplier", "filler_grade",
           "compression_force_kN", "blend_time_min", "dissolution_instrument", "dissolution_30min_pct", "hardness", "hardness_unit", "friability_pct", "friability_note", "status", "failure_reason"]


def _stream(*key) -> np.random.Generator:
    """A random stream that depends only on its key (never on the order things are asked in)."""
    return np.random.default_rng([zlib.crc32(str(k).encode()) for k in key])


class SealedLab:
    def __init__(self, seed: int):
        self.seed = int(seed)

    # ------------------------------------------------------------------ the hidden truth (scoring only)
    def _batch(self, batch_id: str) -> tuple[float, float]:
        """A batch shifts the latent time scale and bonding strength (multiplicatively), not the answers."""
        g = _stream("batch", self.seed, batch_id)
        return float(math.exp(g.normal(0.0, 0.07))), float(math.exp(g.normal(0.0, 0.05)))

    def truth(self, recipe: dict, supplier: str = "A", grade: str = "MCC-101", batch_id: str | None = None) -> dict:
        """Noise-free results. With no batch the batch shifts are 1 (a typical batch)."""
        tau_shift, bond_shift = self._batch(batch_id) if batch_id else (1.0, 1.0)
        drug, binder, dis, lube = (recipe[k] for k in ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct"))
        force, blend = recipe["compression_force_kn"], recipe["blend_time_min"]
        binder_eff = binder * SUPPLIER_BINDER[supplier]
        kappa = KAPPA * GRADE_COMPRESSIBILITY[grade] * (1.0 + 0.03 * (binder - 4.0))
        eps = EPS_MIN + (EPS_MAX - EPS_MIN) * math.exp(-kappa * force)                      # porosity falls with compression force
        film = lube * (blend / 15.0) ** 0.8                                                   # lubricant film grows with blending
        sigma = (STRENGTH_0 * bond_shift * (1.0 + BOND_SLOPE * (binder_eff - 4.0)) / (1.0 + 0.30 * film) * (1.0 - 0.010 * (drug - 10.0))
                 * math.exp(-POROSITY_SLOPE * eps))                                          # Ryshkewitch: strength falls exponentially with porosity
        hardness = sigma * KP_PER_MPA
        tau = (TAU_0 * tau_shift * math.exp(-TAU_POROSITY * (eps - 0.17)) * (1.0 + 0.10 * (binder_eff - 4.0)) / (1.0 + 0.30 * dis ** 0.75)
               * (1.0 + 0.50 * lube ** 1.2 * (blend / 15.0) ** 0.6) * (1.0 + 0.012 * (drug - 10.0)))
        beta = 1.0 + 0.04 * dis
        dissolution = 100.0 * (1.0 - math.exp(-((30.0 / tau) ** beta)))                     # Weibull release at 30 minutes
        friability = (6.0 * math.exp(-0.33 * hardness) + 0.12 * max(0.0, lube - 1.4) ** 2 * 10.0 + 0.9 * max(0.0, 0.095 - eps) / 0.02)
        return {"dissolution_30min_pct": dissolution, "hardness_kp": hardness, "friability_pct": friability}

    @staticmethod
    def is_good(truth: dict) -> bool:
        """True when every target is truly met (used for scoring after the fact, never by an engine)."""
        return (truth["dissolution_30min_pct"] >= TARGETS["dissolution_30min_pct"][1]
                and TARGETS["hardness_kp"][1] <= truth["hardness_kp"] <= TARGETS["hardness_kp"][2]
                and truth["friability_pct"] <= TARGETS["friability_pct"][1])

    # ------------------------------------------------------------------ what an instrument reports
    def measure(self, trial_id: int, recipe: dict, supplier: str = "A", grade: str = "MCC-101", batch_id: str = "B000", instrument: str = "DT-1", day_fraction: float = 0.0) -> dict:
        """One noisy measurement. The noise depends only on (seed, trial_id), so a trial always reads the same whatever order trials are run in."""
        t = self.truth(recipe, supplier, grade, batch_id)
        g = _stream("measure", self.seed, trial_id)
        d = t["dissolution_30min_pct"]
        bias = (-0.015 - 0.03 * day_fraction) if instrument == "DT-2" else 0.0               # one of two testers reads low and drifts
        dissolution = d * (1.0 + bias) + g.normal(0.0, 0.6 + 0.035 * math.sqrt(max(d * (100.0 - d), 0.0)))
        hardness = t["hardness_kp"] + g.normal(0.0, 0.2 + 0.03 * t["hardness_kp"])
        friability = t["friability_pct"] * math.exp(g.normal(0.0, 0.18))
        return {"dissolution_30min_pct": min(100.0, max(0.0, dissolution)), "hardness_kp": max(0.0, hardness), "friability_pct": max(0.02, friability)}

    # ------------------------------------------------------------------ past experiments (observations only)
    def history(self, n_experiments: int) -> pd.DataFrame:
        """Past experiments in the mock CSV's 21 columns. Each batch draws a campaign centre; the mix of centres drifts with the date; each centre favours certain suppliers and grades."""
        g = _stream("history", self.seed, n_experiments)
        n_batches = max(4, n_experiments // 50)
        days = pd.bdate_range("2025-01-06", periods=int(n_batches * 1.6))
        batch_days = np.sort(g.choice(len(days), n_batches, replace=False))
        lows = np.array([RANGES[k][0] for k in ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kn")])
        spans = np.array([RANGES[k][1] - RANGES[k][0] for k in ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kn")])
        rows, trial = [], 0
        for e in range(n_experiments):
            b = e * n_batches // n_experiments
            frac = batch_days[b] / len(days)
            if e == 0 or (e * n_batches // n_experiments) != ((e - 1) * n_batches // n_experiments):          # a new batch: draw its centre, supplier, grade, instrument
                weights = np.exp(-((frac - CENTRE_TIME) ** 2) / (2 * 0.15 ** 2))
                centre = int(g.choice(len(CENTRES), p=weights / weights.sum()))
                supplier = SUPPLIERS[int(g.choice(3, p=CENTRE_SUPPLIER[centre]))]
                grade = GRADES[0] if g.random() < CENTRE_GRADE[centre] else GRADES[1]
                instrument = INSTRUMENTS[b % 2]
            u = np.clip(CENTRES[centre] + g.normal(0.0, 0.06, 5), 0, 1) if g.random() < 0.75 else g.random(5)
            drug, binder, dis, lube, force = lows + u * spans
            blend = float(g.uniform(*RANGES["blend_time_min"]))
            filler = 100.0 - drug - binder - dis - lube
            if not FILLER_RANGE[0] <= filler <= FILLER_RANGE[1]:
                continue
            recipe = {"drug_pct": drug, "binder_pct": binder, "disintegrant_pct": dis, "lubricant_pct": lube, "compression_force_kn": force, "blend_time_min": blend}
            batch_id = f"B{b + 1:03d}"
            for rep in range(1, (1 if g.random() > 0.15 else int(g.integers(2, 4))) + 1):
                trial += 1
                m = self.measure(trial, recipe, supplier, grade, batch_id, instrument, frac)
                rows.append({"experiment_id": f"E{e + 1:05d}", "replicate_no": rep, "date": days[batch_days[b]].date().isoformat(), "batch_id": batch_id, "drug_pct": round(drug, 2),
                             "filler_pct": round(filler, 2), "binder_pct": round(binder, 2), "disintegrant_pct": round(dis, 2), "lubricant_pct": round(lube, 2), "binder_supplier": supplier,
                             "filler_grade": grade, "compression_force_kN": round(force, 1), "blend_time_min": round(blend, 0), "dissolution_instrument": instrument,
                             "dissolution_30min_pct": round(m["dissolution_30min_pct"], 1), "hardness": round(m["hardness_kp"], 2), "hardness_unit": "kP",
                             "friability_pct": round(m["friability_pct"], 2), "friability_note": "", "status": "ok", "failure_reason": ""})
        return pd.DataFrame(rows, columns=COLUMNS)
