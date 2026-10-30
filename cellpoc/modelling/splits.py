"""The grouped splitters: how a table is divided into training and test rows. This is the only place in the program where rows are divided.

A model is always tested on whole groups it has never seen, never on random rows (random rows would leak: replicates and batch effects would sit on both sides):
- whole batches (or whole APIs) held out together, in 5 folds;
- whole suppliers held out, one at a time when there are 10 or fewer;
- later dates held out: forward steps, every test date strictly later than every training date, a date (a month, for month-only data) never split.
Nothing is random: the same table always gives the same folds, in whatever order its rows are stored. A hold-out that cannot be run (too few groups,
no column for it) is skipped with a message and never replaced by random rows. Every plan is checked by `plan_problems` before it is handed out.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .findings import FOLDS, FIRST_TRAIN_SHARE, LEAVE_ONE_OUT_MAX, MIN_ROWS, MIN_TEST, MIN_TIMES, STEPS, Finding, make
from .table import KIND_WORDS, ModellingTable

KINDS = ("batch", "supplier", "date")                 # always planned (and skipped with a message when the setup gives no column); "api" is added when declared


class SplitError(Exception):
    """A split that would leak. Raised before any model could be fitted on it."""


@dataclass(frozen=True)
class Fold:
    number: int
    train: np.ndarray                 # positions in the table's frame
    test: np.ndarray
    held_out: tuple[str, ...]         # the groups held out, or the first and last date of the block


@dataclass
class FoldPlan:
    table: str
    response: str
    kind: str
    heading: str                      # how this hold-out is named everywhere; a stand-in for the supplier carries PROXY_PHRASE (see findings.py)
    method: str = ""
    folds: list[Fold] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    n_rows: int = 0                   # rows the result is modelled on
    n_dropped: int = 0                # folds dropped for being too small
    n_unplaced: int = 0               # rows left out of this hold-out for having no group value

    @property
    def available(self) -> bool:
        return bool(self.folds)


# ---------------------------------------------------------------- the groups
def _labels(frame: pd.DataFrame, rows: np.ndarray, columns: tuple[str, ...]) -> tuple[pd.Series, np.ndarray]:
    """(a text label for each row, in the order of `rows`; the positions in `rows` that have no group value)."""
    part = frame.iloc[rows][list(columns)]
    missing = part.isna().any(axis=1).to_numpy()

    def text(column: pd.Series) -> pd.Series:
        """A code stored as 113.0 is written 113."""
        if pd.api.types.is_float_dtype(column) and column.dropna().map(float.is_integer).all():
            return column.map(lambda v: "" if pd.isna(v) else str(int(v)))
        return column.astype(str)

    labels = part.apply(text).agg(" | ".join, axis=1) if len(columns) > 1 else text(part[columns[0]])
    return labels.reset_index(drop=True), missing


def _assign(sizes: dict[str, int], k: int, one_each: bool) -> dict[str, int]:
    """Deal whole groups into k folds, biggest first, each into the fold with the fewest rows so far. Ties break by name, so nothing is random."""
    order = sorted(sizes, key=lambda g: (-sizes[g], g))
    if one_each:
        return {g: i for i, g in enumerate(sorted(sizes))}
    load = [0] * k
    placed: dict[str, int] = {}
    for g in order:
        fold = min(range(k), key=lambda i: (load[i], i))
        placed[g] = fold
        load[fold] += sizes[g]
    return placed


def _group_plan(table: ModellingTable, plan: FoldPlan, rows: np.ndarray, basis: np.ndarray) -> None:
    """Whole groups are dealt into folds using the rows of every modelled result (`basis`), so every result gets the same folds; each result then keeps its own rows."""
    spec = table.groups[plan.kind]
    labels, missing = _labels(table.frame, rows, spec.columns)
    plan.n_unplaced = int(missing.sum())
    if plan.n_unplaced:
        plan.findings.append(make("M31", "", plan.table, plan.heading, n=plan.n_unplaced))
    keep = ~missing
    rows, labels = rows[keep], labels[keep].reset_index(drop=True)
    basis_labels, basis_missing = _labels(table.frame, basis, spec.columns)
    sizes = basis_labels[~basis_missing].value_counts().to_dict()
    if len(sizes) < 2 or labels.nunique() < 2:
        plan.findings.append(make("M30", "few_groups", plan.table, plan.heading, n=min(len(sizes), labels.nunique())))
        return
    one_each = plan.kind == "supplier" and len(sizes) <= LEAVE_ONE_OUT_MAX
    k = len(sizes) if one_each else min(FOLDS, len(sizes))
    placed = _assign(sizes, k, one_each)
    fold_of = np.array([placed[g] for g in labels])
    # "groups", not "batches" or "suppliers": the heading above names what the groups are, including a stand-in that is not a confirmed supplier
    plan.method = (f"each of the {len(sizes)} groups is held out in turn: the model is trained on the others and tested on the one held out" if one_each else
                   f"the {len(sizes)} groups are divided into {k} folds of whole groups (nothing is random: the biggest are dealt out first); "
                   f"each fold is held out in turn and the model is trained on the rest")
    for f in range(k):
        test, train = rows[fold_of == f], rows[fold_of != f]
        held = tuple(sorted(g for g in set(labels) if placed[g] == f))
        if len(test) < MIN_TEST or len(train) < MIN_ROWS:
            plan.n_dropped += 1
            plan.findings.append(make("M32", "", plan.table, plan.heading, number=f + 1, test=len(test), train=len(train), min_test=MIN_TEST, min_train=MIN_ROWS))
            continue
        plan.folds.append(Fold(f + 1, train, test, held))
    plan.n_rows = len(rows)


def _date_plan(table: ModellingTable, plan: FoldPlan, rows: np.ndarray, basis: np.ndarray) -> None:
    column = table.groups["date"].columns[0]
    times = table.frame.iloc[rows][column]
    missing = times.isna().to_numpy()
    plan.n_unplaced = int(missing.sum())
    if plan.n_unplaced:
        plan.findings.append(make("M31", "", plan.table, plan.heading, n=plan.n_unplaced))
    rows, times = rows[~missing], times[~missing].reset_index(drop=True)
    units = sorted(pd.to_datetime(table.frame.iloc[basis][column].dropna().unique()))      # the dates of every modelled result, so every result steps through the same dates
    if len(units) < MIN_TIMES:
        plan.findings.append(make("M30", "few_times", plan.table, plan.heading, n=len(units), minimum=MIN_TIMES))
        return
    first = math.ceil(FIRST_TRAIN_SHARE * len(units))
    later = np.empty(len(units) - first, dtype=object)         # the dates that are tested, in order, cut into consecutive blocks
    later[:] = units[first:]
    blocks = [b for b in np.array_split(later, min(STEPS, len(later))) if len(b)]
    plan.method = (f"{len(blocks)} forward steps over {len(units)} distinct dates: the earliest {first} dates are always training; each step trains on everything "
                   f"earlier than its block and tests on the next block of dates, so every test date is later than every training date and a date is never split")
    if "date_precision" in table.frame.columns and (table.frame.iloc[rows]["date_precision"] == "month").all():
        plan.findings.append(make("M35", "", plan.table, plan.heading))
    for number, block in enumerate(blocks, 1):
        test = rows[((times >= block[0]) & (times <= block[-1])).to_numpy()]
        train = rows[(times < block[0]).to_numpy()]
        if len(test) < MIN_TEST or len(train) < MIN_ROWS:
            plan.n_dropped += 1
            plan.findings.append(make("M32", "", plan.table, plan.heading, number=number, test=len(test), train=len(train), min_test=MIN_TEST, min_train=MIN_ROWS))
            continue
        plan.folds.append(Fold(number, train, test, (str(pd.Timestamp(block[0]).date()), str(pd.Timestamp(block[-1]).date()))))
    plan.n_rows = len(rows)


# ---------------------------------------------------------------- the guards
def plan_problems(plan: FoldPlan, table: ModellingTable) -> list[str]:
    """Everything wrong with a plan, found by a route independent of the one that built it (empty means safe)."""
    found: list[str] = []
    frame = table.frame
    allowed = set(table.responses[plan.response].rows.tolist()) if plan.response in table.responses else set()
    spec = table.groups.get(plan.kind)
    seen_test: set[int] = set()
    for fold in plan.folds:
        train, test = set(fold.train.tolist()), set(fold.test.tolist())
        name = f"fold {fold.number}"
        if not train or not test:
            found.append(f"{name} has no training rows or no test rows")
        if train & test:
            found.append(f"{name}: {len(train & test)} rows are in both training and test")
        if not (train | test) <= allowed:
            found.append(f"{name} uses rows the result is not modelled on")
        if test & seen_test:
            found.append(f"{name}: {len(test & seen_test)} test rows were already tested in an earlier fold")
        seen_test |= test
        if spec is None:
            found.append(f"{name}: the setup has no column for this hold-out")
            continue
        if plan.kind == "date":
            times = frame[spec.columns[0]]
            if not times.iloc[sorted(train)].max() < times.iloc[sorted(test)].min():
                found.append(f"{name}: a test date is not later than every training date")
        else:
            groups = frame[list(spec.columns)].apply(lambda column: column.map(str)).agg(" | ".join, axis=1)      # a missing value becomes the text "nan"
            shared = set(groups.iloc[sorted(train)]) & set(groups.iloc[sorted(test)])
            if shared:
                found.append(f"{name}: {len(shared)} group(s) appear in both training and test ({', '.join(sorted(shared)[:3])})")
    return found


# ---------------------------------------------------------------- planning
def make_fold_plan(table: ModellingTable, response: str, kind: str) -> FoldPlan:
    """The folds for one result and one hold-out type. Raises SplitError if the plan would leak (it never should)."""
    spec = table.groups.get(kind)
    heading = spec.heading if spec else f"{KIND_WORDS[kind]} (no column given)"
    plan = FoldPlan(table.name, response, kind, heading)
    rows = table.responses[response].rows
    plan.n_rows = len(rows)
    if spec is None:
        plan.findings.append(make("M30", "none", table.name, heading))
        return plan
    usable = [t.rows for t in table.responses.values() if t.usable] or [rows]
    basis = np.unique(np.concatenate(usable))
    (_date_plan if kind == "date" else _group_plan)(table, plan, rows, basis)
    if plan.method:
        plan.findings.append(make("M34" if kind == "date" else "M33", "", table.name, heading, method=plan.method))
    if plan.method and not plan.folds:
        plan.findings.append(make("M30", "no_fold", table.name, heading, test=MIN_TEST, train=MIN_ROWS))
    problems = plan_problems(plan, table)
    if problems:
        raise SplitError(f"{plan.heading}: " + "; ".join(problems))
    return plan


def make_fold_plans(table: ModellingTable, response: str) -> dict[str, FoldPlan]:
    """Every hold-out type for one result: batches, suppliers, dates, and APIs when the setup names a column for them."""
    kinds = KINDS + (("api",) if "api" in table.groups else ())
    return {kind: make_fold_plan(table, response, kind) for kind in kinds}
