"""The group-level warning: is this whole batch of recipes from an unfamiliar batch, supplier or time period?

A per-recipe distance barely moves when a few inputs shift, but a whole group of recipes carries far more evidence: if every recipe of a group is a little off in the same few inputs, the group's
AVERAGE is clearly off. This warning looks only at the inputs, never at a result or a model, and answers for a group of recipes that arrive together (a batch, a supplier, or a block of dates).
The method was fixed before any result existed (docs/decisions.md):
- STATISTIC: in the space the models work in (numeric inputs standardised on the training rows, categories as 0/1 columns), T = n x |group mean - training mean|^2 / p, where n is the number of
  recipes in the group and p the number of encoded inputs. With no shift T is about 1; a shift in a few inputs raises it in proportion to n.
- THRESHOLD: the 95th percentile of the same T for groups known to be ordinary. For each training group of the same kind with at least n rows, draw DRAWS_PER_GROUP random subsets of n of its rows and
  measure T against the training rows OUTSIDE that group, so the ordinary differences between groups (batch effects) are inside the threshold. This needs at least MIN_NULL_GROUPS such groups.
  With fewer, the threshold comes from CHANCE_DRAWS random subsets of n training rows, which knows nothing about how much groups normally differ: it is labelled "compared with chance alone".
- EXPLANATION: the inputs that moved most (the shift in standard errors, with its sign).
Groups of fewer than MIN_GROUP_ROWS recipes are not assessed. Everything is set from the training rows alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .domain import QUANTILE, STABLE_RATIO, VARYING_RATIO, threshold_swing
from .findings import Finding, make
from .models import Encoder
from .splits import _labels
from .validate import Validation

MIN_GROUP_ROWS = 5
MIN_NULL_GROUPS = 10
DRAWS_PER_GROUP = 10
CHANCE_DRAWS = 500
SEED = 20261012
REFERENCE_SIZE = 30          # the group size at which thresholds are compared across folds
NOUN = {"batch": "batches of recipes", "supplier": "suppliers", "date": "time periods", "api": "APIs"}      # the plural, for "x% of ..."


@dataclass
class GroupReference:
    encoded: np.ndarray
    labels: np.ndarray
    names: list[str]
    mean: np.ndarray = field(init=False)
    total: np.ndarray = field(init=False)
    index: dict = field(init=False)
    cache: dict = field(default_factory=dict)

    def __post_init__(self):
        self.mean = self.encoded.mean(axis=0)
        self.total = self.encoded.sum(axis=0)
        order = np.argsort(self.labels, kind="stable")
        sorted_labels = self.labels[order]
        cuts = np.flatnonzero(sorted_labels[1:] != sorted_labels[:-1]) + 1
        self.index = {str(sorted_labels[s]): order[s:e] for s, e in zip(np.r_[0, cuts], np.r_[cuts, len(order)])}


@dataclass
class GroupWarning:
    n: int
    statistic: float
    threshold: float
    flagged: bool
    null_kind: str                      # "group-based" (ordinary differences between groups are inside the threshold) or "chance alone"
    n_null_groups: int
    top_inputs: list[tuple[str, float]]  # (input, shift in standard errors with its sign), the three that moved most


def fit_group_reference(encoded: np.ndarray, labels: np.ndarray, names: list[str]) -> GroupReference:
    return GroupReference(encoded, np.asarray(labels).astype(str), names)


def statistic(rows: np.ndarray, reference_mean: np.ndarray) -> float:
    difference = rows.mean(axis=0) - reference_mean
    return float(len(rows) * (difference @ difference) / len(reference_mean))


def null_threshold(ref: GroupReference, n: int) -> tuple[float, str, int]:
    """(the 95th percentile of T for ordinary groups of n rows, how it was made, how many training groups it used)."""
    if n in ref.cache:
        return ref.cache[n]
    rng = np.random.default_rng(SEED + n)
    big = [g for g, idx in ref.index.items() if len(idx) >= n]
    total_rows = len(ref.encoded)
    values = []
    if len(big) >= MIN_NULL_GROUPS:
        for g in big:
            idx = ref.index[g]
            outside = (ref.total - ref.encoded[idx].sum(axis=0)) / (total_rows - len(idx))
            for _ in range(DRAWS_PER_GROUP):
                values.append(statistic(ref.encoded[rng.choice(idx, size=n, replace=False)], outside))
        out = (float(np.quantile(values, QUANTILE)), "group-based", len(big))
    else:
        for _ in range(CHANCE_DRAWS):
            pick = rng.choice(total_rows, size=n, replace=False)
            outside = (ref.total - ref.encoded[pick].sum(axis=0)) / (total_rows - n)
            values.append(statistic(ref.encoded[pick], outside))
        out = (float(np.quantile(values, QUANTILE)), "chance alone", len(big))
    ref.cache[n] = out
    return out


def check_group(ref: GroupReference, rows: np.ndarray) -> GroupWarning | None:
    """Is this group of recipes (already encoded the same way as the training rows) unfamiliar? None if it has fewer than MIN_GROUP_ROWS recipes."""
    if len(rows) < MIN_GROUP_ROWS:
        return None
    t = statistic(rows, ref.mean)
    threshold, kind, used = null_threshold(ref, len(rows))
    shift = (rows.mean(axis=0) - ref.mean) * np.sqrt(len(rows))
    top = [(ref.names[i], float(shift[i])) for i in np.argsort(-np.abs(shift))[:3]]
    return GroupWarning(len(rows), t, threshold, t > threshold, kind, used, top)


# ---------------------------------------------------------------- the warning on the saved Stage 3a folds
@dataclass
class GroupResult:
    label: str
    warning: GroupWarning
    mae: float | None                  # the chosen model's mean absolute error on this group's recipes


@dataclass
class KindGroups:
    kind: str
    heading: str
    groups: list[GroupResult]
    n_small: int
    reference_thresholds: list[tuple[float, str]]       # per fold: the threshold for a group of REFERENCE_SIZE recipes, and how it was made
    findings: list[Finding] = field(default_factory=list)

    @property
    def flagged_share(self) -> float | None:
        return float(np.mean([g.warning.flagged for g in self.groups])) if self.groups else None

    @property
    def error_ratio(self) -> float | None:
        """Mean error of flagged groups over that of unflagged ones (None with fewer than 3 of either)."""
        a = [g.mae for g in self.groups if g.warning.flagged and g.mae is not None]
        b = [g.mae for g in self.groups if not g.warning.flagged and g.mae is not None]
        return float(np.mean(a) / np.mean(b)) if len(a) >= 3 and len(b) >= 3 and np.mean(b) > 0 else None

    @property
    def rank_correlation(self) -> float | None:
        """Rank correlation, across groups, of how unfamiliar a group is (T over its threshold) with the error on it (needs 10 groups)."""
        pairs = [(g.warning.statistic / g.warning.threshold, g.mae) for g in self.groups if g.mae is not None]
        if len(pairs) < 10:
            return None
        order = lambda a: np.argsort(np.argsort(a))
        return float(np.corrcoef(order([p[0] for p in pairs]), order([p[1] for p in pairs]))[0, 1])

    @property
    def null_kinds(self) -> set[str]:
        return {g.warning.null_kind for g in self.groups}

    def top_shifted(self, limit: int = 3) -> list[tuple[str, int]]:
        """The inputs that most often appear among the three that moved most in flagged groups."""
        counts: dict[str, int] = {}
        for g in self.groups:
            if g.warning.flagged:
                for name, _ in g.warning.top_inputs:
                    counts[name] = counts.get(name, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]


def group_findings(table_name: str, place: str, groups: list[GroupResult], n_small: int) -> list[Finding]:
    found = []
    chance = [g for g in groups if g.warning.null_kind == "chance alone"]
    if chance:
        found.append(make("M62", "", table_name, place, n=min(g.warning.n_null_groups for g in chance), minimum=MIN_NULL_GROUPS))
    if n_small:
        found.append(make("M63", "", table_name, place, n=n_small, minimum=MIN_GROUP_ROWS))
    return found


def _train_labels(table, kind: str, train: np.ndarray, test: np.ndarray) -> np.ndarray:
    """The group of every training row: its batch or supplier, or for a time hold-out its consecutive block of dates, as many dates long as the held-out block."""
    spec = table.groups[kind]
    if kind != "date":
        return _labels(table.frame, train, spec.columns)[0].to_numpy()
    dates = pd.to_datetime(table.frame.iloc[train][spec.columns[0]]).reset_index(drop=True)
    width = max(1, pd.to_datetime(table.frame.iloc[test][spec.columns[0]]).nunique())
    rank = {d: i for i, d in enumerate(sorted(dates.unique()))}
    return np.array([f"block{rank[d] // width}" for d in dates])


def evaluate_groups(validation: Validation, result: str, kind: str, model: str) -> KindGroups | None:
    table = validation.table
    run = validation.runs.get((result, kind))
    if run is None or not run.plan.available:
        return None
    rt = table.responses[result]
    spec = table.groups[kind]
    trains = {fold.number: fold.train for fold in run.plan.folds}
    results, small, thresholds = [], 0, []
    for f in run.folds:
        train = trains[f.number]
        part = table.frame.iloc[train]
        encoder = Encoder(rt.numeric, rt.categorical).fit(part)
        ref = fit_group_reference(encoder.transform(part), _train_labels(table, kind, train, f.test), encoder.names())
        thresholds.append(null_threshold(ref, REFERENCE_SIZE)[:2])
        held = encoder.transform(table.frame.iloc[f.test])
        names = np.array(["the whole block of dates"] * len(f.test)) if kind == "date" else _labels(table.frame, f.test, spec.columns)[0].to_numpy()
        error = np.abs(f.y - f.preds[model].mean) if model in f.preds else None
        for label in sorted(set(names)):
            pick = np.flatnonzero(names == label)
            warning = check_group(ref, held[pick])
            if warning is None:
                small += 1
            else:
                results.append(GroupResult(f"{label} (fold {f.number})" if kind == "date" else label, warning, float(error[pick].mean()) if error is not None else None))
    out = KindGroups(kind, run.plan.heading, results, small, thresholds)
    out.findings = group_findings(table.name, f"{table.column_label(result)}, {run.plan.heading}", results, small)
    return out