"""Health check for Stage 3a (modelling): so far the modelling table, the rules that stop a model being handed the answer, the grouped splitters, and the models.

In plain words it also checks (3a-3), in fast mode, that: the selection rule behaves as approved (worst of the hold-out types, must beat both baselines in every
one, ties within 5% go to the simpler model, and 'no model beats the baseline' is a possible answer); the models recover known answers (exact quadratics,
noise-free interpolation, a range that widens away from the data, conformal ranges that hit about 90%); destroying the test answers changes no prediction; the same
fold always gives the same predictions however many run at once; on freshly generated mock data every candidate beats the baseline against the generator's true values;
and every report lists both baselines, says how each model is fitted across results, and carries its labels (exploratory, robustness-only, 'proxy, not a confirmed supplier').

And (3a-2) that: every fold plan on every test table passes the guards (no row in both training and test, no batch, supplier or API on both
sides, every test date later than every training date); 200 random tables never produce a leaking split; a planted random split, backwards-in-time split,
duplicated row or twice-tested row is caught; no random splitter exists anywhere in the modelling code; the number of groups in each table equals a recount
from the raw file; and the fold maps carry the data-status label and, for the stand-in supplier, the words "proxy, not a confirmed supplier".

And (3a-1) that: every modelling message has a test and the message document is up to date; a correct `validation` section in a
setup is accepted; the five test tables (three synthetic mock files and, when present, the two real public datasets) are prepared with row counts
an independent recount agrees with; freshly generated mock files are prepared too; a result hiding among the inputs under another name is
blocked, as is a column calculated from the result (for example tensile strength and hardness); the balance ingredient is left out; rows whose amounts
do not add up are kept with their flag; an assumed unit travels with the column; and a stand-in for the supplier always carries the words
"proxy, not a confirmed supplier". Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import copy
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.ingest import ReadOptions, clean_table, read_and_clean, read_table  # noqa: E402
from cellpoc.modelling import CATALOGUE, PROXY_PHRASE, Finding, GroupSpec, build_table, build_table_for_setup  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, PUBLIC, fixture_available, fixture_setup  # noqa: E402
from cellpoc.setup import PROJECT_ROOT, validate  # noqa: E402
from checks import architecture, modelling_cases, setup_cases  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.modelling_messages_doc import DOC_PATH, build_text  # noqa: E402


def project_files() -> dict[str, tuple[int, int]]:
    skip = {".venv", ".git", "__pycache__", "runs", "chrome_profile"}
    return {p.relative_to(ROOT).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in ROOT.rglob("*")
            if p.is_file() and not (skip & set(p.relative_to(ROOT).parts))}


def recount_rows(frame: pd.DataFrame, result: str, inputs: list[str]) -> int:
    """How many rows have the result and every input, counted one row at a time (a different route from the table builder's)."""
    columns = [frame.columns.get_loc(c) for c in [result] + inputs]
    count = 0
    for row in frame.itertuples(index=False, name=None):
        if not any(pd.isna(row[i]) for i in columns):
            count += 1
    return count


# ---------------------------------------------------------------- the checks
def message_checks(cl: Checklist, results) -> None:
    failed = [r for r in results if not r.passed]
    cl.record(not failed, f"Each of the {len(results)} modelling messages is produced by a tiny table made to cause it, at the right level, in plain English",
              "; ".join(f"{r.case.rule} {r.case.variant}: {' / '.join(r.notes or [])[:160]}" for r in failed[:3]) if failed else f"{len(CATALOGUE)} messages in the catalogue")
    missing = modelling_cases.uncovered()
    cl.record(not missing, "Every message in the catalogue has at least one test",
              "no test for: " + ", ".join(f"{a} {b}".strip() for a, b in missing) if missing else f"{len(CATALOGUE)} of {len(CATALOGUE)} covered")
    CATALOGUE[("M99", "")] = CATALOGUE[("M01", "")]
    try:
        caught = ("M99", "") in modelling_cases.uncovered()
    finally:
        del CATALOGUE[("M99", "")]
    cl.record(caught, "Self-test: a message added without a test is caught by the coverage check", "")

    def fake(text):
        return Finding("M99", "", "error", "t", "", text)

    bad = ["the schema is wrong", "got None as null", "Traceback (most recent call last)", "KeyError: 'x'", "{unfilled}", "a DataFrame had a problem"]
    cl.record(all(modelling_cases.wording_problems(fake(t)) for t in bad) and not modelling_cases.wording_problems(fake("you wrote 'null' here")),
              "Self-test: the plain-English check catches technical wording (and ignores what the person typed, quoted)", "")
    saved = DOC_PATH.read_bytes().decode("utf-8") if DOC_PATH.exists() else ""
    expected = build_text(results)
    cl.record(saved == expected and bool(re.search(r", 0 without a test\.", expected)),
              f"docs/modelling_messages.md lists every message with its test and is up to date ({len(CATALOGUE)} messages)",
              str(DOC_PATH.relative_to(ROOT)) if saved == expected else "out of date: run  .venv\\Scripts\\python.exe tools\\make_modelling_messages.py")


def setup_section_checks(cl: Checklist) -> None:
    good = setup_cases.fresh()
    setup_cases._with_validation(good, inputs=["drug_pct", "binder_pct", "compression_force_kn"], derived_from={"hardness_kp": ["compression_force_kn"]},
                                 left_out=[{"id": "friability_pct", "why": "not measured on every row"}])
    found = [p.message for p in setup_cases.check(good) if p.rule in ("R69", "R70", "R71", "R72", "R73")]
    cl.record(not found, "A correct 'validation' section in a setup is accepted with no messages about it", "; ".join(found[:2]))
    amounts = setup_cases.fresh()
    amounts["data"]["column_map"].update({"Drug mg": "drug_mg", "Weight mg": "tablet_weight_mg"})
    amounts["data"]["composition"] = {"total_weight": "tablet_weight_mg"}
    setup_cases._with_validation(amounts, inputs=["drug_pct"])
    cl.record(not [p for p in setup_cases.check(amounts) if p.rule == "R69"],
              "The percentage columns made from amounts in mg (drug_mg becomes drug_pct) are accepted as inputs", "")


def table_checks(cl: Checklist, tables: dict) -> None:
    for name in NAMES:
        if name not in tables:
            cl.skip(f"{name}: the modelling table", "the real public data is not on this computer (it is never in git); the check runs when it is")
            continue
        t = tables[name]
        usable = [r for r in t.responses.values() if r.usable]
        wrong = [f"{r.name}: {len(r.rows)} rows, recount {recount_rows(t.frame, r.name, r.numeric + r.categorical)}" for r in t.responses.values()
                 if len(r.rows) != recount_rows(t.frame, r.name, r.numeric + r.categorical)]
        status = t.label.short if t.label else "no label"
        wanted = "SYNTHETIC DATA" if name not in PUBLIC else "REAL PUBLIC DATA, NOT CLIENT DATA"
        cl.record(t.ok and len(usable) == len(t.responses) and not wrong and status == wanted,
                  f"{name} ({wanted.lower()}): {len(t.frame):,} rows; {len(t.responses)} results each use the same rows as an independent recount "
                  f"({', '.join(f'{r.name} {len(r.rows):,}' for r in t.responses.values())})",
                  "; ".join(wrong[:2]) or "; ".join(f.message for f in t.findings if f.level == "error")[:200] or status)


def fresh_mock_checks(cl: Checklist) -> None:
    problems, shown = [], []
    with tempfile.TemporaryDirectory() as folder:
        for seed, difficulty, base in ((8101, "easy", "mock_easy"), (8102, "hard", "mock_hard")):
            out = Path(folder) / f"fresh_{difficulty}.csv"
            done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "make_mock_data.py"), "--n", "300", "--seed", str(seed), "--difficulty", difficulty, "--out", str(out)],
                                  capture_output=True, text=True, cwd=folder)
            if done.returncode != 0 or not out.exists():
                problems.append(f"{difficulty}: the generator failed")
                continue
            # the setup reader only opens files inside the project (a safety rule), so the fresh file is read directly and cleaned with the same setup
            setup = fixture_setup(base)
            clean = clean_table(read_table(out, ReadOptions.from_setup(setup)), setup)
            table = build_table(setup, clean, None, f"fresh {difficulty} (seed {seed})")
            wrong = [r.name for r in table.responses.values() if len(r.rows) != recount_rows(table.frame, r.name, r.numeric + r.categorical)]
            if not table.ok or wrong or len(table.responses) != 3:
                problems.append(f"{difficulty}: {'; '.join(f.message for f in table.findings if f.level == 'error')[:120] or 'row counts differ for ' + ', '.join(wrong)}")
            shown.append(f"{difficulty} seed {seed}: {len(table.frame)} rows")
    cl.record(not problems, "Freshly generated mock files (new seeds, never used to choose anything) are prepared with row counts an independent recount agrees with",
              "; ".join(problems) if problems else "; ".join(shown))


def leakage_checks(cl: Checklist, tables: dict) -> None:
    # a result hiding among the inputs under another name
    frame = modelling_cases.tiny_frame()
    frame["disguised"] = frame["y"] * 3 + 1
    frame["noisy_copy"] = frame["y"] + np.random.default_rng(3).normal(0, 0.1, len(frame))
    table = build_table(modelling_cases.tiny_setup(inputs=["drug_pct", "binder_pct", "disguised", "noisy_copy"]), modelling_cases.CleanResult(frame, [], []), None, "t")
    left = dict(table.responses["y"].left_out_inputs)
    honest = float(frame["drug_pct"].corr(frame["y"]))
    cl.record(left.get("disguised") == "copy" and left.get("noisy_copy") == "copy" and table.responses["y"].numeric == ["drug_pct", "binder_pct"] and 0.98 < honest < 0.999,
              "Self-test: a result hiding among the inputs (exactly, or with a little noise) is found and left out, while a very strong honest input "
              f"(correlation {honest:.3f} with the result) is kept",
              f"left out: {left}")
    # a column calculated from others: found only because it is declared (the documented limit)
    rng = np.random.default_rng(5)
    n = 200
    frame = pd.DataFrame({"hardness": rng.uniform(5, 15, n), "diameter": rng.uniform(8, 12, n), "thickness": rng.uniform(3, 5, n), "drug_pct": rng.uniform(10, 30, n)})
    frame["tensile"] = 2 * frame["hardness"] / (np.pi * frame["diameter"] * frame["thickness"])
    inputs = ["drug_pct", "hardness", "diameter", "thickness"]
    undeclared = build_table(modelling_cases.tiny_setup(responses=["tensile"], inputs=inputs, groups={"batch": {"column": "drug_pct"}}), modelling_cases.CleanResult(frame, [], []), None, "t")
    declared = build_table(modelling_cases.tiny_setup(responses=["tensile"], inputs=inputs, groups={"batch": {"column": "drug_pct"}},
                                                      derived_from={"tensile": ["hardness", "diameter", "thickness"]}), modelling_cases.CleanResult(frame, [], []), None, "t")
    cl.record(declared.responses["tensile"].numeric == ["drug_pct"] and "hardness" in undeclared.responses["tensile"].numeric,
              "Declared calculated columns are never used to predict each other (tensile strength is not predicted from the hardness, diameter and thickness it is calculated from)",
              f"declared: inputs kept {declared.responses['tensile'].numeric}")
    cl.record(set(c for c, _ in declared.responses["tensile"].left_out_inputs) == {"hardness", "diameter", "thickness"} and "diameter" in undeclared.responses["tensile"].numeric,
              "Known limit, stated: a product formula is NOT caught by looking at correlations, so the calculated-from list must be declared (this is why the setup asks for it)", "")
    # the reverse direction: a calculated column is not used to predict a column it is calculated from
    reverse = build_table(modelling_cases.tiny_setup(responses=["hardness"], inputs=inputs + ["tensile"], groups={"batch": {"column": "drug_pct"}},
                                                     derived_from={"tensile": ["hardness", "diameter", "thickness"]}), modelling_cases.CleanResult(frame, [], []), None, "t")
    cl.record("tensile" not in reverse.responses["hardness"].numeric and dict(reverse.responses["hardness"].left_out_inputs).get("tensile") == "derived",
              "Tensile strength is not used to predict hardness either (the leak runs both ways)", "")
    # the real batch dataset: the exact copies in Process.csv and the tensile formula
    if "batch_production" in tables:
        base = fixture_setup("batch_production")
        extra = copy.deepcopy(base)
        extra["data"]["validation"]["inputs"] = base["data"]["validation"]["inputs"] + ["drug_release_average", "tbl_av_hardness", "tbl_max_diameter"]
        t = build_table_for_setup(extra, None, PROJECT_ROOT, "batch_production with extra inputs")
        left = dict(t.responses["dissolution_av"].left_out_inputs)
        tensile = dict(t.responses["tbl_tensile"].left_out_inputs)
        cl.record(left.get("drug_release_average") == "copy" and tensile.get("tbl_av_hardness") == "source" and tensile.get("tbl_max_diameter") == "source",
                  "Real batch data: the exact copy of dissolution that Process.csv carries is blocked when offered as an input, and hardness and diameter are blocked for tensile strength",
                  f"dissolution left out: {left}; tensile left out: {tensile}")
        plain = tables["batch_production"]
        offered = set(plain.responses["tbl_tensile"].numeric) | set(plain.responses["dissolution_av"].numeric)
        cl.record(not offered & {"drug_release_average", "tbl_av_hardness", "tbl_tensile", "tbl_max_diameter", "dissolution_av", "batch_yield"},
                  "Real batch data: no test result of the finished tablet is ever offered as an input", "")


def composition_checks(cl: Checklist, tables: dict) -> None:
    for name in ("mock_easy", "mock_hard"):
        t = tables[name]
        ingredients = ["drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "filler_pct"]
        total = t.frame[ingredients].sum(axis=1)
        never_used = all("filler_pct" not in r.numeric for r in t.responses.values())
        cl.record(bool(((total - 100).abs() < 0.05).all()) and never_used,
                  f"{name}: the five ingredient percentages add up to 100 in every row, and the balance ingredient (filler) is left out of the inputs so the same information is not given twice",
                  f"largest difference from 100: {float((total - 100).abs().max()):.3f}")
    if "literature" in tables:
        t = tables["literature"]
        pct = [c for c in t.responses["hardness_kp"].numeric if c.endswith("_pct")]
        total = t.frame[pct].sum(axis=1)
        flagged = t.frame["mass_balance_flag"]
        kept = all(set(np.flatnonzero(flagged.to_numpy())) <= set(r.rows.tolist()) for r in t.responses.values())
        cl.record(bool((total <= 100.0 + 2.0 + 1e-9).all()) and int(flagged.sum()) == 118 and kept and "mass_balance_flag" in t.flag_columns,
                  "Literature table (real public data): the listed percentages never add up to more than the tablet weight (plus 2%), and the 118 rows that fall short "
                  "are kept in every result's rows with their flag carried (not removed, not repaired)",
                  f"largest total {float(total.max()):.2f}%, flagged rows {int(flagged.sum())}")
        cl.record(t.column_label("hardness_kp") == "hardness_kp (unit assumed)" and "sodium_saccharine_pct" in t.unit_assumed
                  and {c for c, _ in t.left_out} == {"drug_content_pct", "water_absorption_pct", "wetting_time_s"},
                  "Literature table: hardness and sodium saccharine carry '(unit assumed)', and the three zero-heavy columns are listed as left out, not modelled",
                  ", ".join(sorted(t.unit_assumed)))
    else:
        cl.skip("Literature table: flagged rows, assumed units and left-out columns", "the real public data is not on this computer")


def proxy_checks(cl: Checklist, tables: dict) -> None:
    proxy, confirmed = GroupSpec("supplier", ("api_code",), False), GroupSpec("supplier", ("binder_supplier",), True)
    cl.record(PROXY_PHRASE in proxy.heading and PROXY_PHRASE not in confirmed.heading and PROXY_PHRASE == "proxy, not a confirmed supplier",
              f"A stand-in for the supplier is always named with the exact words '{PROXY_PHRASE}'; a confirmed supplier is not", proxy.heading)
    if "batch_production" in tables:
        t = tables["batch_production"]
        notes = [f for f in t.findings if f.rule == "M24"]
        cl.record(PROXY_PHRASE in t.groups["supplier"].heading and len(notes) == 1 and PROXY_PHRASE in notes[0].message,
                  "Real batch data: the supplier hold-out (api_code) is headed, and its note says, 'proxy, not a confirmed supplier'", t.groups["supplier"].heading)
    cl.record(PROXY_PHRASE not in tables["mock_easy"].groups["supplier"].heading, "The mock's binder supplier is a real (synthetic) supplier column, so it is not called a proxy", "")
    # no phrase is written by hand anywhere else: it comes from the one place
    hand_written = [p.relative_to(ROOT).as_posix() for p in (ROOT / "cellpoc" / "modelling").rglob("*.py") if p.name != "findings.py" and PROXY_PHRASE in p.read_text(encoding="utf-8")]
    cl.record(not hand_written, "The proxy wording is written in exactly one place, so no heading can drift from it", ", ".join(hand_written))


def honesty_checks(cl: Checklist) -> None:
    result = read_and_clean(fixture_setup("mock_small"), None, PROJECT_ROOT)
    before = result.frame.copy(deep=True)
    table = build_table(fixture_setup("mock_small"), result, None, "small")
    same = before.equals(result.frame) and table.frame is not None and len(table.frame) == len(before)
    values_kept = bool(table.frame.equals(before.reset_index(drop=True)))       # equals() counts a gap in the same place as the same
    cl.record(same and values_kept, "Preparing a table never changes a value or fills a gap: the table holds exactly the values that were read (gaps stay gaps)", "")
    cl.record(all(len(set(r.rows.tolist())) == len(r.rows) and bool((np.diff(r.rows) > 0).all()) for r in table.responses.values()),
              "Each result's rows are listed once each, in the file's own order (no shuffling, no sampling)", "")


# ---------------------------------------------------------------- 3a-2: the grouped splitters and their guards
FORBIDDEN_SPLITTERS = re.compile(r"train_test_split|KFold|ShuffleSplit|cross_val_|cross_validate|GridSearchCV|RandomizedSearchCV|HalvingGridSearchCV|HalvingRandomSearchCV"
                                 r"|early_stopping\s*=\s*True|validation_fraction|\.sample\(|\bshuffle\b|\bpermutation\b")


def forbidden_in(paths) -> list[str]:
    """Anything in the given files that divides rows at random, or lets a model do it behind our back (scikit-learn's random splitters, a model's own validation split)."""
    return [f"{p.name} line {n}: {line.strip()[:60]}" for p in paths for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if FORBIDDEN_SPLITTERS.search(line)]


def random_table(rng: np.random.Generator, name: str):
    n = int(rng.integers(60, 400))
    frame = pd.DataFrame({"x1": rng.uniform(0, 1, n), "y": rng.normal(0, 1, n),
                          "batch_id": [f"B{i}" for i in rng.integers(0, int(rng.integers(2, 30)), n)],
                          "supplier": [f"S{i}" for i in rng.integers(0, int(rng.integers(1, 12)), n)],
                          "date": pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, int(rng.integers(1, 40)), n), unit="D")})
    frame.loc[rng.random(n) < 0.05, "batch_id"] = np.nan
    setup = modelling_cases.tiny_setup(inputs=["x1"], groups={"batch": {"column": "batch_id"}, "supplier": {"column": "supplier", "confirmed": bool(rng.integers(0, 2))}, "date": {"column": "date"}})
    return build_table(setup, modelling_cases.CleanResult(frame, [], []), None, name)


def split_checks(cl: Checklist, tables: dict) -> None:
    from cellpoc.modelling import Fold, FoldPlan, SplitError, make_fold_plan, make_fold_plans, plan_problems

    # every table, every result, every hold-out type: a plan, checked by the guards, that tests each row at most once
    problems, built, skipped = [], 0, 0
    for name, t in tables.items():
        for r, rt in t.responses.items():
            for kind, plan in make_fold_plans(t, r).items():
                built += plan.available
                skipped += not plan.available
                bad = plan_problems(plan, t)
                tested = [i for f in plan.folds for i in f.test.tolist()]
                if bad or len(tested) != len(set(tested)) or any(len(f.train) + len(f.test) > rt.rows.size for f in plan.folds):
                    problems.append(f"{name}/{r}/{kind}: {'; '.join(bad)[:100] or 'a row is tested twice'}")
    cl.record(not problems, f"All {built} fold plans on the test tables (every result, every hold-out type) pass the guards: no row in both training and test, no group on both sides, "
                            f"no row tested twice ({skipped} hold-outs are skipped with a message because the table cannot support them)", "; ".join(problems[:3]))

    # the same table always gives the same folds, whatever order its rows are stored in
    clean = read_and_clean(fixture_setup("mock_easy"), None, PROJECT_ROOT)
    shuffled = copy.copy(clean)
    shuffled.frame = clean.frame.sample(frac=1, random_state=11)
    a = build_table(fixture_setup("mock_easy"), clean, None, "a")
    b = build_table(fixture_setup("mock_easy"), shuffled, None, "b")
    same = all([(f.held_out, len(f.train), len(f.test)) for f in make_fold_plan(a, "hardness_kp", k).folds] ==
               [(f.held_out, len(f.train), len(f.test)) for f in make_fold_plan(b, "hardness_kp", k).folds] for k in ("batch", "supplier", "date"))
    again = [[f.held_out for f in make_fold_plan(a, "hardness_kp", k).folds] for k in ("batch", "supplier", "date")] == [[f.held_out for f in make_fold_plan(a, "hardness_kp", k).folds] for k in ("batch", "supplier", "date")]
    cl.record(same and again, "The same folds come out every time, and when the same rows are stored in a different order (nothing is random)", "")

    # property test on 200 random tables of random shapes
    rng = np.random.default_rng(20261010)
    broken, plans_made = [], 0
    for number in range(200):
        t = random_table(rng, f"random {number}")
        if not t.responses["y"].usable:
            continue
        for kind in ("batch", "supplier", "date"):
            try:
                plan = make_fold_plan(t, "y", kind)
            except SplitError as error:
                broken.append(f"#{number} {kind}: {error}")
                continue
            plans_made += 1
            frame, spec = t.frame, t.groups[kind]
            for f in plan.folds:
                if kind == "date":
                    if not frame["date"].iloc[f.train].max() < frame["date"].iloc[f.test].min() or set(frame["date"].iloc[f.train]) & set(frame["date"].iloc[f.test]):
                        broken.append(f"#{number} date fold {f.number}: dates overlap or run backwards")
                elif set(frame[spec.columns[0]].iloc[f.train].dropna()) & set(frame[spec.columns[0]].iloc[f.test].dropna()):
                    broken.append(f"#{number} {kind} fold {f.number}: a group is on both sides")
            if kind != "date" and plan.available and not plan.n_dropped:
                placed = frame[spec.columns[0]].iloc[t.responses["y"].rows].notna().sum()
                if sum(len(f.test) for f in plan.folds) != placed:
                    broken.append(f"#{number} {kind}: every placed row should be tested exactly once")
    cl.record(not broken, f"200 random tables of random sizes and shapes ({plans_made} fold plans): groups never straddle a split, every test date is later than every training date, "
                          "and every row is tested exactly once", "; ".join(broken[:3]))

    # the guards catch a split that leaks (each leak is planted on purpose)
    t = build_table(modelling_cases.tiny_setup(groups={"batch": {"column": "batch_id"}, "date": {"column": "date"}}), modelling_cases.CleanResult(modelling_cases.dated_frame(), [], []), None, "t")
    rows = t.responses["y"].rows
    rng2 = np.random.default_rng(7)
    mixed = rng2.permutation(rows)
    random_split = FoldPlan("t", "y", "batch", "whole batches (batch_id)", folds=[Fold(1, np.sort(mixed[24:]), np.sort(mixed[:24]), ("random",))])
    backwards = FoldPlan("t", "y", "date", "later dates (date)", folds=[Fold(1, rows[60:], rows[:60], ("x",))])
    duplicated = FoldPlan("t", "y", "batch", "whole batches (batch_id)", folds=[Fold(1, rows[:90], rows[80:], ("x",))])
    seen_twice = FoldPlan("t", "y", "batch", "whole batches (batch_id)", folds=[Fold(1, rows[6:], rows[:6], ("B0",)), Fold(2, rows[12:], rows[:6], ("B0",))])
    caught = [bool(plan_problems(p, t)) for p in (random_split, backwards, duplicated, seen_twice)]
    cl.record(all(caught), "Self-test: the guards catch a random split, a split that tests on earlier dates than it trains on, rows in both training and test, and a row tested twice",
              f"caught: {caught}")
    clean_plan = make_fold_plan(t, "y", "batch")
    cl.record(not plan_problems(clean_plan, t), "Self-test: the same guards pass a proper grouped split of that table", f"{len(clean_plan.folds)} folds")

    # no random splitter anywhere in the modelling code
    found = forbidden_in(sorted((ROOT / "cellpoc" / "modelling").glob("*.py")))
    with tempfile.TemporaryDirectory() as folder:
        trap = Path(folder) / "trap.py"
        trap.write_text("from sklearn.model_selection import train_test_split\nm = Model(early_stopping=True)\nx = frame.sample(frac=0.2)\n", encoding="utf-8")
        planted = forbidden_in([trap])
    cl.record(not found and len(planted) == 3, "The modelling code contains no random splitter (no train_test_split, KFold, ShuffleSplit, cross-validation helper, search helper, sampling, shuffling, "
                                                "or model that holds out rows by itself); a planted example of each kind is caught", "; ".join(found[:3]) or f"planted lines caught: {len(planted)} of 3")


def group_count_checks(cl: Checklist, tables: dict) -> None:
    """The number of groups in each table, recounted from the raw files with the plain csv module (no shared code)."""
    import csv

    def distinct(path: Path, delimiter: str, columns: list[str]) -> int:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=delimiter))
        names = {k.strip(): k for k in rows[0]}
        return len({tuple(r[names[c]].strip() for c in columns) for r in rows if all(r[names[c]].strip() for c in columns)})

    expected = []
    for name, file in (("mock_easy", "mock_formulation_experiments.csv"), ("mock_hard", "mock_formulation_hard.csv"), ("mock_small", "mock_formulation_small.csv")):
        path = ROOT / "data" / "mock" / file
        expected.append((name, {"batch": distinct(path, ",", ["batch_id"]), "supplier": distinct(path, ",", ["binder_supplier"]), "date": distinct(path, ",", ["date"])}))
    lab = ROOT / "data" / "public" / "batch_production" / "Laboratory.csv"
    if lab.exists():
        expected.append(("batch_production", {"batch": distinct(lab, ";", ["api_batch"]), "supplier": distinct(lab, ";", ["api_code"]), "date": distinct(lab, ";", ["start"])}))
    lit = ROOT / "data" / "public" / "formulation_literature" / "final Data All Exipients.csv"
    if lit.exists():
        expected.append(("literature", {"api": distinct(lit, ",", ["Molecular Weight", "XLogP3-AA", "Hydrogen Bond Donor Count", "Hydrogen Bond Acceptor Count", "Rotational bond count",
                                                                   "Topological surface area", "Heavy atom count", "Complexity", "LogS"])}))
    wrong = []
    for name, counts in expected:
        t = tables[name]
        for kind, want in counts.items():
            got = len(t.frame[list(t.groups[kind].columns)].drop_duplicates())
            if got != want:
                wrong.append(f"{name} {kind}: table {got}, recount {want}")
    shown = "; ".join(f"{n}: " + ", ".join(f"{k} {v}" for k, v in c.items()) for n, c in expected)
    cl.record(not wrong, "The number of batches, suppliers (or stand-ins), dates and APIs in every table equals a recount from the raw file", "; ".join(wrong) or shown)


def fold_shape_checks(cl: Checklist, tables: dict) -> None:
    from cellpoc.modelling import make_fold_plans
    from cellpoc.modelling.foldmap import build_fold_map

    plans = make_fold_plans(tables["mock_easy"], "hardness_kp")
    sizes = [len(f.held_out) for f in plans["batch"].folds]
    suppliers = sorted(g for f in plans["supplier"].folds for g in f.held_out)
    steps = plans["date"].folds
    ordered = all(max(steps[i].held_out) < min(steps[i + 1].held_out) for i in range(len(steps) - 1))
    cl.record(len(plans["batch"].folds) == 5 and max(sizes) - min(sizes) <= 1 and sum(sizes) == 60 and suppliers == ["A", "B", "C"] and len(plans["supplier"].folds) == 3
              and len(steps) == 4 and ordered,
              "Easy mock: 60 batches in 5 folds of 12 whole batches; each of the 3 suppliers held out once; 4 forward steps over 60 dates in time order",
              f"batches per fold {sizes}; suppliers {suppliers}; steps {len(steps)}")
    small = make_fold_plans(tables["mock_small"], "hardness_kp")
    cl.record(len(small["batch"].folds) == 4 and len(small["supplier"].folds) == 2 and not small["date"].available
              and any(f.variant == "few_times" for f in small["date"].findings),
              "Small mock: 4 batches held out one at a time, 2 suppliers held out one at a time, and no forward steps because there are only 4 dates (said in a message, not replaced by random rows)", "")
    maps = {name: build_fold_map(t) for name, t in tables.items()}
    ok_head = all(text.startswith(f"# Fold map [{tables[n].label.short}]") and f": {n}\n" in text.split("\n\n")[0] + "\n" and "No random rows are ever used" in text for n, text in maps.items())
    cl.record(ok_head, "Every fold map opens with the data-status label and states that no random rows are ever used", "")
    tagged = [n for n, t in tables.items() if t.tag]
    cl.record(set(tagged) == {"batch_production_extended", "literature"} & set(tables)
              and all(all(tables[n].tag in line for line in text.splitlines() if line.startswith("#")) for n, text in maps.items() if n in tagged),
              "Exploratory and robustness-only tables carry their label in every heading of their fold map (the extended batch comparison: exploratory, smaller and non-random sample, "
              "not part of the main comparison; the literature table: robustness test only); the main comparisons carry none", ", ".join(tagged))
    if "batch_production" in tables:
        text = maps["batch_production"]
        named = [line for line in text.splitlines() if "api_code" in line]
        cl.record(bool(named) and all(PROXY_PHRASE in line for line in named),
                  "Real batch data: every line of the fold map that names api_code also says 'proxy, not a confirmed supplier'", f"{len(named)} lines name api_code")
        headings = [line for line in text.splitlines() if line.startswith("## Hold-out: whole suppliers")]
        cl.record(len(headings) == 1 and PROXY_PHRASE in headings[0], "Real batch data: the supplier hold-out's heading in the fold map carries the proxy wording", headings[0] if headings else "")
    if "literature" in tables:
        lit = make_fold_plans(tables["literature"], "hardness_kp")
        groups = sum(len(f.held_out) for f in lit["api"].folds)
        cl.record(len(lit["api"].folds) == 5 and groups == 126 and not lit["batch"].available and not lit["supplier"].available and not lit["date"].available,
                  "Literature table (real public data): only the leave-APIs-out hold-out runs (126 APIs in 5 folds); batch, supplier and date hold-outs are skipped with a message because the file has none",
                  f"APIs in the folds: {groups}")
    time_ok = []
    for name, t in tables.items():
        for r in t.responses:
            plan = make_fold_plans(t, r)["date"]
            for f in plan.folds:
                times = t.frame[t.groups["date"].columns[0]]
                time_ok.append(set(times.iloc[f.train]).isdisjoint(set(times.iloc[f.test])) and times.iloc[f.train].max() < times.iloc[f.test].min())
    cl.record(bool(time_ok) and all(time_ok), f"Forward steps on every table that has dates ({len(time_ok)} steps): every test date is later than every training date, and no date (no month, for month-only data) is split",
              "")


# ---------------------------------------------------------------- 3a-3: the models, the selection rule and the report (fast mode)
def fake_validation(errors: dict):
    """A made-up set of results where each model's error is exactly the given multiple of the result's spread, for testing the selection rule."""
    from cellpoc.modelling import Fold, FoldPlan
    from cellpoc.modelling.models import FAST, Prediction
    from cellpoc.modelling.selection import spread
    from cellpoc.modelling.validate import FoldRun, PlanRun, Validation

    table = build_table(modelling_cases.tiny_setup(groups={"batch": {"column": "batch_id"}}), modelling_cases.CleanResult(modelling_cases.tiny_frame(120), [], []), None, "t")
    rows = table.responses["y"].rows[:60]
    y, sd = table.frame["y"].to_numpy()[rows], spread(table, "y")
    sign = np.where(np.arange(len(rows)) % 2 == 0, 1.0, -1.0)
    runs = {}
    for kind, by_model in errors.items():
        preds = {m: Prediction(y + e * sd * sign, y + e * sd * sign - 1, y + e * sd * sign + 1) for m, e in by_model.items()}
        plan = FoldPlan("t", "y", kind, f"({kind})", folds=[Fold(1, rows[:0], rows, ("g",))])
        runs[("y", kind)] = PlanRun(plan, [FoldRun(1, rows, y, preds, {m: 0.0 for m in preds})])
    return Validation(table, FAST, runs, [], 0.0)


def selection_checks(cl: Checklist) -> None:
    from cellpoc.modelling.selection import select

    base = {"mean": 1.0, "nearest": 1.2}
    tie = select(fake_validation({"batch": {**base, "quadratic": 0.50, "boosting": 0.48, "forest": 0.60, "ensemble": 0.70, "gp": 0.80}}), "y")
    cl.record(tie.chosen == "quadratic", "Selection rule: ties within 5% go to the simpler or faster model (boosting scores 0.48, quadratic 0.50: within 5%, so the simpler quadratic regression is chosen)",
              f"chosen {tie.chosen}; {tie.why}")
    outside = select(fake_validation({"batch": {**base, "quadratic": 0.60, "boosting": 0.48}}), "y")
    cl.record(outside.chosen == "boosting", "Selection rule: a model that is more than 5% better is chosen even though it is more complex (0.48 against 0.60)", f"chosen {outside.chosen}")
    worst = select(fake_validation({"batch": {**base, "quadratic": 0.30, "forest": 0.40}, "supplier": {**base, "quadratic": 0.95, "forest": 0.45}}), "y")
    cl.record(worst.chosen == "forest" and abs(worst.worst["quadratic"] - 0.95) < 1e-9,
              "Selection rule: the score is the worst of the hold-out types (the quadratic regression is best on batches but poor on suppliers, so the steadier forest is chosen)", f"worst scores {worst.worst}")
    none = select(fake_validation({"batch": {**base, "quadratic": 1.05, "forest": 1.10}}), "y")
    cl.record(none.chosen is None and none.why == "no model beats the baseline.", "Selection rule: when no model beats the baseline, the answer is 'no model beats the baseline' and none is offered", none.why)
    nearest = select(fake_validation({"batch": {"mean": 1.0, "nearest": 0.5, "quadratic": 0.6, "forest": 0.7}}), "y")
    cl.record(nearest.chosen is None, "Selection rule: beating the training mean is not enough: a model must beat the nearest-neighbour lookup too", f"chosen {nearest.chosen}")
    mixed = select(fake_validation({"batch": {**base, "quadratic": 0.3, "forest": 0.5}, "supplier": {**base, "quadratic": 1.1, "forest": 0.5}}), "y")
    cl.record(mixed.chosen == "forest" and "quadratic" not in mixed.eligible,
              "Selection rule: a model must beat the baselines in EVERY hold-out type that can be run (the quadratic regression fails on suppliers and is not eligible)", f"eligible {mixed.eligible}")


def inner_blocks(n: int) -> list:
    """Four inner folds over n training rows, for the made-up tests (the real ones are whole groups: see inner_folds)."""
    index = np.arange(n)
    return [(np.flatnonzero(index % 4 != f), np.flatnonzero(index % 4 == f)) for f in range(4)]


def regression_checks(cl: Checklist) -> None:
    from cellpoc.modelling.models import FAST, LinearRidge, PENALTIES, QuadraticRidge, choose_penalty

    rng = np.random.default_rng(3)
    # the fast way of trying every penalty gives exactly the answer of scikit-learn's own ridge fitted penalty by penalty, for a wide and for a tall table
    from sklearn.linear_model import Ridge
    agree = []
    for rows, columns in ((120, 400), (300, 40)):
        A = rng.normal(size=(rows, columns))
        b = A[:, :3].sum(axis=1) + rng.normal(0, 1, rows)
        folds = inner_blocks(rows)
        chosen, _, rmse = choose_penalty(A, b, folds)
        errors = [sum(float(((b[c] - Ridge(alpha=p).fit(A[f], b[f]).predict(A[c])) ** 2).sum()) for f, c in folds) for p in PENALTIES]
        reference = float(np.sqrt(min(errors) / sum(len(c) for _, c in folds)))
        agree.append(chosen == PENALTIES[int(np.argmin(errors))] and abs(rmse - reference) < 1e-6)
    cl.record(all(agree), "The fast penalty search is exact: for a wide table (more columns than rows) and a tall one it picks the same penalty, with the same error, as scikit-learn's own ridge fitted penalty by penalty", str(agree))
    # a linear function is recovered exactly by the linear regression, with a small penalty chosen
    X, Xt = rng.uniform(-1, 1, (300, 5)), rng.uniform(-1, 1, (200, 5))
    line = lambda A: 3 + A @ np.array([1.0, -2.0, 0.5, 0.0, 4.0])
    model = LinearRidge().fit(X, line(X), None, inner_blocks(300))
    miss = float(np.sqrt(np.mean((line(Xt) - model.predict(Xt).mean) ** 2)) / line(Xt).std())
    cl.record(miss < 0.01 and model.penalty_ <= 0.1 and model.by_validation_, "Known answer: the linear regression recovers an exact linear function (error under 1% of its spread) and chooses a small penalty by validation",
              f"error {miss:.4f}, penalty {model.penalty_}")
    # the penalty is chosen on the training rows: big for pure noise in many columns, small for clean data
    noise_X, noise_y = rng.normal(size=(160, 120)), rng.normal(size=160)
    chosen, by_validation, error = choose_penalty(noise_X, noise_y, inner_blocks(160))
    cl.record(chosen >= 1000 and by_validation, "The ridge penalty is chosen by validation inside the training rows: pure noise in 120 columns gets a strong penalty", f"penalty {chosen}")
    cl.record(choose_penalty(noise_X, noise_y, None) == (1.0, False, float("nan")) or choose_penalty(noise_X, noise_y, None)[:2] == (1.0, False),
              "With too few groups to hold any out, the penalty falls back to 1 and says so (it is never chosen on the fold being tested)", "")
    # category columns are never squared or multiplied: squares and pairwise products of the numeric inputs only
    n_numeric, n_category = 5, 3
    Z = np.hstack([rng.normal(size=(120, n_numeric)), np.eye(3)[rng.integers(0, 3, 120)]])
    quad = QuadraticRidge(n_numeric).fit(Z, rng.normal(size=120), None, inner_blocks(120))
    expected = n_numeric * (n_numeric + 3) // 2 + n_category
    cl.record(quad.model_.coef_.shape[0] == expected, f"The quadratic regression expands only the numeric inputs ({n_numeric} give {n_numeric * (n_numeric + 3) // 2} squares and products); the {n_category} category columns enter once, linearly: "
                                                       f"{expected} features in all", f"{quad.model_.coef_.shape[0]} features")


def inner_fold_checks(cl: Checklist, tables: dict) -> None:
    from cellpoc.modelling import make_fold_plans
    from cellpoc.modelling.validate import inner_folds

    def problems_of(t, kind, fold, fit, check) -> list[str]:
        found = []
        fit_rows, check_rows = fold.train[fit], fold.train[check]
        if set(fit.tolist()) & set(check.tolist()):
            found.append("the same row is used to fit and to check")
        if (set(fit_rows.tolist()) | set(check_rows.tolist())) & set(fold.test.tolist()):
            found.append("a held-out row is used inside the training rows")
        spec = t.groups[kind]
        if kind == "date":
            times = t.frame[spec.columns[0]]
            if not times.iloc[fit_rows].max() < times.iloc[check_rows].min():
                found.append("a check date is not later than every fit date")
        else:
            if kind not in labels_of.setdefault(id(t), {}):           # the group label of every row, worked out once per table and hold-out type
                labels_of[id(t)][kind] = t.frame[list(spec.columns)].apply(lambda c: c.map(str)).agg(" | ".join, axis=1)
            labels = labels_of[id(t)][kind]
            if set(labels.iloc[fit_rows]) & set(labels.iloc[check_rows]):
                found.append("a group is on both sides of an inner fold")
        return found

    labels_of: dict = {}

    bad, count = [], 0
    for name, t in tables.items():
        result = next((r for r, rt in t.responses.items() if rt.usable), None)
        if result is None:
            continue
        for kind, plan in make_fold_plans(t, result).items():
            for fold in plan.folds:
                for fit, check in inner_folds(t, plan, fold.train) or []:
                    count += 1
                    bad += [f"{name}/{kind}/fold {fold.number}: {p}" for p in problems_of(t, kind, fold, fit, check)]
    t0 = tables["mock_small"]
    plan0 = make_fold_plans(t0, "hardness_kp")["batch"]
    planted = problems_of(t0, "batch", plan0.folds[0], np.arange(len(plan0.folds[0].train)), np.arange(len(plan0.folds[0].train)))
    cl.record(not bad and count > 0 and len(planted) >= 1,
              f"The validation folds used to choose a ridge penalty ({count} on the test tables) are made only of rows inside each training fold, never the held-out fold, with whole groups (or forward in time) kept apart; "
              "a planted overlap is caught", "; ".join(bad[:2]) or f"planted problems caught: {len(planted)}")


def synthetic_model_checks(cl: Checklist) -> None:
    from cellpoc.modelling.models import FAST, GaussianProcess, GradientBoostingConformal, single_models

    def r2(y, p):
        return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    rng = np.random.default_rng(1)
    X, Xt = rng.uniform(-1, 1, (600, 4)), rng.uniform(-1, 1, (300, 4))
    smooth = lambda A: 1 + 2 * A[:, 0] - A[:, 1] + 0.5 * A[:, 0] ** 2 + A[:, 0] * A[:, 1] - 0.7 * A[:, 1] ** 2 + np.sin(2 * A[:, 2])
    quadratic = lambda A: 1 + 2 * A[:, 0] - A[:, 1] + 0.5 * A[:, 0] ** 2 + A[:, 0] * A[:, 1] - 0.7 * A[:, 1] ** 2
    models = {m.key: m for m in single_models(FAST, 4, 4)}
    fits = {k: m.fit(X, smooth(X)).predict(Xt) for k, m in models.items() if k not in ("mean", "nearest")}
    scores = {k: r2(smooth(Xt), p.mean) for k, p in fits.items()}
    cl.record(all(scores[k] > 0.95 for k in ("quadratic", "boosting", "forest", "ensemble")) and scores["gp"] > 0.99,
              "Known answer: on a smooth made-up function every model recovers it on fresh points (R-squared above 0.95; the Gaussian process above 0.99)", ", ".join(f"{k} {v:.3f}" for k, v in scores.items()))
    by_key = {m.key: m for m in single_models(FAST, 4, 4)}
    ridge = by_key["quadratic"].fit(X, quadratic(X), None, inner_blocks(len(X))).predict(Xt)
    miss = float(np.sqrt(np.mean((quadratic(Xt) - ridge.mean) ** 2)) / quadratic(Xt).std())
    cl.record(miss < 0.02, "Known answer: the quadratic regression recovers an exact linear-plus-squares-plus-interaction function (error under 2% of its spread)", f"{miss:.4f}")
    # noise-free interpolation and uncertainty that grows away from the data
    Z = rng.uniform(0, 1, (60, 3))
    y = np.sin(2 * Z[:, 0]) + Z[:, 1] ** 2 - Z[:, 0] * Z[:, 2]
    gp = GaussianProcess(FAST, 3).fit(Z, y)
    near, far = gp.predict(Z), gp.predict(np.full((5, 3), 6.0))
    miss = float(np.sqrt(np.mean((near.mean - y) ** 2)) / y.std())
    cl.record(miss < 0.02, "Known answer: with noise-free data the Gaussian process passes (almost) exactly through the training points (error under 2% of the spread)", f"{miss:.4f}")
    width_near, width_far = float(np.mean(near.hi - near.lo)), float(np.mean(far.hi - far.lo))
    cl.record(width_far > 5 * width_near, "Known answer: the Gaussian process's 90% range is much wider far from the training data than at the training points", f"{width_near:.3f} near, {width_far:.3f} far")
    # conformal ranges on exchangeable data should hit about 90%
    n = 4000
    Xc = rng.uniform(0, 1, (n, 3))
    yc = np.sin(3 * Xc[:, 0]) + Xc[:, 1] + rng.normal(0, 0.3, n)
    kept_apart = np.arange(2000) % 4 == 0
    p = GradientBoostingConformal(FAST).fit(Xc[:2000], yc[:2000], kept_apart).predict(Xc[2000:])
    hit = float(np.mean((yc[2000:] >= p.lo) & (yc[2000:] <= p.hi)))
    cl.record(0.87 <= hit <= 0.93, "Known answer: the conformal 90% range contains the truth about 90% of the time on fresh data from the same source", f"{hit:.3f}")


def fold_pipeline_checks(cl: Checklist) -> None:
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.validate import _run_task, build_tasks, run_validation
    from cellpoc.modelling import make_fold_plans

    table = build_table_for_setup(fixture_setup("mock_small"), None, PROJECT_ROOT, "mock_small")
    usable = ["dissolution_30min_pct", "hardness_kp"]
    plans = {r: make_fold_plans(table, r) for r in usable}
    tasks, where = build_tasks(table, FAST, usable, plans, ["batch"], None)
    single = next(t for t in tasks if not t["joint"])
    joint = next(t for t in tasks if t["joint"])
    changed = []
    for task in (single, joint):
        altered = dict(task)
        frame = task["frame"].copy()
        for result, test in task["tests"].items():
            frame.loc[frame.index[test], result] = frame.loc[frame.index[test], result] + 1000.0       # the test answers are destroyed
        altered["frame"] = frame
        a, b = _run_task(task), _run_task(altered)
        for result in a:
            for key in a[result].preds:
                same = all(np.allclose(getattr(a[result].preds[key], f), getattr(b[result].preds[key], f), equal_nan=True) for f in ("mean", "lo", "hi"))
                if not same:
                    changed.append(f"{result}/{key}")
    n_models = sum(len(r.preds) for r in _run_task(single).values()) + sum(len(r.preds) for r in _run_task(joint).values())
    cl.record(not changed and n_models >= 9, "Leakage self-test: destroying the test answers (adding 1,000 to every held-out value) changes no model's prediction, so no model uses the answers it is tested on "
                                              f"({n_models} model predictions compared, joint model included)", ", ".join(changed[:4]))
    again = _run_task(single)
    first = _run_task(single)
    cl.record(all(np.array_equal(again[r].preds[k].mean, first[r].preds[k].mean, equal_nan=True) for r in first for k in first[r].preds),
              "Reproducible: the same fold gives exactly the same predictions every time", "")
    one = run_validation(table, FAST, kinds=["batch", "supplier"], n_jobs=1)
    two = run_validation(table, FAST, kinds=["batch", "supplier"], n_jobs=2)
    same = all(np.allclose(f1.preds[k].mean, f2.preds[k].mean, equal_nan=True) for key in one.runs for f1, f2 in zip(one.runs[key].folds, two.runs[key].folds) for k in f1.preds) \
        and {k: len(v.folds) for k, v in one.runs.items()} == {k: len(v.folds) for k, v in two.runs.items()}
    cl.record(same, "The answers do not depend on how many folds run at the same time (one at a time and two at a time give identical predictions)", "")


def resume_checks(cl: Checklist) -> None:
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.validate import run_validation

    table = build_table_for_setup(fixture_setup("mock_small"), None, PROJECT_ROOT, "mock_small")
    with tempfile.TemporaryDirectory() as folder:
        saved = Path(folder)
        first = run_validation(table, FAST, kinds=["batch"], n_jobs=2, cache=saved)
        files = sorted(saved.glob("*.pkl"))
        again = run_validation(table, FAST, kinds=["batch"], n_jobs=1, cache=saved)
        for f in files[:3]:                                  # a run that was stopped part-way: three folds are missing
            f.unlink()
        files[3].write_bytes(b"damaged")                     # and one saved file is damaged
        resumed = run_validation(table, FAST, kinds=["batch"], n_jobs=1, cache=saved)

        def same(a, b):
            return all(np.allclose(x.preds[k].mean, y.preds[k].mean, equal_nan=True) for key in a.runs for x, y in zip(a.runs[key].folds, b.runs[key].folds) for k in x.preds) \
                and {k: len(v.folds) for k, v in a.runs.items()} == {k: len(v.folds) for k, v in b.runs.items()}
        refilled = len(list(saved.glob("*.pkl")))
    cl.record(len(files) > 5 and same(first, again) and same(first, resumed) and refilled == len(files),
              f"A run that is stopped can be resumed: {len(files)} saved fold answers are reused, three deleted and one damaged file are recomputed, and the results are identical to an uninterrupted run",
              f"{refilled} of {len(files)} files present afterwards")


_SHARED: dict = {}


def shared_runs(tables: dict) -> dict:
    """The fast-mode runs on the real tables that the report checks and the summary checks both read: worked out once (a restricted slice of each table keeps the check short)."""
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.validate import run_validation

    if not _SHARED:
        _SHARED["batch"] = run_validation(tables["batch_production"], FAST, kinds=["supplier"], results=["dissolution_av", "tbl_av_hardness", "tbl_tensile", "batch_yield"], n_jobs=1)
        _SHARED["extended"] = run_validation(tables["batch_production_extended"], FAST, kinds=["supplier"], results=["dissolution_av"], n_jobs=1)
        _SHARED["literature"] = run_validation(tables["literature"], FAST, kinds=["api"], results=["hardness_kp"], n_jobs=1)
    return _SHARED


def summary_checks(cl: Checklist, tables: dict) -> None:
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.summary import build_summary
    from cellpoc.modelling.validate import run_validation

    if "batch_production" not in tables:
        cl.skip("The summary report keeps its three parts apart and labelled", "the real public data is not on this computer")
        return
    shared = shared_runs(tables)
    runs = [run_validation(tables["mock_small"], FAST, kinds=["batch"], n_jobs=1), shared["batch"], shared["extended"], shared["literature"]]
    text = build_summary(runs, "fast")
    a = text[text.index("## Part A"):text.index("## Part B")]
    b = text[text.index("## Part B"):text.index("## Part C")]
    c = text[text.index("## Part C"):text.index("## Results that are not independent")]
    ok_a = "### mock_small [SYNTHETIC DATA]" in a and "### batch_production [REAL PUBLIC DATA, NOT CLIENT DATA]" in a and "EXPLORATORY" not in a and "ROBUSTNESS" not in a and "CHOSEN" in a
    ok_b = "batch_production_extended" in b and "CHOSEN" not in b and all(tables["batch_production_extended"].tag in line for line in b.splitlines() if line.startswith("###"))
    ok_c = "literature" in c and "CHOSEN" not in c and all(tables["literature"].tag in line for line in c.splitlines() if line.startswith("###"))
    cl.record(ok_a and ok_b and ok_c, "The summary keeps three parts apart: the main comparisons (the only ones a model is chosen from), the exploratory comparison and the robustness-only table; "
                                      "the last two carry their labels in every table heading and choose nothing", f"A {ok_a}, B {ok_b}, C {ok_c}")
    named = [line for line in text.splitlines() if "api_code" in line]
    cl.record(bool(named) and all(PROXY_PHRASE in line for line in named) and "only the joint Gaussian process is fitted jointly across results" in text and "Every other model" in text,
              "Summary: every line that names api_code says 'proxy, not a confirmed supplier', and the joint-versus-independent limitation is stated", f"{len(named)} lines name api_code")
    dependent = text[text.index("## Results that are not independent"):text.index("## What was left out")]
    cl.record("`tbl_tensile` is calculated from `tbl_av_hardness`" in dependent and "correlate at 0.95" in dependent and "never be presented as independent findings" in dependent,
              "Summary: results that are not independent findings are named (tensile strength is calculated from hardness; tablet yield and batch yield correlate at 0.95 and only batch yield is modelled)", "")


def fresh_truth_checks(cl: Checklist) -> None:
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.validate import run_validation

    with tempfile.TemporaryDirectory() as folder:
        out, truth = Path(folder) / "fresh.csv", Path(folder) / "truth.csv"
        done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "make_mock_data.py"), "--n", "900", "--seed", "8201", "--difficulty", "easy", "--out", str(out), "--truth", str(truth)],
                              capture_output=True, text=True, cwd=folder)
        if done.returncode != 0:
            cl.record(False, "Fresh mock data (new seed, with the generator's true values): the generator ran", done.stderr[-120:])
            return
        setup = fixture_setup("mock_easy")
        table = build_table(setup, clean_table(read_table(out, ReadOptions.from_setup(setup)), setup), None, "fresh easy (seed 8201)")
        true = pd.read_csv(truth).drop_duplicates("experiment_id").set_index("experiment_id")
        validation = run_validation(table, FAST, kinds=["supplier"], results=["dissolution_30min_pct", "hardness_kp"], n_jobs=1)
        ids = table.frame["experiment_id"].to_numpy()
        losers, shown = [], []
        for (result, _), run in validation.runs.items():
            column = {"dissolution_30min_pct": "_true_diss", "hardness_kp": "_true_hard"}[result]
            error = {}
            for key in ("mean", "quadratic", "boosting", "forest", "ensemble", "gp", "gp_joint"):
                sq = [(true.loc[ids[f.test], column].to_numpy() - f.preds[key].mean) ** 2 for f in run.folds if key in f.preds]
                error[key] = float(np.sqrt(np.concatenate(sq).mean())) if sq else float("nan")
            losers += [f"{result}/{k}" for k in error if k != "mean" and not error[k] < 0.9 * error["mean"]]
            shown.append(f"{result}: mean {error['mean']:.2f}, best {min(v for k, v in error.items() if k != 'mean'):.2f}")
    cl.record(not losers, "Fresh mock data (new seed, never used to choose anything), scored against the generator's TRUE values with whole suppliers held out: every candidate model "
                          "beats the training-mean baseline by at least 10%", "; ".join(losers) or "; ".join(shown))


def report_checks(cl: Checklist, tables: dict) -> None:
    from cellpoc.modelling.models import FAST
    from cellpoc.modelling.report import build_report
    from cellpoc.modelling.validate import build_with_flags_removed, run_validation

    small = tables["mock_small"]
    text = build_report(run_validation(small, FAST, n_jobs=1))
    blocks = text.split("**Result: ")[1:]
    rows = [line for block in blocks for line in block.splitlines() if line.startswith("| ") and "---" not in line and "Model |" not in line]
    cl.record(bool(blocks) and all("Baseline: predict the training mean" in b and "Baseline: nearest-neighbour lookup" in b for b in blocks),
              f"Every results table in the report (all {len(blocks)}) lists both naive baselines beside the candidates", "")
    joint_rows = [r for r in rows if "Gaussian process, joint across results" in r]
    cl.record(bool(rows) and all(("jointly across results" in r) == ("joint across results" in r) and ("independently, one model per result" in r or "jointly across results" in r) for r in rows) and joint_rows,
              f"Every model row of every table in the report ({len(rows)}) says whether it was fitted jointly across results or independently per result; only the joint Gaussian process says 'jointly'", "")
    cl.record("fitted **jointly across results**" in text and "**Every other model, including the ordinary Gaussian process, is fitted independently, one model per result,**" in text
              and text.startswith("# Model comparison, FAST MODE [SYNTHETIC DATA]: mock_small") and "No model was tuned" in text,
              "The report states the joint-versus-independent limitation in words, opens with the data-status label and says it is fast mode", "")
    cl.record(small.tag == "" and "No model is chosen" not in text and "## Which model would be chosen" in text,
              "A main comparison reports which model the rule would choose", "")
    # the real tables: restricted runs, so the labels and the proxy wording can be checked on the actual reports
    if "batch_production" in tables:
        batch, extended, lit = tables["batch_production"], tables["batch_production_extended"], tables["literature"]
        shared = shared_runs(tables)
        reports = {"batch": build_report(shared["batch"]), "extended": build_report(shared["extended"]), "literature": build_report(shared["literature"])}
        named = [line for line in reports["batch"].splitlines() if "api_code" in line]
        cl.record(bool(named) and all(PROXY_PHRASE in line for line in named) and any(line.startswith("## Hold-out: whole suppliers") and PROXY_PHRASE in line for line in named),
                  "Real batch data: every line of the model report that names api_code also says 'proxy, not a confirmed supplier', including the hold-out heading", f"{len(named)} lines name api_code")
        for name, key in (("extended batch comparison", "extended"), ("literature table", "literature")):
            table = extended if key == "extended" else lit
            headings = [line for line in reports[key].splitlines() if line.startswith("#")]
            cl.record(all(table.tag in line for line in headings) and "No model is chosen" in reports[key] and "Which model would be chosen" in reports[key],
                      f"The {name} carries its label in EVERY heading of its model report ({table.tag[:60]}...) and no model is chosen from it", f"{len(headings)} headings")
        cl.record(all(tables["batch_production"].tag == "" for _ in [0]) and "No model is chosen" not in reports["batch"],
                  "The main batch comparison carries no exploratory label and is the one that is judged", "")
        without = build_with_flags_removed(lit)
        flagged = int(lit.frame["mass_balance_flag"].sum())
        cl.record(all(len(without.responses[r].rows) == len(lit.responses[r].rows) - flagged for r in lit.responses),
                  f"Literature table: the 'without the flagged rows' version leaves out exactly the {flagged} flagged rows from every result and nothing else", "")
    else:
        cl.skip("The real tables' model reports (labels, proxy wording, flagged rows)", "the real public data is not on this computer")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 3a: preparing tables for modelling (the modelling table, the leakage rules and the labels every report carries)")
    before = project_files()
    results = modelling_cases.run_all()
    message_checks(cl, results)
    setup_section_checks(cl)
    tables = {}
    for name in NAMES:
        if fixture_available(name):
            tables[name] = build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name)
    table_checks(cl, tables)
    fresh_mock_checks(cl)
    leakage_checks(cl, tables)
    composition_checks(cl, tables)
    proxy_checks(cl, tables)
    honesty_checks(cl)
    split_checks(cl, tables)
    group_count_checks(cl, tables)
    fold_shape_checks(cl, tables)
    selection_checks(cl)
    regression_checks(cl)
    inner_fold_checks(cl, tables)
    synthetic_model_checks(cl)
    fold_pipeline_checks(cl)
    resume_checks(cl)
    fresh_truth_checks(cl)
    report_checks(cl, tables)
    summary_checks(cl, tables)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project (the modelling part and its tests leave no files behind)", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
