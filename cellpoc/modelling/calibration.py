"""Calibration: is the uncertainty a model states honest?

Every model states a 90% range. On the held-out groups of the 3a comparison we count how often the range really contained the truth. About 0.90 means honest; well below
means over-confident (ranges too narrow); well above means under-confident (wider than needed). Nothing is refitted: this works from the saved held-out predictions.

- **Hit rate** per hold-out type, with an error bar from resampling whole held-out groups (rows inside a group are not independent), when there are at least MIN_BOOTSTRAP_GROUPS groups.
- **Verdict**, fixed in advance: honest if the 90% hit rate is within HONEST_BAND in every hold-out type; over-confident if it is below the band in any; under-confident if above the band in any.
- **Recalibration**: a scale factor for the range, learned ONLY from the held-out errors of the OTHER folds and applied to the current fold, so the fold's own answers never enter it.
  For hold-outs forward in time only EARLIER steps are used, so a later step can never influence an earlier one. The hit rate is then re-measured on the fold.
- **Does it know when it is unsure?** The rank correlation between a row's stated range and its actual error. A model that states the same range for every recipe cannot say; that is reported as such.
Only the 90% range is stated by a model, so other levels (50%, 80%, 95%) show the same range rescaled as if errors were bell-shaped: they show shape, and the verdict never uses them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .findings import Finding, make
from .models import MODELS_BY_KEY
from .splits import _labels
from .validate import PlanRun, Validation, spread

HONEST_BAND = (0.85, 0.95)
LEVELS = {0.5: 0.6744897501960817, 0.8: 1.2815515655446004, 0.9: 1.6448536269514722, 0.95: 1.959963984540054}
MIN_BOOTSTRAP_GROUPS = 10
BOOTSTRAPS = 1000
BOOTSTRAP_SEED = 20261011
MIN_RECALIBRATION_ROWS = 30


@dataclass
class Pool:
    """Everything one model produced on the held-out folds of one hold-out type, as plain arrays."""
    u: np.ndarray            # |truth - prediction| divided by the stated 90% half-width: at most 1 means the 90% range contained the truth
    half: np.ndarray         # the stated 90% half-width
    fold: np.ndarray         # the fold of each row
    group: np.ndarray        # the held-out group of each row (text)
    abs_error: np.ndarray


@dataclass
class KindCalibration:
    kind: str
    heading: str
    n: int
    hit: float                               # the stated 90% range's hit rate
    ci: tuple[float, float] | None           # 95% error bar from resampling whole groups (None: too few groups)
    n_groups: int
    levels: dict[float, float]               # hit rate of the range rescaled to other levels (bell-shaped errors assumed)
    width: float                             # mean stated width divided by the result's spread
    spearman: float | None                   # does a wider stated range go with a larger error? None: the range is the same for every row
    fold_hits: list[float]
    recal_hit: float | None                  # hit rate after recalibration, on the folds that could be recalibrated
    recal_width: float | None
    factors: list[float | None]              # the scale factor of each fold (None: none could be learned)
    n_recalibrated: int = 0


@dataclass
class ModelCalibration:
    table: str
    result: str
    model: str
    role: str                                # "chosen" or "tie"
    kinds: dict[str, KindCalibration] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)              # folds that could not be recalibrated, and why

    @property
    def verdict(self) -> str:
        return verdict([k.hit for k in self.kinds.values()])

    @property
    def verdict_after(self) -> str | None:
        after = [k.recal_hit for k in self.kinds.values() if k.recal_hit is not None]
        return verdict(after) if len(after) == len([k for k in self.kinds.values()]) else None


def verdict(hits: list[float]) -> str:
    """honest, over-confident, under-confident or inconsistent, by the hit rate of the stated 90% range in every hold-out type."""
    if not hits:
        return "not measured"
    low, high = any(h < HONEST_BAND[0] for h in hits), any(h > HONEST_BAND[1] for h in hits)
    return "inconsistent" if low and high else "over-confident" if low else "under-confident" if high else "honest"


# ---------------------------------------------------------------- the recalibration factor (the guarded part)
def scale_factor(u_by_fold: dict[int, np.ndarray], fold: int, forward: bool = False) -> float | None:
    """The factor that makes the stated 90% range contain the truth 90% of the time, learned from the OTHER folds' held-out errors only.

    `u_by_fold` maps a fold number to the normalised errors (|error| / stated half-width) of its held-out rows. The current fold's own entry is never read.
    With `forward` (hold-outs in time) only folds with a smaller number, that is EARLIER steps, are used. None when fewer than MIN_RECALIBRATION_ROWS rows are available."""
    pool = [u for f, u in u_by_fold.items() if f != fold and (not forward or f < fold)]
    pooled = np.concatenate(pool) if pool else np.array([])
    n = len(pooled)
    if n < MIN_RECALIBRATION_ROWS:
        return None
    return float(np.quantile(pooled, min(1.0, math.ceil((n + 1) * 0.9) / n), method="higher"))


# ---------------------------------------------------------------- measuring one model on one hold-out type
def collect(run: PlanRun, key: str, frame, group_columns: tuple[str, ...], truth: dict | None = None) -> Pool | None:
    u, half, fold, group, err = [], [], [], [], []
    for f in run.folds:
        if key not in f.preds:
            continue
        p = f.preds[key]
        width = (p.hi - p.lo) / 2
        ok = np.isfinite(width) & (width > 0)
        if not ok.any():
            continue
        labels = _labels(frame, f.test, group_columns)[0].to_numpy() if frame is not None else np.array([str(f.number)] * len(f.test))
        error = np.abs(f.y - p.mean)
        u.append((error / width)[ok]); half.append(width[ok]); fold.append(np.full(ok.sum(), f.number)); group.append(labels[ok]); err.append(error[ok])
    if not u:
        return None
    return Pool(*(np.concatenate(a) for a in (u, half, fold, group, err)))


def _bootstrap(hit: np.ndarray, group: np.ndarray) -> tuple[float, float] | None:
    names, inverse = np.unique(group, return_inverse=True)
    if len(names) < MIN_BOOTSTRAP_GROUPS:
        return None
    hits, counts = np.bincount(inverse, weights=hit.astype(float)), np.bincount(inverse).astype(float)
    pick = np.random.default_rng(BOOTSTRAP_SEED).integers(0, len(names), size=(BOOTSTRAPS, len(names)))    # whole groups drawn with replacement
    rates = hits[pick].sum(axis=1) / counts[pick].sum(axis=1)
    return float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5))


def calibrate_kind(pool: Pool, kind: str, heading: str, sd: float) -> KindCalibration:
    hit = pool.u <= 1.0
    folds = sorted(set(pool.fold.tolist()))
    u_by_fold = {f: pool.u[pool.fold == f] for f in folds}
    forward = kind == "date"
    factors = [scale_factor(u_by_fold, f, forward) for f in folds]
    after = [(u_by_fold[f] <= s, pool.half[pool.fold == f] * s) for f, s in zip(folds, factors) if s is not None]
    # does a wider stated range go with a bigger error? Measured WITHIN each fold (a model that states one fixed range per fold cannot say), then averaged over the folds that can
    order = lambda a: np.argsort(np.argsort(a))                         # ranks, for a rank correlation without any extra library
    per_fold = []
    for f in folds:
        w, e = pool.half[pool.fold == f], pool.abs_error[pool.fold == f]
        if len(w) > 10 and float(np.ptp(w)) > 1e-9 * max(float(w.max()), 1e-300):
            per_fold.append((float(np.corrcoef(order(w), order(e))[0, 1]), len(w)))
    spearman = float(sum(c * n for c, n in per_fold) / sum(n for _, n in per_fold)) if per_fold else None
    return KindCalibration(
        kind, heading, len(pool.u), float(hit.mean()), _bootstrap(hit, pool.group), len(np.unique(pool.group)),
        {p: float((pool.u <= z / LEVELS[0.9]).mean()) for p, z in LEVELS.items()}, float(pool.half.mean() * 2 / sd), spearman,
        [float(hit[pool.fold == f].mean()) for f in folds],
        float(np.concatenate([a[0] for a in after]).mean()) if after else None, float(np.concatenate([a[1] for a in after]).mean() * 2 / sd) if after else None,
        factors, len(after))


def calibrate(validation: Validation, result: str, model: str, role: str) -> ModelCalibration:
    table = validation.table
    out = ModelCalibration(table.name, result, model, role)
    sd = spread(table, result)
    for (r, kind), run in validation.runs.items():
        if r != result or not run.plan.available:
            continue
        spec = table.groups[kind]
        pool = collect(run, model, table.frame, spec.columns)
        if pool is not None:
            kc = out.kinds[kind] = calibrate_kind(pool, kind, run.plan.heading, sd)
            missing = sum(f is None for f in kc.factors)
            if missing:
                why = "the first forward step has no earlier step to learn from" if kind == "date" else "too few held-out rows in the other folds"
                out.findings.append(make("M52", "", table.name, f"{table.column_label(result)}, {MODELS_BY_KEY[model].label}, {run.plan.heading}", n=missing, why=why))
    return out
