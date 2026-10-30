"""Fitting every model on every fold and scoring it on the whole groups it never saw.

For each result and hold-out type (from splits.py), and each fold, every model is fitted on the training rows only and asked to predict the held-out rows,
with a 90% range. The predictions are kept, so scores can be worked out afterwards in any way (all rows, or without the flagged ones) without refitting.
A model that cannot be fitted on a fold is recorded with a plain reason and has no result there; it never stops the run. Folds are independent of each
other, so they can run in parallel; the answers do not depend on how many run at once.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .findings import Finding, make
from .models import ORDER, Encoder, Model, ModelSkipped, Prediction, Settings, joint_models, single_models
from .splits import FoldPlan, _assign, _labels, make_fold_plans
from .table import ModellingTable

CALIBRATION_EVERY = 4          # one group in four (the first of each four, by name) is kept apart to calibrate the conformal range
CALIBRATION_LATEST = 0.2       # for later dates, the latest fifth of the training dates is kept apart for the same purpose
INNER_FOLDS = 5                # the regressions choose their penalty on 5 folds of whole groups inside the training rows (or 4 forward blocks for dates)
INNER_BLOCKS = 4
INNER_MIN_CHECK, INNER_MIN_FIT = 5, 10


@dataclass
class FoldRun:
    number: int
    test: np.ndarray                              # positions in the table's frame
    y: np.ndarray
    preds: dict[str, Prediction] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    notes: list[Finding] = field(default_factory=list)   # plain-English reasons a model has no result here
    errors: list[str] = field(default_factory=list)      # the technical detail behind them, for the person debugging


@dataclass
class PlanRun:
    plan: FoldPlan
    folds: list[FoldRun]


@dataclass
class Validation:
    table: ModellingTable
    settings: Settings
    runs: dict[tuple[str, str], PlanRun]          # (result, hold-out type) -> its folds and predictions
    findings: list[Finding]
    seconds: float = 0.0


# ---------------------------------------------------------------- keeping whole groups apart for the conformal range
def calibration_mask(table: ModellingTable, plan: FoldPlan, train: np.ndarray) -> np.ndarray | None:
    """Which training rows are kept apart to calibrate the conformal range: whole groups, or the latest dates. None when too little is left to spare."""
    spec = table.groups[plan.kind]
    if plan.kind == "date":
        times = table.frame.iloc[train][spec.columns[0]].reset_index(drop=True)
        units = sorted(times.unique())
        if len(units) < 2:
            return None
        cut = units[len(units) - max(1, math.ceil(CALIBRATION_LATEST * len(units)))]
        mask = (times >= cut).to_numpy()
    else:
        labels, _ = _labels(table.frame, train, spec.columns)
        names = sorted(labels.unique())
        if len(names) < 2:
            return None
        mask = labels.isin(names[::CALIBRATION_EVERY]).to_numpy()
    return mask if 0 < mask.sum() < len(mask) else None


# ---------------------------------------------------------------- choosing a penalty without touching the held-out fold
def inner_folds(table: ModellingTable, plan: FoldPlan, train: np.ndarray) -> list | None:
    """Folds INSIDE the training rows, of the same kind as the real hold-out (whole groups, or forward in time), as (fit rows, check rows) positions within `train`.
    The real held-out fold is never in them. None when there are too few groups or dates to hold any out."""
    spec = table.groups[plan.kind]
    folds = []
    if plan.kind == "date":
        times = table.frame.iloc[train][spec.columns[0]].reset_index(drop=True)
        units = sorted(times.unique())
        if len(units) < INNER_BLOCKS:
            return None
        for block in np.array_split(np.arange(len(units)), INNER_BLOCKS)[1:]:
            check = np.flatnonzero(((times >= units[block[0]]) & (times <= units[block[-1]])).to_numpy())
            fit = np.flatnonzero((times < units[block[0]]).to_numpy())
            folds.append((fit, check))
    else:
        labels, _ = _labels(table.frame, train, spec.columns)
        sizes = labels.value_counts().to_dict()
        if len(sizes) < 2:
            return None
        placed = _assign(sizes, min(INNER_FOLDS, len(sizes)), False)
        fold_of = np.array([placed[g] for g in labels])
        folds = [(np.flatnonzero(fold_of != f), np.flatnonzero(fold_of == f)) for f in sorted(set(placed.values()))]
    folds = [(fit, check) for fit, check in folds if len(check) >= INNER_MIN_CHECK and len(fit) >= INNER_MIN_FIT]
    return folds or None


# ---------------------------------------------------------------- one fold (a plain function, so it can run in another process)
def _fit_one(model: Model, X_train, y_train, X_test, calibration, notes: list[Finding], errors: list[str], name: str, inner=None) -> tuple[Prediction | None, float]:
    """Fit one model and predict every test row. Returns the prediction (None if the model could not be fitted) and the seconds it took."""
    started = time.time()
    predicted = None
    try:
        model.fit(X_train, y_train, calibration, inner)
        predicted = model.predict(X_test)
        if getattr(model, "by_validation_", True) is False:
            notes.append(make("M43", "", name, model.label))
    except ModelSkipped as reason:
        notes.append(make("M40", "", name, model.label, reason=str(reason)))
    except Exception as error:                          # noqa: BLE001 - one model failing must not stop the others
        notes.append(make("M41", "", name, model.label))
        errors.append(f"{model.label}: {type(error).__name__}: {str(error)[:150]}")
    return predicted, time.time() - started


def _cut(predicted: Prediction, rows: np.ndarray, column: int | None = None) -> Prediction:
    """The part of a prediction that belongs to one result's test rows (and, for a joint model, to one of its result columns)."""
    parts = [a[rows] for a in (predicted.mean, predicted.lo, predicted.hi)]
    return Prediction(*(p if column is None else p[:, column] for p in parts))


def _run_task(task: dict) -> dict:
    """Fit every model of one task on its training rows and predict its test rows. Returns plain data: {result: FoldRun}."""
    from threadpoolctl import threadpool_limits

    frame, settings = task["frame"], task["settings"]
    with threadpool_limits(limits=task["threads"]):
        encoder = Encoder(task["numeric"], task["categorical"]).fit(frame.iloc[task["train"]])
        X_train, X_test = encoder.transform(frame.iloc[task["train"]]), encoder.transform(frame.iloc[task["test_all"]])
        calibration = task["calibration"]
        runs: dict[str, FoldRun] = {}
        for result, test in task["tests"].items():
            runs[result] = FoldRun(task["number"], test, frame[result].to_numpy(dtype=float)[test])
        slot = {int(p): i for i, p in enumerate(task["test_all"])}
        slices = {result: np.array([slot[int(p)] for p in test]) for result, test in task["tests"].items()}
        if task["joint"]:
            y = frame[list(task["tests"])].to_numpy(dtype=float)[task["train"]]
            for model in joint_models(settings, X_train.shape[1]):
                notes, errors = [], []
                predicted, seconds = _fit_one(model, X_train, y, X_test, None, notes, errors, task["name"])
                for column, (result, run) in enumerate(runs.items()):
                    if predicted is not None:
                        run.preds[model.key] = _cut(predicted, slices[result], column)
                    run.seconds[model.key] = seconds / len(runs)
                    run.notes += notes
                    run.errors += errors
        else:
            (result,) = task["tests"]
            y = frame[result].to_numpy(dtype=float)[task["train"]]
            run = runs[result]
            for model in single_models(settings, encoder.n_numeric, X_train.shape[1]):
                predicted, seconds = _fit_one(model, X_train, y, X_test, calibration, run.notes, run.errors, task["name"], task["inner"])
                if predicted is not None:
                    run.preds[model.key] = predicted
                run.seconds[model.key] = seconds
    return runs


# ---------------------------------------------------------------- the whole table
def build_tasks(table: ModellingTable, settings: Settings, usable: list[str], plans: dict, kind_list: list[str], threads) -> tuple[list[dict], list[tuple]]:
    """One task per fold and result, plus one joint task per fold number. Each task holds plain data, so it can run in another process."""
    needed = sorted({c for r in usable for c in table.responses[r].numeric + table.responses[r].categorical} | set(usable))
    frame = table.frame[needed]
    tasks, where = [], []
    for kind in kind_list:
        for r in usable:
            plan = plans[r][kind]
            rt = table.responses[r]
            for fold in plan.folds:
                tasks.append({"frame": frame, "settings": settings, "threads": threads, "joint": False, "name": table.name, "number": fold.number, "numeric": rt.numeric, "categorical": rt.categorical,
                              "train": fold.train, "tests": {r: fold.test}, "test_all": fold.test, "calibration": calibration_mask(table, plan, fold.train),
                              "inner": inner_folds(table, plan, fold.train)})
                where.append((r, kind, fold.number))
        # one joint task per fold number: trained on the rows every result has, tested on each result's own test rows
        if len(usable) >= 2:
            for number in sorted({f.number for r in usable for f in plans[r][kind].folds}):
                folds = {r: next((f for f in plans[r][kind].folds if f.number == number), None) for r in usable}
                have = [r for r in usable if folds[r] is not None]
                if len(have) < 2:
                    continue
                numeric = [c for c in table.responses[have[0]].numeric if all(c in table.responses[r].numeric for r in have)]
                categorical = [c for c in table.responses[have[0]].categorical if all(c in table.responses[r].categorical for r in have)]
                train = np.array(sorted(set.intersection(*(set(folds[r].train.tolist()) for r in have))), dtype=int)
                if not (numeric or categorical) or len(train) < 30:
                    continue
                tests = {r: folds[r].test for r in have}
                tasks.append({"frame": frame, "settings": settings, "threads": threads, "joint": True, "name": table.name, "number": number, "numeric": numeric, "categorical": categorical,
                              "train": train, "tests": tests, "test_all": np.unique(np.concatenate(list(tests.values()))), "calibration": None, "inner": None})
                where.append((tuple(have), kind, number))
    return tasks, where


CACHE_VERSION = "3a-4-2"       # change this (or delete the cache folder) whenever model code changes: a saved answer is only reused when everything it depends on is identical


def task_key(task: dict) -> str:
    """A fingerprint of everything one fold's answer depends on: the data values, the rows, the inputs, the settings and the code version.
    How many folds run at once (and so the forest's thread count) is not part of it, because it does not change the answer."""
    import hashlib
    s = task["settings"]
    digest = hashlib.sha256()
    for part in (CACHE_VERSION, task["name"], task["joint"], task["number"], sorted(task["tests"]), task["numeric"], task["categorical"],
                 (s.mode, s.gp_search_rows, s.gbt_iterations, s.rf_trees, s.mlp_members, s.mlp_iterations)):
        digest.update(repr(part).encode())
    for rows in [task["train"]] + [task["tests"][k] for k in sorted(task["tests"])]:
        digest.update(np.ascontiguousarray(rows).tobytes())
    digest.update(pd.util.hash_pandas_object(task["frame"], index=False).to_numpy().tobytes())
    return digest.hexdigest()[:40]


def run_validation(table: ModellingTable, settings: Settings, kinds=None, results=None, n_jobs: int = 1, progress=None, cache=None, save: bool = True) -> Validation:
    """Every model, every fold, for the chosen results and hold-out types (all of them by default).

    With a `cache` folder, every fold's answer is saved the moment it is done and reused on the next run if nothing it depends on has changed, so an interrupted
    run carries on where it stopped. The answers are the same with or without the cache, and however many folds run at once."""
    import pickle
    from pathlib import Path
    started = time.time()
    usable = [r for r, t in table.responses.items() if t.usable and (results is None or r in results)]
    plans = {r: make_fold_plans(table, r) for r in usable}
    threads = 1 if n_jobs != 1 else None
    if n_jobs != 1:
        settings = Settings(settings.mode, settings.gp_search_rows, settings.gbt_iterations, settings.rf_trees, settings.mlp_members, settings.mlp_iterations, rf_jobs=1)
    kind_list = list(kinds) if kinds else (list(next(iter(plans.values()))) if plans else [])
    tasks, where = build_tasks(table, settings, usable, plans, kind_list, threads)
    answers: list = [None] * len(tasks)
    files = [None] * len(tasks)
    if cache is not None:
        Path(cache).mkdir(parents=True, exist_ok=True)
        for i, task in enumerate(tasks):
            files[i] = Path(cache) / f"{task_key(task)}.pkl"
            if files[i].exists():
                try:
                    answers[i] = pickle.loads(files[i].read_bytes())
                except Exception:                      # noqa: BLE001 - a damaged file is simply computed again
                    files[i].unlink(missing_ok=True)
    todo = [i for i, a in enumerate(answers) if a is None]
    done = len(tasks) - len(todo)
    if progress and done:
        progress(done, len(tasks))

    def keep(i: int, answer: dict) -> None:
        answers[i] = answer
        if files[i] is not None and save:                  # save=False reads saved answers but never writes (used by checks, which must leave the project untouched)
            temporary = files[i].with_suffix(".tmp")
            temporary.write_bytes(pickle.dumps(answer))
            temporary.replace(files[i])                # a file only ever exists whole
        if progress:
            progress(sum(a is not None for a in answers), len(tasks))

    if n_jobs == 1:
        for i in todo:
            keep(i, _run_task(tasks[i]))
    elif todo:
        from joblib import Parallel, delayed
        for i, answer in zip(todo, Parallel(n_jobs=n_jobs, return_as="generator")(delayed(_run_task)(tasks[i]) for i in todo)):
            keep(i, answer)
    runs: dict[tuple[str, str], PlanRun] = {(r, k): PlanRun(plans[r][k], []) for r in usable for k in kind_list}
    folds: dict[tuple[str, str, int], FoldRun] = {}
    for (who, kind, number), answer in zip(where, answers):
        for result, run in answer.items():
            if (result, kind, number) in folds:                 # the joint answers join the single-result run of the same fold
                folds[(result, kind, number)].preds.update(run.preds)
                folds[(result, kind, number)].seconds.update(run.seconds)
                folds[(result, kind, number)].notes += [n for n in run.notes if n.text not in {m.text for m in folds[(result, kind, number)].notes}]
                folds[(result, kind, number)].errors += run.errors
            else:
                folds[(result, kind, number)] = run
    for (result, kind, number), run in sorted(folds.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        runs[(result, kind)].folds.append(run)
    findings = [f for r in usable for k in kind_list for f in plans[r][k].findings if f.level != "note"]
    findings += [n for run in runs.values() for f in run.folds for n in f.notes]
    validation = Validation(table, settings, runs, findings, time.time() - started)
    validation.findings += leakage_alarms(validation)
    return validation


def leakage_alarms(validation: Validation) -> list[Finding]:
    """A held-out R-squared above LEAKAGE_R2 is too good to believe: it is flagged, not celebrated."""
    from .selection import LEAKAGE_R2
    from .models import MODELS_BY_KEY
    found = []
    for (result, kind), run in validation.runs.items():
        for key, s in score(run).items():
            if np.isfinite(s.r2) and s.r2 > LEAKAGE_R2:
                found.append(make("M42", "", validation.table.name, f"{validation.table.column_label(result)}, {MODELS_BY_KEY[key].label}",
                                  r2=f"{s.r2:.4f}", limit=f"{LEAKAGE_R2:g}", hold_out=run.plan.heading))
    return found


# ---------------------------------------------------------------- scoring
@dataclass
class Score:
    model: str
    n: int                         # held-out rows scored
    rmse: float
    mae: float
    r2: float
    worst_fold_rmse: float
    coverage: float                # how often the 90% range contained the truth (NaN: the model gives no range)
    width: float                   # the mean width of the 90% range
    seconds: float
    folds: int                     # folds the model has a result on
    of_folds: int


def score(run: PlanRun, keep: np.ndarray | None = None) -> dict[str, Score]:
    """Score every model on its held-out rows. `keep` (a True/False per row of the table) limits the rows scored, for example without the flagged rows."""
    scores = {}
    for key in ORDER:
        have = [f for f in run.folds if key in f.preds]
        if not have:
            continue
        rows = [(f.y[m], f.preds[key].mean[m], f.preds[key].lo[m], f.preds[key].hi[m], f.seconds.get(key, 0.0))
                for f in have for m in [np.ones(len(f.y), bool) if keep is None else keep[f.test]] if m.any()]
        if not rows:
            continue
        y, mean, lo, hi = (np.concatenate([r[i] for r in rows]) for i in range(4))
        sse = float(((y - mean) ** 2).sum())
        sst = float(((y - y.mean()) ** 2).sum())
        finite = np.isfinite(lo) & np.isfinite(hi)
        per_fold = [float(np.sqrt(np.mean((r[0] - r[1]) ** 2))) for r in rows]
        scores[key] = Score(key, len(y), math.sqrt(sse / len(y)), float(np.abs(y - mean).mean()), 1 - sse / sst if sst > 0 else float("nan"), max(per_fold),
                            float(((y >= lo) & (y <= hi))[finite].mean()) if finite.any() else float("nan"),
                            float((hi - lo)[finite].mean()) if finite.any() else float("nan"), sum(r[4] for r in rows), len(have), len(run.folds))
    return scores


def spread(table: ModellingTable, result: str) -> float:
    """The result's standard deviation over the rows it is modelled on: errors are reported as a share of it so results in different units compare."""
    return float(table.frame[result].iloc[table.responses[result].rows].std())


def build_with_flags_removed(table: ModellingTable) -> ModellingTable | None:
    """The same table with the flagged rows left out of every result's rows (training and testing), for the 'with and without' comparison. None if nothing is flagged."""
    if not table.flag_columns:
        return None
    import copy
    flagged = table.frame[table.flag_columns].any(axis=1).to_numpy()
    other = copy.copy(table)
    other.name = f"{table.name} without the flagged rows"
    other.responses = {r: type(t)(**{**t.__dict__, "rows": t.rows[~flagged[t.rows]]}) for r, t in table.responses.items()}
    return other
