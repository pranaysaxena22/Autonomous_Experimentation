"""Health check for Stage 3b-1 (calibration): is the uncertainty a model states honest, and which results are strong enough to be calibrated at all.

In plain words it checks that: the carry-forward rule puts every result in the right one of three statuses at its exact lines (carried up to 0.70 of the spread,
carried-but-exploratory up to 0.80, skipped beyond, or when no model beats both baselines, or the table is exploratory or robustness-only, or too small); the hit-rate arithmetic
and the verdict give the right answer on made-up errors where the truth is known (exactly bell-shaped errors at the stated 90% are called honest; ranges halved are called
over-confident and recalibration restores about 90% on fresh data; ranges doubled are called under-confident); the recalibration scale factor of a fold is computed ENTIRELY from other
folds (artificially inflating one fold's errors leaves that fold's factor exactly unchanged, and for hold-outs forward in time a later step can never change an earlier one); error bars are
reproducible; a range that is the same for every recipe is reported as unable to say when it is unsure; and, on the saved Stage 3a full-comparison answers, the three statuses are kept in
separate sections of the reports with their own labels, skipped results get no calibration number, and every line naming api_code says 'proxy, not a confirmed supplier'.
Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import PROXY_PHRASE, build_table_for_setup  # noqa: E402
from cellpoc.modelling.calibration import Pool, calibrate, calibrate_kind, scale_factor, verdict  # noqa: E402
from cellpoc.modelling.calibration_report import build_report, build_summary  # noqa: E402
from cellpoc.modelling.carry import BORDERLINE, CARRIED, SKIPPED, STATUS_WORDS, decide, decide_all  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from checks import architecture, modelling_cases  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

CACHE = ROOT / "runs" / "modelling" / "cache_full"
BASE = {"mean": 1.0, "nearest": 1.2}
fake = modelling_cases.fake_validation


# ---------------------------------------------------------------- the carry-forward rule
def carry_rule_checks(cl: Checklist) -> None:
    def status(errors, **kw):
        return decide(fake({"batch": {**BASE, **errors}}, **kw), "y")

    cases = [("carried at 0.699", status({"quadratic": 0.699}).status, CARRIED), ("borderline at 0.701", status({"quadratic": 0.701}).status, BORDERLINE),
             ("borderline at 0.799", status({"quadratic": 0.799}).status, BORDERLINE), ("skipped at 0.801", status({"quadratic": 0.801}).status, SKIPPED),
             ("skipped when no model beats the baselines", status({"quadratic": 1.1}).status, SKIPPED),
             ("skipped when it beats the mean but not the nearest-neighbour lookup", decide(fake({"batch": {"mean": 1.0, "nearest": 0.4, "quadratic": 0.5}}), "y").status, SKIPPED),
             ("skipped with 60 rows", status({"quadratic": 0.4}, n_rows=60).status, SKIPPED),
             ("skipped for an exploratory table", status({"quadratic": 0.4}, setup=modelling_cases.tiny_setup(groups={"batch": {"column": "batch_id"}}, exploratory="a smaller sample")).status, SKIPPED)]
    wrong = [f"{name}: got {got}" for name, got, want in cases if got != want]
    cl.record(not wrong, "Carry rule: carried up to 0.70 of the spread, carried-but-exploratory up to 0.80, skipped beyond; also skipped when no model beats BOTH baselines, with 60 rows, or for an exploratory table",
              "; ".join(wrong) or ", ".join(name for name, _, _ in cases[:4]))
    tie = decide(fake({"batch": {**BASE, "quadratic": 0.50, "boosting": 0.48, "forest": 0.60}}), "y")
    cl.record(tie.status == CARRIED and tie.models == ["quadratic", "boosting"] and tie.chosen == "quadratic" and tie.worst is not None and abs(tie.worst - 0.48) < 1e-9,
              "Carry rule: the rule's choice is carried first, then every model within its 5% tie (and not a model outside it); the line is judged on the best model's score (0.48), not the tie-preferred one's",
              f"models {tie.models}, judged on {tie.worst}")
    words = list(STATUS_WORDS.values())
    cl.record(len(set(words)) == 3 and all(w for w in words) and "EXPLORATORY" not in STATUS_WORDS[CARRIED] and "EXPLORATORY" in STATUS_WORDS[BORDERLINE].upper(),
              "The three statuses have three different names (carried, carried but exploratory, not assessed), so none can be mistaken for another", "; ".join(words))


# ---------------------------------------------------------------- hit rates, verdicts and recalibration on made-up errors with a known answer
def pool_of(rng, ranges: float, folds: int = 4, rows: int = 2000, spread_by_fold: list | None = None) -> Pool:
    """Normal errors with spread 1, and a stated 90% half-width of `ranges` (1.645 is exactly honest)."""
    parts = []
    for f in range(1, folds + 1):
        e = np.abs(rng.normal(0, 1 if spread_by_fold is None else spread_by_fold[f - 1], rows))
        parts.append((np.full(rows, f), e, np.full(rows, ranges), np.array([f"g{f}-{i % 25}" for i in range(rows)])))
    fold, err, half, group = (np.concatenate([p[i] for p in parts]) for i in range(4))
    return Pool(err / half, half, fold, group, err)


def calibration_checks(cl: Checklist) -> None:
    rng = np.random.default_rng(11)
    honest = calibrate_kind(pool_of(rng, 1.645), "batch", "whole batches (x)", 1.0)
    narrow = calibrate_kind(pool_of(rng, 0.8225), "batch", "whole batches (x)", 1.0)
    wide = calibrate_kind(pool_of(rng, 3.29), "batch", "whole batches (x)", 1.0)
    cl.record(abs(honest.hit - 0.90) < 0.02 and verdict([honest.hit]) == "honest" and honest.ci is not None and honest.ci[0] <= honest.hit <= honest.ci[1],
              "Known answer: exactly bell-shaped errors with a stated 90% range hit 0.90 (within 0.02) and are called honest, with an error bar around the hit rate", f"hit {honest.hit:.3f}, error bar {honest.ci}")
    cl.record(narrow.hit < 0.70 and verdict([narrow.hit]) == "over-confident" and abs(narrow.recal_hit - 0.90) < 0.03,
              "Known answer: ranges that are half as wide as they should be are called over-confident, and recalibration restores about 90% (within 0.03) on the held-out folds", f"{narrow.hit:.3f} then {narrow.recal_hit:.3f}")
    cl.record(wide.hit > 0.97 and verdict([wide.hit]) == "under-confident" and abs(wide.recal_hit - 0.90) < 0.03,
              "Known answer: ranges twice as wide as they should be are called under-confident, and recalibration restores about 90%", f"{wide.hit:.3f} then {wide.recal_hit:.3f}")
    edges = [verdict([0.85]), verdict([0.95]), verdict([0.849]), verdict([0.951]), verdict([0.80, 0.97]), verdict([0.90, 0.80])]
    cl.record(edges == ["honest", "honest", "over-confident", "under-confident", "inconsistent", "over-confident"],
              "Verdict rule: honest only if every hold-out type is within 0.85 to 0.95 (edges included); below in any is over-confident; above is under-confident; both is inconsistent", str(edges))
    again = calibrate_kind(pool_of(np.random.default_rng(11), 1.645), "batch", "x", 1.0)
    few = calibrate_kind(Pool(*(a[:0] for a in (np.array([0.5]),) * 5)), "batch", "x", 1.0) if False else None
    p = pool_of(rng, 1.645, folds=3)
    p.group = np.array([f"g{i % 4}" for i in range(len(p.u))])
    cl.record(again.ci == honest.ci and calibrate_kind(p, "supplier", "x", 1.0).ci is None,
              "Error bars are reproducible (the same data always gives the same bar) and are not given when there are fewer than 10 groups", "")


def guard_checks(cl: Checklist) -> None:
    rng = np.random.default_rng(5)
    folds = {f: np.abs(rng.normal(0, 1, 400)) / 1.645 for f in range(1, 6)}
    # a fold's factor is computed entirely from OTHER folds: inflating its own errors changes nothing
    before = {f: scale_factor(folds, f) for f in folds}
    inflated = dict(folds)
    inflated[3] = folds[3] * 50                                           # one fold's errors made 50 times larger
    after = {f: scale_factor(inflated, f) for f in folds}
    cl.record(after[3] == before[3] and all(after[f] != before[f] for f in folds if f != 3),
              "Recalibration guard: artificially inflating one fold's errors leaves THAT fold's scale factor exactly unchanged, while every other fold's factor does change (so the test can see a difference)",
              f"fold 3 factor {before[3]:.4f} before, {after[3]:.4f} after; the others moved")
    poisoned = dict(folds)
    poisoned[2] = np.array([np.nan, np.inf, -1.0])                        # garbage in the fold's own entry cannot matter if it is never read
    cl.record(scale_factor(poisoned, 2) == before[2], "Recalibration guard: the fold's own entry is never read at all (replacing it with garbage gives the identical factor)", "")
    # forward in time: only EARLIER steps count
    fwd_before = {f: scale_factor(folds, f, forward=True) for f in folds}
    later = dict(folds)
    later[5] = folds[5] * 50
    fwd_later = {f: scale_factor(later, f, forward=True) for f in folds}
    earlier = dict(folds)
    earlier[1] = folds[1] * 50
    fwd_earlier = {f: scale_factor(earlier, f, forward=True) for f in folds}
    cl.record(all(fwd_later[f] == fwd_before[f] for f in (1, 2, 3, 4)) and fwd_before[1] is None and all(fwd_earlier[f] != fwd_before[f] for f in (2, 3, 4, 5)) and fwd_later[1] is None,
              "Recalibration guard, forward in time: a LATER step can never change an earlier step's factor (the last step inflated: steps 1 to 4 unchanged), the first step has no factor, and an earlier step does change later ones",
              f"first step: {fwd_before[1]}")
    # the same guard, end to end through the real calibration on made-up held-out results
    v1 = fake({"batch": {**BASE, "quadratic": 0.5}}, folds=5)
    v2 = fake({"batch": {**BASE, "quadratic": 0.5}}, folds=5)
    run2 = v2.runs[("y", "batch")]
    target = run2.folds[2]
    target.y = target.y + 1000.0                                          # that fold's held-out answers destroyed: its errors become enormous
    c1, c2 = calibrate(v1, "y", "quadratic", "chosen").kinds["batch"], calibrate(v2, "y", "quadratic", "chosen").kinds["batch"]
    cl.record(c1.factors[2] == c2.factors[2] and all(a != b for i, (a, b) in enumerate(zip(c1.factors, c2.factors)) if i != 2),
              "Recalibration guard, end to end: destroying one fold's held-out answers in the full calibration leaves that fold's factor identical and changes every other fold's", f"{c1.factors[2]} vs {c2.factors[2]}")


def unsure_checks(cl: Checklist) -> None:
    rng = np.random.default_rng(8)
    n = 600

    def pool(width_per_fold, error_scale_by_width: bool) -> Pool:
        parts = []
        for f, w in enumerate(width_per_fold, 1):
            half = np.full(n, w) if np.isscalar(w) else w
            err = np.abs(rng.normal(0, 1, n)) * (half if error_scale_by_width else 1.0)
            parts.append((np.full(n, f), err, half, np.array([f"g{f}-{i % 20}" for i in range(n)])))
        fold, err, half, group = (np.concatenate([p[i] for p in parts]) for i in range(4))
        return Pool(err / half, half, fold, group, err)

    informative = calibrate_kind(pool([rng.uniform(0.5, 2.0, n), rng.uniform(0.5, 2.0, n), rng.uniform(0.5, 2.0, n)], True), "batch", "x", 1.0)
    uninformative = calibrate_kind(pool([rng.uniform(0.5, 2.0, n), rng.uniform(0.5, 2.0, n), rng.uniform(0.5, 2.0, n)], False), "batch", "x", 1.0)
    # a model that states ONE fixed range per fold, a different one in each fold: across folds the width and the error can line up by accident, within a fold it says nothing
    constant = calibrate_kind(pool([0.8, 1.6, 3.2], True), "batch", "x", 1.0)
    # (errors built as |bell-shaped noise| times the stated range have a true rank correlation with it of about 0.38, so 0.25 is the line between informative and not)
    cl.record(informative.spearman is not None and informative.spearman > 0.25 and uninformative.spearman is not None and abs(uninformative.spearman) < 0.15 and constant.spearman is None,
              "Knows-when-it-is-unsure: wider ranges that really go with bigger errors score high, ranges unrelated to the errors score near zero, and a fixed range per fold is reported as unable to say "
              "(not credited with a correlation that only comes from folds differing from each other)", f"{informative.spearman}, {uninformative.spearman}, {constant.spearman}")


# ---------------------------------------------------------------- the real tables, from the saved Stage 3a answers
def real_checks(cl: Checklist) -> None:
    files = len(list(CACHE.glob("*.pkl"))) if CACHE.exists() else 0
    if files < 280 or not all(fixture_available(n) for n in NAMES):
        cl.skip("Calibration on the saved Stage 3a full-comparison answers", "they (or the real public data) are not on this computer: double-click run_full_validation.bat first")
        return
    validations = []
    for name in NAMES:
        table = build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name)
        validations.append(run_validation(table, FULL, n_jobs=1, cache=CACHE, save=False))
    decisions = decide_all(validations)
    got = {s: sorted(f"{d.table}/{d.result}" for d in decisions if d.status == s) for s in (CARRIED, BORDERLINE, SKIPPED)}
    want_carried = sorted(["mock_easy/dissolution_30min_pct", "mock_easy/hardness_kp", "mock_easy/friability_pct", "mock_hard/hardness_kp", "mock_hard/friability_pct",
                           "batch_production/tbl_av_hardness", "batch_production/tbl_tensile"])
    want_borderline = ["mock_hard/dissolution_30min_pct"]
    skipped_ok = all(x in got[SKIPPED] for x in ["batch_production/dissolution_av", "batch_production/batch_yield"]) \
        and all(any(s.startswith(t) for s in got[SKIPPED]) for t in ("literature/", "batch_production_extended/", "mock_small/"))
    pairs = sum(len(d.models) for d in decisions if d.status == CARRIED)
    cl.record(got[CARRIED] == want_carried and got[BORDERLINE] == want_borderline and skipped_ok and pairs == 22 and sum(len(d.models) for d in decisions if d.status == BORDERLINE) == 5,
              "On the real Stage 3a answers the carry rule gives exactly the list the project owner was shown: carried: easy mock dissolution, hardness, friability; hard mock hardness, friability; real batch hardness and "
              "tensile strength (22 model-and-result pairs); carried but exploratory: hard mock dissolution (5 pairs); skipped: batch dissolution and yield, all of the literature table, the extended batch comparison, the small mock",
              f"carried {len(got[CARRIED])}, borderline {len(got[BORDERLINE])}, skipped {len(got[SKIPPED])}, pairs {pairs}")
    text = build_summary(validations)
    a = text[text.index("## Part A"):text.index("## Part B")]
    b = text[text.index("## Part B"):text.index("## Part C")]
    c = text[text.index("## Part C"):]
    heads_b = [line for line in b.splitlines() if line.startswith("###")]
    cl.record("mock_hard" in b and "dissolution_30min_pct" in b and "EXPLORATORY: borderline" not in a and all("EXPLORATORY: borderline" in h for h in heads_b) and bool(heads_b)
              and "dissolution_30min_pct" not in "".join(line for line in a.splitlines() if "mock_hard" in line and line.startswith("###")),
              "The carried-but-exploratory result sits ONLY in its own part, with its label in its heading, and never among the carried results", f"{len(heads_b)} borderline heading(s)")
    skipped_headings = [line for line in (a + b).splitlines() if line.startswith("###") and any(x in line for x in ("dissolution_av", "batch_yield", "literature", "mock_small", "extended"))]
    skipped_listed = all(x in c for x in ("dissolution_av", "batch_yield", "literature", "mock_small", "batch_production_extended"))
    cl.record(not skipped_headings and skipped_listed and c.count("Calibration not assessed") == sum(d.status == SKIPPED for d in decisions),
              "Every skipped result is listed as 'Calibration not assessed' with its reason, and none has a calibration table (batch dissolution and yield, the literature table, the extended comparison, the small mock)",
              f"{c.count('Calibration not assessed')} listed")
    named = [line for line in text.splitlines() if "api_code" in line]
    per_table = {d.table: build_report(v) for v in validations for d in [decide(v, next(iter(v.table.responses)))]}
    named += [line for t in per_table.values() for line in t.splitlines() if "api_code" in line]
    cl.record(bool(named) and all(PROXY_PHRASE in line for line in named), "Every line of every calibration report that names api_code says 'proxy, not a confirmed supplier'", f"{len(named)} lines")
    every_heading = all(all(v.table.tag in line for line in per_table[v.table.name].splitlines() if line.startswith("#")) for v in validations if v.table.tag)
    cl.record(every_heading, "Exploratory and robustness-only tables carry their label in EVERY heading of their calibration report", "")
    # facts the project owner can check against the Stage 3a tables
    easy = next(v for v in validations if v.table.name == "mock_easy")
    nn = calibrate(easy, "friability_pct", "ensemble", "chosen")
    batch = next(v for v in validations if v.table.name == "batch_production")
    forest = calibrate(batch, "tbl_av_hardness", "forest", "chosen")
    cl.record(nn.verdict == "over-confident" and all(k.hit < 0.5 for k in nn.kinds.values()) and nn.verdict_after == "honest" and forest.verdict == "honest",
              "Consistent with the Stage 3a tables: the neural-network ensemble's ranges on easy-mock friability (the rule's choice there) are over-confident (hit rates under 0.5) and recalibration makes them honest; "
              "the random forest's ranges on real batch hardness are honest as stated",
              f"ensemble {nn.verdict} then {nn.verdict_after}; forest {forest.verdict}")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 3b-1: calibration (is the uncertainty a model states honest?) and the carry-forward rule")
    before = project_files()
    carry_rule_checks(cl)
    calibration_checks(cl)
    guard_checks(cl)
    unsure_checks(cl)
    real_checks(cl)
    found = forbidden_in(sorted((ROOT / "cellpoc" / "modelling").glob("*.py")))
    cl.record(not found, "The modelling code, including the calibration code, contains no random splitter or sampler (the error bars resample whole held-out groups only to measure a hit rate; they never divide data for fitting)", "; ".join(found[:3]))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
