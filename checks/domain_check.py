"""Health check for Stage 3b-2 (the applicability-domain warning): does it warn when a recipe is far from the data, and is its own threshold steady?

In plain words it checks, on made-up data where the truth is known, that: about 5% of rows from the same source as the training data are warned; recipes pushed 8 standard
deviations away are warned essentially always; warned rows have larger errors when errors really grow with distance, and the ratio is about 1 when they do not (a negative control);
the threshold is computed from the training rows alone (changing the held-out rows leaves it identical, changing a training row changes it) and equals a slow brute-force
calculation that leaves out each row's own group; the range check ignores an excursion inside the 10% tolerance and catches one beyond it; an unseen category is always warned; and
the steadiness criterion classifies a list of thresholds as stable, varying or swinging at its exact lines. On the saved Stage 3a answers it checks that every carried result gets a warning
evaluation in all its hold-out types with deliberately far-away recipes warned, that the distance threshold is steady across folds next to how much the recalibration factors swung,
and that the reports keep the three statuses apart, carry every label, give the safeguard message, evaluate nothing that was skipped and say 'proxy, not a confirmed supplier' on every line
that names api_code. Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import PROXY_PHRASE, build_table_for_setup  # noqa: E402
from cellpoc.modelling.calibration import calibrate  # noqa: E402
from cellpoc.modelling.carry import BORDERLINE, CARRIED, SKIPPED, decide_all  # noqa: E402
from cellpoc.modelling.domain import (K_NEIGHBOURS, MIN_REFERENCE_ROWS, QUANTILE, RANGE_TOLERANCE, component, fit_reference, stability, threshold_swing, warn)  # noqa: E402
from cellpoc.modelling.domain_report import SAFEGUARD, _basis, build_report, build_summary
from cellpoc.modelling.group_domain import (GroupResult, GroupWarning, KindGroups, MIN_GROUP_ROWS, check_group, evaluate_groups, fit_group_reference, null_threshold)  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

CACHE = ROOT / "runs" / "modelling" / "cache_full"
COLUMNS = ["x1", "x2", "x3", "x4"]


def synth(rng, groups: int = 100, per: int = 30) -> tuple[pd.DataFrame, np.ndarray]:
    frame = pd.DataFrame(rng.normal(size=(groups * per, 4)), columns=COLUMNS)
    return frame, np.repeat(np.arange(groups), per).astype(str)


def reference_of(frame, labels, train):
    return fit_reference(frame, COLUMNS, [], train, labels[train])


def proof_checks(cl: Checklist) -> None:
    shares, far, thresholds = [], [], []
    for seed in range(5):
        rng = np.random.default_rng(100 + seed)
        frame, labels = synth(rng)
        train, test = np.flatnonzero(np.isin(labels, [str(i) for i in range(80)])), np.flatnonzero(~np.isin(labels, [str(i) for i in range(80)]))
        ref = reference_of(frame, labels, train)
        shares.append(float(warn(ref, frame, test).by_distance.mean()))
        far.append(float(warn(ref, frame, test, far=True).by_distance.mean()))
        thresholds.append(ref.threshold)
    cl.record(0.035 <= np.mean(shares) <= 0.07,
              f"Proof: for held-out groups from the same source as the training data, about {100 * (1 - QUANTILE):.0f}% of rows are warned by distance (average of five made-up tables: {100 * np.mean(shares):.1f}%, each between "
              f"{100 * min(shares):.1f}% and {100 * max(shares):.1f}%)", "")
    cl.record(min(far) >= 0.99, "Proof: recipes pushed 8 standard deviations away on every numeric input are warned by distance (at least 99% of them, on every made-up table)", f"lowest {100 * min(far):.1f}%")
    # does a warned row really have a bigger error? (the warned/unwarned comparison, on errors we build to be related or unrelated to distance)
    rng = np.random.default_rng(7)
    n = 20000
    distance = np.abs(rng.normal(size=n)) + 1.0
    flag = distance > np.quantile(distance, 0.95)
    related = distance * np.abs(rng.normal(1.0, 0.3, n))
    unrelated = np.abs(rng.normal(1.0, 0.3, n)) * 2.0
    c_related = component(flag, related, related >= np.quantile(related, 0.9))
    c_unrelated = component(flag, unrelated, unrelated >= np.quantile(unrelated, 0.9))
    cl.record(c_related.error_ratio > 1.5 and c_related.lift > 1.5 and c_unrelated.error_ratio is not None and 0.8 < c_unrelated.error_ratio < 1.25 and 0.6 < c_unrelated.lift < 1.5,
              "Proof: warned rows have clearly larger errors when errors really grow with distance (error ratio and lift above 1.5), and about the same when they do not (negative control: ratio and lift near 1)",
              f"related: ratio {c_related.error_ratio:.2f}, lift {c_related.lift:.2f}; unrelated: ratio {c_unrelated.error_ratio:.2f}, lift {c_unrelated.lift:.2f}")


def guard_checks(cl: Checklist) -> None:
    rng = np.random.default_rng(21)
    frame, labels = synth(rng, groups=40, per=20)
    train = np.flatnonzero(np.isin(labels, [str(i) for i in range(32)]))
    test = np.setdiff1d(np.arange(len(frame)), train)
    base = reference_of(frame, labels, train).threshold
    destroyed = frame.copy()
    destroyed.iloc[test] = destroyed.iloc[test] * 1000 + 50                       # the held-out rows are changed beyond recognition
    changed_train = frame.copy()
    changed_train.iloc[train[:40]] = changed_train.iloc[train[:40]] * 30          # some training rows are changed
    cl.record(reference_of(destroyed, labels, train).threshold == base and reference_of(changed_train, labels, train).threshold != base,
              "Guard: the threshold is computed from the training rows alone: changing the held-out rows beyond recognition leaves it exactly identical, changing training rows changes it", f"{base:.4f}")
    # a slow brute-force calculation that leaves out each row's own group
    small, names = synth(np.random.default_rng(3), groups=6, per=10)
    ids = np.arange(len(small))
    values = small[COLUMNS].to_numpy()
    mine = []
    for i in ids:
        other = names != names[i]
        d = np.sort(np.sqrt(((values[other] - values[i]) ** 2).sum(axis=1)))
        mine.append(d[:K_NEIGHBOURS].mean())
    # the warning measures in the standardised space the models use, so standardise the same way for the comparison
    standard = (values - values.mean(axis=0)) / np.where(values.std(axis=0) > 0, values.std(axis=0), 1.0)
    brute = []
    for i in ids:
        other = names != names[i]
        d = np.sort(np.sqrt(((standard[other] - standard[i]) ** 2).sum(axis=1)))
        brute.append(d[:K_NEIGHBOURS].mean())
    reference = fit_reference(small, COLUMNS, [], ids, names)
    cl.record(len(small) >= MIN_REFERENCE_ROWS and abs(reference.threshold - float(np.quantile(brute, QUANTILE))) < 1e-9,
              f"Guard: the threshold equals a slow brute-force calculation that measures each row's distance only against rows from OTHER groups (the {QUANTILE:.0%} point of the {K_NEIGHBOURS}-nearest-row distance)",
              f"{reference.threshold:.6f}")
    # copies of the same row inside a group would be at distance zero: they must not count
    twins = pd.DataFrame(np.repeat(np.random.default_rng(4).normal(size=(10, 4)), 6, axis=0), columns=COLUMNS)
    twin_groups = np.repeat(np.arange(10), 6).astype(str)
    cl.record(fit_reference(twins, COLUMNS, [], np.arange(60), twin_groups).threshold > 0.5,
              "Guard: identical rows inside one group are never counted as neighbours of each other (otherwise the threshold would collapse to zero)", "")
    one_group = fit_reference(small, COLUMNS, [], ids, np.array(["only"] * len(small)))
    cl.record(one_group.threshold is None and not warn(one_group, small, ids).by_distance.any(), "With only one group there is no way to set a distance threshold: it is reported as unavailable and the distance check stays off", "")


def range_checks(cl: Checklist) -> None:
    rng = np.random.default_rng(9)
    values = rng.uniform(0, 10, 100)
    values[:2] = [0.0, 10.0]
    frame = pd.DataFrame({"x1": values, "kind": np.where(np.arange(100) % 2 == 0, "A", "B")})
    ref = fit_reference(frame, ["x1"], ["kind"], np.arange(100), np.array([str(i % 5) for i in range(100)]))
    probe = pd.DataFrame({"x1": [10.9, 11.1, -0.9, -1.1, 5.0, 5.0], "kind": ["A", "A", "B", "B", "C", "A"]})
    w = warn(ref, probe, np.arange(6))
    cl.record(list(w.by_range) == [False, True, False, True, False, False] and list(w.by_category) == [False, False, False, False, True, False],
              f"Range check: an input up to {RANGE_TOLERANCE:.0%} of the training range beyond its largest or smallest value is not warned, one beyond that is; a category never seen in training is always warned (even with every number in range) and only by the category check",
              f"range {list(w.by_range)}, category {list(w.by_category)}")


def steadiness_checks(cl: Checklist) -> None:
    got = [threshold_swing([1.0, 1.1]), threshold_swing([1.0, 1.25]), threshold_swing([1.0, 1.26]), threshold_swing([1.0, 1.5]), threshold_swing([1.0, 1.51]), threshold_swing([4.0, 2.0]),
           threshold_swing([1.0]), threshold_swing([1.0, None]), threshold_swing([0.0, 0.0])]
    verdicts = [g[1] if g else None for g in got]
    cl.record(verdicts == ["stable", "stable", "varying", "varying", "swinging", "swinging", None, None, None],
              "Steadiness criterion: largest over smallest up to 1.25 is stable, up to 1.5 varying, above swinging (edges included); fewer than two usable values gives no verdict", str(verdicts))


# ---------------------------------------------------------------- the group-level warning: the scenarios fixed in advance (docs/decisions.md), then its guards
def group_checks(cl: Checklist) -> None:
    from checks import group_scenarios as g

    s1 = g.s1_same_source()
    cl.record(0.02 <= s1 <= 0.08, "Group warning, scenario S1: groups of recipes from the same source as the training data are flagged about 5% of the time (200 made-up groups)", f"{100 * s1:.1f}%")
    s2 = g.s2_shifted()
    cl.record(s2["group"] >= 0.90 and s2["per_recipe_rows"] <= 0.12,
              "Group warning, scenario S2: a group of 30 recipes shifted by one standard deviation in 3 of 40 inputs is flagged at least 90% of the time, while the per-recipe distance check flags at most 12% of the same recipes "
              "(it is nearly blind to the shift)", f"group {100 * s2['group']:.0f}%, per-recipe distance {100 * s2['per_recipe_rows']:.1f}% of rows")
    s3 = g.s3_unseen_category()
    cl.record(s3["category_rows"] == 1.0 and s3["names_it"], "Group warning, scenario S3: a group from a supplier never seen in training is flagged by the unseen-supplier-or-product status in every recipe, and the unseen value is named", str(s3))
    s4 = g.s4_later_period()
    cl.record(s4 >= 0.90, "Group warning, scenario S4: a later time period drifting by half a standard deviation in 10 of 40 inputs (60 recipes) is flagged at least 90% of the time", f"{100 * s4:.0f}%")
    s5a = g.s5a_small_groups()
    cl.record(s5a["false_alarm_small"] < s5a["small"] < s5a["large"],
              "Group warning, scenario S5a (small groups): the same shift in groups of only 5 recipes is detected less often than in groups of 30 but more often than the false-alarm rate",
              f"5 recipes: {100 * s5a['small']:.0f}% (false alarm {100 * s5a['false_alarm_small']:.0f}%); 30 recipes: {100 * s5a['large']:.0f}%")
    s5b = g.s5b_ordinary_batch_effect()
    cl.record(s5b["group_based"] <= 0.08 and s5b["chance_alone"] >= 0.30 and s5b["chance_alone"] >= 5 * max(s5b["group_based"], 0.01),
              "Group warning, scenario S5b (a large ordinary batch effect, no shift): the threshold built from ordinary training groups flags about 5% (it allows for ordinary differences between groups), while a chance-alone "
              "threshold flags most of them: this is why the group-based threshold exists", f"group-based {100 * s5b['group_based']:.0f}%, chance alone {100 * s5b['chance_alone']:.0f}%")
    s5c = g.s5c_few_groups()
    cl.record(s5c["kind"] == "chance alone" and s5c["message"] == "M62" and s5c["training_groups_big_enough"] < 10,
              "Group warning, scenario S5c: with fewer than 10 training groups the threshold is labelled 'chance alone' and the message saying so is produced", str(s5c))
    # guards
    rng = np.random.default_rng(31)
    train_x, labels = g.make_groups(rng, 40, 30)
    other_x = g.make_groups(rng, 1, 30, shift={0: 3.0})[0]
    group_x = g.make_groups(rng, 1, 30)[0]
    train_s, group_s, other_s = g.standardise(train_x, group_x, other_x)
    ref = fit_group_reference(train_s, labels, g.COLUMNS)
    alone = check_group(ref, group_s)
    ref_again = fit_group_reference(train_s, labels, g.COLUMNS)
    check_group(ref_again, other_s)                                               # another group is checked first
    after_other = check_group(ref_again, group_s)
    changed = train_s.copy()
    changed[:60] = changed[:60] * 4
    moved = null_threshold(fit_group_reference(changed, labels, g.COLUMNS), 30)[0]
    cl.record(alone.statistic == after_other.statistic and alone.threshold == after_other.threshold and moved != alone.threshold,
              "Group warning guard: a group's verdict does not depend on which other groups are checked, and its threshold comes from the training rows alone (changing training rows changes it)", f"threshold {alone.threshold:.4f}")
    tiny = check_group(ref, group_s[:MIN_GROUP_ROWS - 1])
    exact = check_group(ref, group_s[:MIN_GROUP_ROWS])
    cl.record(tiny is None and exact is not None, f"Group warning guard: a group of fewer than {MIN_GROUP_ROWS} recipes is not assessed (it is counted instead), and a group of exactly {MIN_GROUP_ROWS} is", "")
    named = check_group(ref, g.standardise(train_x, g.make_groups(rng, 1, 30, shift={7: 1.5, 12: -1.5})[0])[1])
    cl.record({n for n, _ in named.top_inputs} >= {"x7", "x12"} and dict(named.top_inputs)["x7"] > 0 > dict(named.top_inputs)["x12"],
              "Group warning guard: the inputs that moved most are named, with the direction of the shift (the two inputs shifted up and down are the two named)", str(named.top_inputs))
    mixed = KindGroups("supplier", "whole suppliers (x)", [GroupResult("a", GroupWarning(30, 3.0, 1.0, True, "chance alone", 3, []), None), GroupResult("b", GroupWarning(30, 3.0, 1.0, True, "group-based", 12, []), None)], 0, [(1.0, "chance alone")])
    cl.record(_basis(mixed) == "other training groups for 1, chance alone for 1" and "chance alone" in _basis(KindGroups("x", "x", [GroupResult("a", GroupWarning(30, 3.0, 1.0, True, "chance alone", 3, []), None)], 0, [])),
              "The report says how each group's threshold was made, and never hides a chance-alone threshold", _basis(mixed))


# ---------------------------------------------------------------- the saved Stage 3a answers
def real_checks(cl: Checklist) -> None:
    files = len(list(CACHE.glob("*.pkl"))) if CACHE.exists() else 0
    if files < 280 or not all(fixture_available(n) for n in NAMES):
        cl.skip("The warning on the saved Stage 3a full-comparison answers", "they (or the real public data) are not on this computer: double-click run_full_validation.bat first")
        return
    validations = [run_validation(build_table_for_setup(fixture_setup(n), None, PROJECT_ROOT, n), FULL, n_jobs=1, cache=CACHE, save=False) for n in NAMES]
    by = {v.table.name: v for v in validations}
    decisions = decide_all(validations)
    carried = [d for d in decisions if d.status in (CARRIED, BORDERLINE)]
    shared: dict = {}
    far_low, swings, factor_swings, missing = 1.0, [], [], []
    for d in carried:
        info = stability(by[d.table], d.result, d.chosen, shared)
        expected = {k for (r, k), run in by[d.table].runs.items() if r == d.result and run.plan.available}
        if set(info) != expected:
            missing.append(f"{d.table}/{d.result}")
        for kind, (own, alt, st) in info.items():
            far_low = min(far_low, own.far)
            swings.append((st.swing[0] if st.swing else 1.0, d.table, d.result, kind))
            factor_swings.append(st.factor_swing[0] if st.factor_swing else 1.0)
    cl.record(not missing and len(carried) == 8 and far_low >= 0.95, f"Every carried result (8: 7 carried and 1 borderline) gets a warning evaluation in every hold-out type that was run, "
                                                                          f"and deliberately far-away recipes are warned by distance (lowest share {100 * far_low:.1f}%, at least 95% required)", "; ".join(missing))
    worst = max(swings)
    cl.record(worst[0] <= 1.25, f"Stability (the question asked before 3b-2 was built): the distance threshold is STEADY across the folds of every hold-out type of every carried result: "
                                f"the largest ratio of largest to smallest threshold is {worst[0]:.2f} ({worst[1]}, {worst[2]}, {worst[3]}), "
                                f"while the recalibration factors of the same folds swing up to {max(factor_swings):.2f}", f"limit 1.25; {len(swings)} hold-out types compared")
    summary = build_summary(validations)
    a, b, c = (summary[summary.index(s):summary.index(e) if e else None] for s, e in (("## Part A", "## Part B"), ("## Part B", "## Part C"), ("## Part C", None)))
    heads_b = [line for line in b.splitlines() if line.startswith("###")]
    ok_status = ("mock_hard" in b and bool(heads_b) and all("EXPLORATORY: borderline" in h for h in heads_b) and "EXPLORATORY: borderline" not in a
                 and "batch_production, dissolution_av" in c and "dissolution_av" not in "".join(l for l in a.splitlines() if l.startswith("###")) and "Carning" not in summary and "calibration" not in c.lower().replace("a calibration", ""))
    cl.record(ok_status, "The warning summary keeps the three statuses apart (the borderline result only in its own part, with its label in every heading) and lists every skipped result as not assessed, with no evaluation for it", "")
    texts = {n: build_report(v) for n, v in by.items()}
    cl.record(SAFEGUARD in summary and all(SAFEGUARD in t for t in texts.values()),
              "The summary and every per-table report open with the safeguard message: no model's range tracks its own error, so this warning is the platform's main safeguard", "")
    named = [line for t in list(texts.values()) + [summary] for line in t.splitlines() if "api_code" in line]
    cl.record(bool(named) and all(PROXY_PHRASE in line for line in named), "Every line of every warning report that names api_code says 'proxy, not a confirmed supplier'", f"{len(named)} lines")
    tagged = all(all(v.table.tag in line for line in texts[v.table.name].splitlines() if line.startswith("#")) for v in validations if v.table.tag)
    cl.record(tagged, "Exploratory and robustness-only tables carry their label in EVERY heading of their warning report", "")
    # item 1: three separate per-recipe statuses and a fourth, group-level one, with no combined flag anywhere
    composite = [w for w in ("Warned (any check)", "any check", "by any", "warned (any") if w in summary + "".join(texts.values())]
    columns_ok = all(h in summary for h in ("(1) Distance: warned", "(2) Numeric range: warned", "(3) Unseen supplier or product: warned", "(4) Groups flagged as unfamiliar"))
    group_tables = summary.count("**Whole group: is this batch, supplier or time period unfamiliar?**")
    cl.record(not composite and columns_ok and group_tables == len(carried),
              f"Item 1 of the decision: distance, numeric range and unseen supplier or product are three SEPARATE statuses, the whole-group warning is a fourth, and there is no combined 'warned' flag anywhere; "
              f"all four appear for each of the {len(carried)} carried results", f"combined-flag wording found: {composite}; group tables {group_tables}")
    batch = by["batch_production"]
    own = stability(batch, "tbl_av_hardness", "forest", shared)["supplier"][0]
    cl.record(own.parts["category"].share == 1.0 and any(c == "product_code" for c, _, _ in own.unseen) and "product_code = " in summary,
              "Real batch data: under the API-code hold-out the unseen-supplier-or-product status warns every recipe and names the product codes that were never seen (shown in the report)", f"{own.unseen[:2]}")
    group_ok = all(evaluate_groups(by[d.table], d.result, k, d.chosen) is not None for d in carried for (r, k), run in by[d.table].runs.items() if r == d.result and run.plan.available)
    chance_text = "chance alone" in summary and "too few training group" in "".join(texts.values())
    cl.record(group_ok and chance_text, "The whole-group warning is evaluated for every carried result in every hold-out type, and where there were too few training groups the reports say so in words ('chance alone' and the message M62)", "")
    swing_text = "Largest ÷ smallest" in summary and summary.count("(stable)") >= len(swings) // 2
    cl.record(swing_text, "The reports show, for every carried result and hold-out type, the threshold on every fold, its largest-over-smallest ratio and verdict, the same with batches as reference groups, and the recalibration factors beside them", "")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 3b-2: the applicability-domain warning (is a recipe far from the data, and is the warning's own threshold steady?)")
    before = project_files()
    proof_checks(cl)
    guard_checks(cl)
    range_checks(cl)
    steadiness_checks(cl)
    group_checks(cl)
    real_checks(cl)
    found = forbidden_in(sorted((ROOT / "cellpoc" / "modelling").glob("*.py")))
    cl.record(not found, "The modelling code, including the warning, contains no random splitter or sampler", "; ".join(found[:3]))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
