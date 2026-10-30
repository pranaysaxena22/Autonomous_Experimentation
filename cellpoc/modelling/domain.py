"""The applicability-domain warning: is this recipe far from the data the model learned from?

Stage 3b-1 found that no model's stated range tracks its own error, so this warning is the platform's main safeguard. It looks only at the INPUTS (never at a result, a model
or a held-out answer), in the space the models themselves work in (numeric inputs standardised on the training rows, categories as 0/1 columns). A recipe is warned when
 (a) DISTANCE: its mean distance to the K_NEIGHBOURS nearest training rows is above a threshold, the QUANTILE (95th) percentile of the same distance for the training rows themselves,
     each measured only against training rows from OTHER groups (leave-one-group-out), so the threshold mimics how far a whole new group normally sits from the data; or
 (b) RANGE: a numeric input is beyond the training range by more than RANGE_TOLERANCE of that input's training range, or a category was never seen in training.
Everything is fixed in advance and set from the training rows of a fold alone: nothing about the held-out rows can reach the threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .findings import Finding, make
from .models import Encoder
from .splits import _labels
from .validate import Validation

K_NEIGHBOURS = 5
QUANTILE = 0.95
RANGE_TOLERANCE = 0.10
FAR_SHIFT = 8.0                  # standard deviations: how far a deliberately far-away recipe is pushed on every numeric input
MIN_REFERENCE_ROWS = 30          # fewest training rows with a usable reference distance for a threshold to be set
STABLE_RATIO, VARYING_RATIO = 1.25, 1.5


@dataclass
class Reference:
    """Everything the warning knows, learned from the training rows of ONE fold."""
    encoder: Encoder
    train_encoded: np.ndarray
    low: np.ndarray
    high: np.ndarray
    levels: dict[str, set]
    numeric: list[str]
    categorical: list[str]
    threshold: float | None                       # None: too few groups or rows to set one
    n_groups: int = 0


@dataclass
class Warnings:
    distance: np.ndarray
    by_distance: np.ndarray
    by_range: np.ndarray
    by_category: np.ndarray
    out_of_range_inputs: dict[str, int] = field(default_factory=dict)       # which inputs went out of range, and how often
    unseen: dict[str, dict[str, int]] = field(default_factory=dict)         # which category values were never seen in training, and how many rows have each
    # There is deliberately no combined "warned" flag: each check is its own status and is reported as such.


def _distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    squared = (a ** 2).sum(1)[:, None] + (b ** 2).sum(1)[None, :] - 2 * a @ b.T
    return np.sqrt(np.clip(squared, 0.0, None))


def _mean_nearest(distances: np.ndarray, k: int = K_NEIGHBOURS) -> np.ndarray:
    k = min(k, distances.shape[1])
    return np.partition(distances, k - 1, axis=1)[:, :k].mean(axis=1)


def fit_reference(frame: pd.DataFrame, numeric: list[str], categorical: list[str], train: np.ndarray, groups: np.ndarray) -> Reference:
    """Learn the warning from the training rows only. `groups` names the group of each training row (same order as `train`)."""
    part = frame.iloc[train]
    encoder = Encoder(numeric, categorical).fit(part)
    encoded = encoder.transform(part)
    raw = part[numeric].to_numpy(dtype=float) if numeric else np.zeros((len(part), 0))
    threshold, names = None, np.unique(groups)
    if len(names) >= 2:
        d = _distances(encoded, encoded)
        d[groups[:, None] == groups[None, :]] = np.inf                    # a row is never compared with its own group
        usable = np.isfinite(d).sum(axis=1) >= K_NEIGHBOURS
        if usable.sum() >= MIN_REFERENCE_ROWS:
            threshold = float(np.quantile(_mean_nearest(d[usable]), QUANTILE))
    return Reference(encoder, encoded, raw.min(axis=0) if raw.size else raw[0:0].sum(0), raw.max(axis=0) if raw.size else raw[0:0].sum(0),
                     {c: set(part[c].astype(str)) for c in categorical}, list(numeric), list(categorical), threshold, len(names))


def warn(reference: Reference, frame: pd.DataFrame, positions: np.ndarray, far: bool = False) -> Warnings:
    """Which of the given rows are warned. With `far`, every numeric input is first pushed FAR_SHIFT standard deviations away in the space the distance is measured in (a deliberately far-away recipe,
    for testing the DISTANCE check on its own; the range check always looks at the real values)."""
    part = frame.iloc[positions]
    encoded = reference.encoder.transform(part)
    if far and reference.encoder.n_numeric:
        encoded = encoded.copy()
        encoded[:, :reference.encoder.n_numeric] += FAR_SHIFT
    distance = _mean_nearest(_distances(encoded, reference.train_encoded))
    by_distance = distance > reference.threshold if reference.threshold is not None else np.zeros(len(part), bool)
    counts: dict[str, int] = {}
    by_range = np.zeros(len(part), bool)
    if reference.numeric:
        raw = part[reference.numeric].to_numpy(dtype=float)
        slack = RANGE_TOLERANCE * (reference.high - reference.low)
        outside = (raw < reference.low - slack) | (raw > reference.high + slack)
        by_range = outside.any(axis=1)
        counts = {name: int(c) for name, c in zip(reference.numeric, outside.sum(axis=0)) if c}
    by_category = np.zeros(len(part), bool)
    unseen: dict[str, dict[str, int]] = {}
    for c in reference.categorical:
        values = part[c].astype(str)
        new = ~values.isin(reference.levels[c]).to_numpy()
        by_category |= new
        if new.any():
            unseen[c] = {str(k): int(v) for k, v in values[new].value_counts().items()}
    return Warnings(distance, by_distance, by_range, by_category, counts, unseen)


# ---------------------------------------------------------------- evaluating the warning on the saved Stage 3a folds
@dataclass
class FoldDomain:
    number: int
    n: int
    threshold: float | None
    rates: dict[str, float]                # the share of this fold's held-out rows warned by each check separately
    far_rate: float | None
    reference_groups: int


@dataclass
class Component:
    """How one of the warning's checks did on the held-out rows of one hold-out type."""
    share: float                           # the share of held-out rows it warned
    n_warned: int
    error_ratio: float | None              # mean absolute error of warned rows over that of unwarned rows (None: fewer than 10 of either)
    capture: float | None                  # the share of the 10% largest errors that it warned
    lift: float | None                     # that share divided by the share warned overall (above 1 means it picks out the bad rows)


@dataclass
class KindDomain:
    kind: str
    heading: str
    folds: list[FoldDomain]
    n: int
    parts: dict[str, Component]            # "distance", "range" (a numeric input out of range) and "category" (a supplier or product value never seen in training): three separate statuses
    far: float                             # share of deliberately far-away copies of the held-out rows that the DISTANCE check warned
    rank_correlation: float | None         # rank correlation of distance with error, within folds
    top_inputs: list[tuple[str, int]]      # inputs most often out of range
    unseen: list[tuple[str, str, int]]     # (input, value never seen in training, held-out rows with it), most rows first


def component(flag: np.ndarray, err: np.ndarray, big: np.ndarray) -> Component:
    """How well one check picks out the bad rows: the error of warned rows against unwarned rows, and how many of the largest errors it caught compared with chance."""
    n_warned = int(flag.sum())
    ratio = float(err[flag].mean() / err[~flag].mean()) if n_warned >= 10 and (~flag).sum() >= 10 and err[~flag].mean() > 0 else None
    capture = float(flag[big].mean()) if n_warned else 0.0
    return Component(float(flag.mean()), n_warned, ratio, capture, capture / float(flag.mean()) if flag.mean() > 0 else None)


def swing_findings(table_name: str, place: str, thresholds: list) -> list[Finding]:
    """The messages about a list of per-fold thresholds: any fold with none (M60), and whether the rest are steady (M61, only when they are not)."""
    found = []
    missing = sum(t is None for t in thresholds)
    if missing:
        found.append(make("M60", "", table_name, place, n=missing))
    swing = threshold_swing(thresholds)
    if swing and swing[1] != "stable":
        found.append(make("M61", "", table_name, place, verdict={"varying": "varies", "swinging": "swings"}[swing[1]], ratio=f"{swing[0]:.2f}", stable=STABLE_RATIO, varying=VARYING_RATIO))
    return found


def threshold_swing(values: list[float]) -> tuple[float, str] | None:
    """(largest over smallest, 'stable' / 'varying' / 'swinging') for a list of per-fold thresholds or factors; None with fewer than two."""
    values = [v for v in values if v is not None and v > 0]
    if len(values) < 2:
        return None
    ratio = max(values) / min(values)
    return ratio, "stable" if ratio <= STABLE_RATIO else "varying" if ratio <= VARYING_RATIO else "swinging"


def evaluate_kind(validation: Validation, result: str, kind: str, model: str, reference_kind: str | None = None, references: dict | None = None) -> KindDomain | None:
    """The warning on every held-out fold of one hold-out type, measured against one model's saved held-out errors.
    `reference_kind` chooses the groups the threshold is measured against (default: the hold-out's own kind). `references` is a cache shared between results with the same inputs."""
    table = validation.table
    run = validation.runs.get((result, kind))
    if run is None or not run.plan.available:
        return None
    rt = table.responses[result]
    spec = table.groups[reference_kind or kind]
    cache = references if references is not None else {}
    folds, err, dist, fold_of, top, seen = [], [], [], [], {}, {}
    flags: dict[str, list] = {"distance": [], "range": [], "category": []}
    trains = {fold.number: fold.train for fold in run.plan.folds}              # the training rows of each fold live on the plan; the saved results hold the test rows
    for f in run.folds:
        train = trains[f.number]
        key = (table.name, tuple(rt.numeric), tuple(rt.categorical), reference_kind or kind, hash(train.tobytes()))
        ref = cache.get(key) if key in cache else cache.setdefault(key, fit_reference(table.frame, rt.numeric, rt.categorical, train, _labels(table.frame, train, spec.columns)[0].to_numpy()))
        real, far = warn(ref, table.frame, f.test), warn(ref, table.frame, f.test, far=True)
        folds.append(FoldDomain(f.number, len(f.test), ref.threshold, {"distance": float(real.by_distance.mean()), "range": float(real.by_range.mean()), "category": float(real.by_category.mean())},
                                float(far.by_distance.mean()), ref.n_groups))
        if model in f.preds:
            err.append(np.abs(f.y - f.preds[model].mean))
            dist.append(real.distance)
            fold_of.append(np.full(len(f.test), f.number))
            for name, flag in (("distance", real.by_distance), ("range", real.by_range), ("category", real.by_category)):
                flags[name].append(flag)
        for name, c in real.out_of_range_inputs.items():
            top[name] = top.get(name, 0) + c
        for column, values in real.unseen.items():
            for value, c in values.items():
                seen[(column, value)] = seen.get((column, value), 0) + c
    if not err:
        return None
    err, dist, fold_of = (np.concatenate(a) for a in (err, dist, fold_of))
    big = err >= np.quantile(err, 0.9)
    parts = {name: component(np.concatenate(v), err, big) for name, v in flags.items()}
    order = lambda a: np.argsort(np.argsort(a))
    rho = [(float(np.corrcoef(order(dist[fold_of == k]), order(err[fold_of == k]))[0, 1]), int((fold_of == k).sum())) for k in np.unique(fold_of) if (fold_of == k).sum() > 10 and np.ptp(dist[fold_of == k]) > 0]
    return KindDomain(kind, run.plan.heading, folds, len(err), parts, float(np.mean([f.far_rate for f in folds])),
                      float(sum(c * n for c, n in rho) / sum(n for _, n in rho)) if rho else None, sorted(top.items(), key=lambda kv: -kv[1])[:3],
                      sorted(((c, v, n) for (c, v), n in seen.items()), key=lambda x: -x[2])[:4])

# ---------------------------------------------------------------- is the threshold itself stable when the data shifts?
@dataclass
class Stability:
    kind: str
    thresholds: list[float | None]                 # the warning's threshold on each fold (default reference groups: the hold-out's own kind)
    swing: tuple[float, str] | None
    batch_thresholds: list[float | None] | None    # the same, with the reference groups always taken to be batches (a diagnostic)
    batch_swing: tuple[float, str] | None
    factor_swing: tuple[float, str] | None         # the recalibration scale factors of the same folds, for comparison
    rates: dict[str, list[float]]                  # for each check separately, the share of each fold's held-out rows it warned
    findings: list[Finding] = field(default_factory=list)


def stability(validation: Validation, result: str, model: str, references: dict | None = None) -> dict[str, tuple[KindDomain, KindDomain | None, Stability]]:
    from .calibration import calibrate
    out = {}
    table = validation.table
    calibration = calibrate(validation, result, model, "chosen").kinds
    for (r, kind), run in validation.runs.items():
        if r != result or not run.plan.available:
            continue
        own = evaluate_kind(validation, result, kind, model, None, references)
        if own is None:
            continue
        alt = evaluate_kind(validation, result, kind, model, "batch", references) if "batch" in table.groups and kind != "batch" else None
        thresholds = [f.threshold for f in own.folds]
        factors = calibration[kind].factors if kind in calibration else []
        out[kind] = (own, alt, Stability(kind, thresholds, threshold_swing(thresholds), [f.threshold for f in alt.folds] if alt else None,
                                          threshold_swing([f.threshold for f in alt.folds]) if alt else None, threshold_swing([f for f in factors if f]),
                                          {name: [f.rates[name] for f in own.folds] for name in ("distance", "range", "category")},
                                          swing_findings(table.name, f"{table.column_label(result)}, {own.heading}", thresholds)))
    return out
