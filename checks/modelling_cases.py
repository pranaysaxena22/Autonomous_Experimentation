"""One test for every message the modelling part can show: a tiny table made to cause exactly that finding.

Each case builds a small made-up table (60 rows) and a setup for it, builds the modelling table, and checks that the expected message appears at the
expected level, in plain English. docs/modelling_messages.md is generated from these cases, and the health check fails if any message has no case.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from cellpoc.ingest import CleanResult, ColumnReport
from cellpoc.modelling import CATALOGUE, Finding, ModellingTable, build_table, make_fold_plan

# Words that belong to programmers; quoted text is the person's own and is not judged.
TECHNICAL = re.compile(r"\b(schema|null|nonetype|traceback|exception|keyerror|typeerror|valueerror|dataframe|pandas|numpy|sklearn|stack trace|undefined|nan)\b|<class|\{|\}",
                       re.IGNORECASE)


def wording_problems(finding: Finding) -> list[str]:
    plain = re.sub(r"'[^']*'", "''", finding.message)
    found = []
    if TECHNICAL.search(plain):
        found.append("contains technical wording: " + finding.message)
    if not finding.text.strip() or not finding.message.startswith(finding.table):
        found.append("is empty or does not start with the table name")
    return found


# ---------------------------------------------------------------- a tiny valid table and setup
def tiny_frame(n: int = 60, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    drug, binder = rng.uniform(10, 30, n), rng.uniform(2, 6, n)
    return pd.DataFrame({
        "drug_pct": drug, "binder_pct": binder, "filler_pct": 100 - drug - binder, "force": rng.uniform(5, 20, n),
        "supplier": np.array(["A", "B", "C"])[np.arange(n) % 3], "batch_id": [f"B{i // 6}" for i in range(n)],
        "y": 2 * drug + binder + rng.normal(0, 1, n),
    })


def tiny_setup(**validation) -> dict:
    block = {"responses": ["y"], "groups": {"batch": {"column": "batch_id"}, "supplier": {"column": "supplier", "confirmed": True}}}
    block.update(validation)
    return {"ingredients": [{"id": "drug_pct", "role": "active"}, {"id": "binder_pct", "role": "binder"}, {"id": "filler_pct", "role": "balance"}],
            "process_factors": [{"id": "force"}], "context_factors": [{"id": "supplier"}], "data": {"validation": block}}


def build(setup: dict | None = None, frame: pd.DataFrame | None = None, columns: list[ColumnReport] | None = None, clean: CleanResult | None = None) -> ModellingTable:
    frame = tiny_frame() if frame is None else frame
    clean = clean if clean is not None else CleanResult(frame, columns or [], [])
    return build_table(setup or tiny_setup(), clean, None, "t")


@dataclass
class Case:
    rule: str
    variant: str
    what: str
    run: Callable[[], ModellingTable]


CASES: list[Case] = []


def case(rule: str, variant: str, what: str):
    def register(function: Callable[[], ModellingTable]):
        CASES.append(Case(rule, variant, what, function))
        return function
    return register


# ------------------------------------------------------------------ the table cannot be modelled
@case("M01", "", "a setup with no validation section")
def _():
    setup = tiny_setup()
    del setup["data"]["validation"]
    return build(setup)


@case("M02", "", "a table that could not be read at all")
def _():
    return build(clean=CleanResult(None, [], []))


@case("M03", "result", "a result to predict that is not in the table")
def _():
    return build(tiny_setup(responses=["no_such_result"]))


@case("M03", "input", "an input that is not in the table")
def _():
    return build(tiny_setup(inputs=["drug_pct", "no_such_input"]))


@case("M03", "group", "a group column that is not in the table")
def _():
    return build(tiny_setup(groups={"batch": {"column": "no_such_batch"}}))


@case("M04", "", "a setup with no inputs listed and no ingredients, process settings or context factors")
def _():
    setup = tiny_setup()
    for section in ("ingredients", "process_factors", "context_factors"):
        del setup[section]
    return build(setup)


# ------------------------------------------------------------------ something was left out or limited
@case("M10", "same", "the result listed among its own inputs")
def _():
    return build(tiny_setup(inputs=["drug_pct", "y"]))


@case("M10", "source", "an input the result is calculated from")
def _():
    return build(tiny_setup(derived_from={"y": ["drug_pct"]}))


@case("M10", "derived", "an input that is calculated from the result")
def _():
    return build(tiny_setup(derived_from={"drug_pct": ["y"]}))


@case("M10", "copy", "an input that is a recalculation of the result (three times the result plus one)")
def _():
    frame = tiny_frame()
    frame["y_again"] = frame["y"] * 3 + 1
    return build(tiny_setup(inputs=["drug_pct", "y_again"]), frame)


@case("M11", "", "ten rows with no value for the result")
def _():
    frame = tiny_frame()
    frame.loc[:9, "y"] = np.nan
    return build(frame=frame)


@case("M12", "", "five rows with no value for an input")
def _():
    frame = tiny_frame()
    frame.loc[:4, "force"] = np.nan
    return build(frame=frame)


@case("M13", "", "only ten rows in the table")
def _():
    return build(frame=tiny_frame(10))


@case("M14", "", "a result with the same value in every row")
def _():
    frame = tiny_frame()
    frame["y"] = 5.0
    return build(frame=frame)


@case("M15", "", "an input with the same value in every row")
def _():
    frame = tiny_frame()
    frame["force"] = 12.0
    return build(frame=frame)


# ------------------------------------------------------------------ facts every report must carry
@case("M20", "", "a balance ingredient (the filler)")
def _():
    return build()


@case("M21", "", "amounts converted to percentages of the tablet weight")
def _():
    setup = tiny_setup()
    setup["data"]["composition"] = {"total_weight": "weight_mg"}
    return build(setup)


@case("M22", "", "rows whose amounts do not add up to the tablet weight")
def _():
    frame = tiny_frame()
    frame["mass_balance_flag"] = [i < 7 for i in range(len(frame))]
    setup = tiny_setup()
    setup["data"]["composition"] = {"total_weight": "weight_mg", "tolerance_pct": 2}
    return build(setup, frame)


@case("M23", "", "a result whose unit is assumed")
def _():
    return build(columns=[ColumnReport("y", "Y", "target", "number", unit="kP", unit_status="assumed", unit_note="a common convention, not exact")])


@case("M24", "", "a supplier column that only stands in for the supplier")
def _():
    return build(tiny_setup(groups={"supplier": {"column": "supplier", "confirmed": False, "note": "the code is not explained in the file"}}))


@case("M26", "", "a comparison marked exploratory")
def _():
    return build(tiny_setup(exploratory="a smaller and non-random sample, not part of the main comparison"))


@case("M25", "", "a column left out on purpose")
def _():
    return build(tiny_setup(left_out=[{"id": "water", "why": "its zeros cannot be confirmed as real"}]))


# ------------------------------------------------------------------ the grouped splitters
def dated_frame(n: int = 120) -> pd.DataFrame:
    """Rows in batches of six, four rows to a date, so forward steps have enough rows."""
    frame = tiny_frame(n)
    frame["date"] = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.arange(n) // 4, unit="D")
    return frame


def plan_for(kind: str, frame: pd.DataFrame | None = None, **groups):
    """The folds for the result y on a tiny table, with the groups the case names."""
    frame = tiny_frame() if frame is None else frame
    groups = groups or {"batch": {"column": "batch_id"}, "supplier": {"column": "supplier", "confirmed": True}, "date": {"column": "date"}}
    table = build(tiny_setup(groups=groups), frame)
    return make_fold_plan(table, "y", kind)


@case("M30", "none", "a supplier hold-out when the setup names no supplier column")
def _():
    return plan_for("supplier", batch={"column": "batch_id"})


@case("M30", "few_groups", "a batch hold-out when every row is in the same batch")
def _():
    frame = tiny_frame()
    frame["batch_id"] = "B0"
    return plan_for("batch", frame, batch={"column": "batch_id"})


@case("M30", "few_times", "forward steps when there are only three distinct dates")
def _():
    frame = tiny_frame()
    frame["date"] = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.arange(60) % 3, unit="D")
    return plan_for("date", frame, date={"column": "date"})


@case("M30", "no_fold", "three batches of twelve rows: every fold would have fewer than 30 training rows")
def _():
    frame = tiny_frame(36)
    frame["batch_id"] = [f"B{i // 12}" for i in range(36)]
    return plan_for("batch", frame, batch={"column": "batch_id"})


@case("M31", "", "rows with no batch")
def _():
    frame = tiny_frame()
    frame.loc[:5, "batch_id"] = np.nan
    return plan_for("batch", frame, batch={"column": "batch_id"})


@case("M32", "", "one batch of only three rows among big ones: its fold is too small")
def _():
    frame = tiny_frame(63)
    frame["batch_id"] = [f"B{i // 15}" for i in range(60)] + ["Z"] * 3
    return plan_for("batch", frame, batch={"column": "batch_id"})


@case("M33", "", "a batch hold-out on a table of ten batches")
def _():
    return plan_for("batch", batch={"column": "batch_id"})


@case("M34", "", "forward steps over thirty dates")
def _():
    return plan_for("date", dated_frame(), date={"column": "date"})


@case("M35", "", "forward steps when every date is a month")
def _():
    frame = dated_frame()
    frame["date_precision"] = "month"
    return plan_for("date", frame, date={"column": "date"})


# ------------------------------------------------------------------ the models
def run_tiny(frame: pd.DataFrame | None = None, settings=None, inputs: list[str] | None = None):
    """Every model on every batch fold of a tiny table (fast settings)."""
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.validate import run_validation
    extra = {"inputs": inputs} if inputs else {}
    table = build(tiny_setup(groups={"batch": {"column": "batch_id"}}, **extra), tiny_frame(120) if frame is None else frame)
    return run_validation(table, settings or FAST, kinds=["batch"], n_jobs=1)


@case("M40", "", "the exact Gaussian process on a table with more training rows than its limit (the limit is lowered to 5 rows for the test)")
def _():
    from cellpoc.modelling import models
    kept = models.MAX_EXACT_GP_ROWS
    models.MAX_EXACT_GP_ROWS = 5
    try:
        return run_tiny()
    finally:
        models.MAX_EXACT_GP_ROWS = kept


@case("M41", "", "a model that cannot be fitted (a neural-network ensemble with no members)")
def _():
    from cellpoc.modelling.models import Settings
    return run_tiny(settings=Settings("test", 50, 20, 20, 0, 20))


@case("M42", "", "a result that an input predicts almost perfectly, but not closely enough to be called a copy")
def _():
    rng = np.random.default_rng(4)
    frame = tiny_frame(120)
    frame["x1"] = rng.uniform(0, 1, 120)
    frame["y"] = 5 * frame["x1"] + rng.normal(0, 0.1, 120)
    return run_tiny(frame, inputs=["x1"])


@case("M43", "", "a table of only two batches: once one is held out a single batch is left, so the ridge penalty cannot be chosen on whole groups inside the training rows")
def _():
    frame = tiny_frame(60)
    frame["batch_id"] = ["B0"] * 30 + ["B1"] * 30
    return run_tiny(frame)


# ------------------------------------------------------------------ calibration and the carry-forward rule
def fake_validation(errors: dict, n_rows: int = 600, setup: dict | None = None, folds: int = 4):
    """Made-up held-out results where each model's error is exactly the given multiple of the result's spread, in `folds` equal folds per hold-out type."""
    from cellpoc.modelling import Fold, FoldPlan
    from cellpoc.modelling.models import FAST, Prediction
    from cellpoc.modelling.selection import spread
    from cellpoc.modelling.validate import FoldRun, PlanRun, Validation

    frame = tiny_frame(n_rows)
    frame["date"] = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.arange(n_rows) // 6, unit="D")
    table = build(setup or tiny_setup(groups={"batch": {"column": "batch_id"}, "date": {"column": "date"}}), frame)
    rows = table.responses["y"].rows
    y, sd = table.frame["y"].to_numpy(), spread(table, "y")
    runs = {}
    for kind, by_model in errors.items():
        plan = FoldPlan("t", "y", kind, f"({kind})")
        run = PlanRun(plan, [])
        for number, chunk in enumerate(np.array_split(rows, folds), 1):
            sign = np.where(np.arange(len(chunk)) % 2 == 0, 1.0, -1.0)
            preds = {m: Prediction(y[chunk] + e * sd * sign, y[chunk] + e * sd * sign - sd, y[chunk] + e * sd * sign + sd) for m, e in by_model.items()}
            plan.folds.append(Fold(number, np.setdiff1d(rows, chunk), chunk, (str(number),)))
            run.folds.append(FoldRun(number, chunk, y[chunk], preds, {m: 0.0 for m in preds}))
        runs[("y", kind)] = run
    return Validation(table, FAST, runs, [], 0.0)


_BASE = {"mean": 1.0, "nearest": 1.2}


@case("M50", "tag", "an exploratory table")
def _():
    from cellpoc.modelling.carry import decide
    return decide(fake_validation({"batch": {**_BASE, "quadratic": 0.4}}, setup=tiny_setup(groups={"batch": {"column": "batch_id"}}, exploratory="a smaller sample")), "y")


@case("M50", "no_model", "a result no model predicts better than the baselines")
def _():
    from cellpoc.modelling.carry import decide
    return decide(fake_validation({"batch": {**_BASE, "quadratic": 1.1, "forest": 1.2}}), "y")


@case("M50", "weak", "a result whose best model has an error of 0.9 of the spread")
def _():
    from cellpoc.modelling.carry import decide
    return decide(fake_validation({"batch": {**_BASE, "quadratic": 0.9, "forest": 0.95}}), "y")


@case("M50", "small", "a table with only 60 held-out rows")
def _():
    from cellpoc.modelling.carry import decide
    return decide(fake_validation({"batch": {**_BASE, "quadratic": 0.4}}, n_rows=60), "y")


@case("M51", "", "a result whose best model has an error of 0.75 of the spread (between the carry and skip lines)")
def _():
    from cellpoc.modelling.carry import decide
    return decide(fake_validation({"batch": {**_BASE, "quadratic": 0.75, "forest": 0.9}}), "y")


@case("M52", "", "forward-in-time folds: the first step has no earlier step to learn a scale factor from")
def _():
    from cellpoc.modelling.calibration import calibrate
    return calibrate(fake_validation({"date": {**_BASE, "quadratic": 0.5}}), "y", "quadratic", "chosen")


@case("M62", "", "a group compared with chance alone because there are too few training groups")
def _():
    from cellpoc.modelling.group_domain import GroupResult, GroupWarning, group_findings
    warning = GroupWarning(30, 3.0, 1.5, True, "chance alone", 4, [("x1", 2.0)])
    return _Found(group_findings("t", "y, whole suppliers (binder_supplier)", [GroupResult("A", warning, None)], 0))


@case("M63", "", "three held-out groups with fewer than 5 recipes")
def _():
    from cellpoc.modelling.group_domain import group_findings
    return _Found(group_findings("t", "y, whole batches (batch_id)", [], 3))


class _Found:
    """A few findings from a function that returns them directly, so a message case can be run the same way as the others."""

    def __init__(self, findings):
        self.findings = findings


@case("M60", "", "a distance threshold that could not be set on one of three folds")
def _():
    from cellpoc.modelling.domain import swing_findings
    return _Found(swing_findings("t", "y, whole batches (batch_id)", [2.0, None, 2.1]))


@case("M61", "", "a distance threshold whose largest value is twice its smallest across the folds")
def _():
    from cellpoc.modelling.domain import swing_findings
    return _Found(swing_findings("t", "y, whole suppliers (binder_supplier)", [2.0, 4.0, 3.0]))


def _made_up_replay(base: float, warned_picks_n: int):
    """Four made-up decision windows of 500 recipes where a perfect predictor is used, so only the pass rate and the number of warned picks differ."""
    from cellpoc.modelling.replay import STATUSES, Window, summarise, warned_picks

    rng = np.random.default_rng(5)
    windows = []
    for i in range(4):
        passed = rng.random(500) < base
        flag = np.zeros(500, bool)
        flag[np.flatnonzero(passed)[:warned_picks_n]] = True
        windows.append(Window(i + 1, "2025-01-01", "2025-01-10", passed.astype(float), passed, np.array([f"B{j // 50}" for j in range(500)]), {s: flag for s in STATUSES}))
    summary, masks = summarise(windows)
    return summary, {s: warned_picks(windows, masks, s) for s in STATUSES}


@case("M70", "", "a target met by 99% of recipes anyway, so ranking cannot improve on random picking")
def _():
    from cellpoc.modelling.replay import target_findings
    summary, warned = _made_up_replay(0.99, 0)
    return _Found(target_findings("t", "Friability at most 1 %", summary, warned))


@case("M71", "", "only a handful of picks were warned by a check, far fewer than the 30 needed to compare them")
def _():
    from cellpoc.modelling.replay import target_findings
    summary, warned = _made_up_replay(0.3, 3)
    return _Found(target_findings("t", "Dissolution at 30 min at least 85 %", summary, warned))


# ------------------------------------------------------------------ running the cases
@dataclass
class CaseResult:
    case: Case
    passed: bool
    finding: Finding | None = None
    notes: list[str] | None = None


def run_case(one: Case) -> CaseResult:
    try:
        table = one.run()
    except Exception as error:                  # noqa: BLE001 - a crash is a failed case
        return CaseResult(one, False, None, [f"the table builder crashed: {type(error).__name__}: {error}"])
    key = (one.rule, one.variant)
    if key not in CATALOGUE:
        return CaseResult(one, False, None, ["this message is not in the catalogue"])
    matches = [f for f in table.findings if (f.rule, f.variant) == key]
    if not matches:
        found = ", ".join(sorted({f.rule + (f"/{f.variant}" if f.variant else "") for f in table.findings})) or "nothing"
        return CaseResult(one, False, None, [f"expected {one.rule}{'/' + one.variant if one.variant else ''} but found: {found}"])
    notes = []
    if matches[0].level != CATALOGUE[key].level:
        notes.append(f"expected level {CATALOGUE[key].level} but got {matches[0].level}")
    for f in table.findings:
        notes += [f"{f.rule}: {w}" for w in wording_problems(f)]
    return CaseResult(one, not notes, matches[0], notes)


def run_all() -> list[CaseResult]:
    return [run_case(one) for one in CASES]


def uncovered() -> list[tuple[str, str]]:
    return sorted(set(CATALOGUE) - {(one.rule, one.variant) for one in CASES})
