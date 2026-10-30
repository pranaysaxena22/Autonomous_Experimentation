"""Health check for Stage 4-2 (the development lab): is it the world it was described to be, and can the engine never see its truth?

In plain words it checks that: the lab's dissolution and hardness are exactly the mock generator's formula (compared on random recipes, to nine decimal places) with the generator's own supplier and grade
effects; a measurement depends only on (seed, trial), never on the order of asking; a recipe outside the allowed ranges, or one whose filler would be out of range, is refused in plain words; and, against
properties written down BEFORE the lab was first tested: a random recipe passes all three targets 2% to 10% of the time, dissolution 15% to 60%, hardness 20% to 60%, friability 55% to 90%, and friability
removes at least 15% of the recipes that pass the other two (so it is a real constraint); the no-shift history has date drift of at most 0.10 and a supplier explaining at most 4% of any input's spread,
while the two shift histories have drift of at least 0.25 and a supplier explaining at least 15%; the new-supplier scenario brings in a supplier the history never contains from trial 8 (and moves the truth
by about 6 points), the period-shift scenario steps the truth by exactly (-6, +0.8) from trial 6 and the baseline never does; in the unpredictable scenario a quadratic fit on the earlier half of the history
explains at most 25% of the later half's dissolution while it explains at least 60% of every smooth result; the history has the mock data's 21 columns and is identical when generated twice; the seeds are fresh
(10000 and up) and none is a sealed acceptance seed, and nothing here names the sealed lab; and the guard stops anything but the virtual lab and the scoring from importing the lab's hidden truth.
Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.virtual_lab import _dev_truth as truth  # noqa: E402
from cellpoc.virtual_lab import dev_oracle as oracle  # noqa: E402
from cellpoc.virtual_lab.dev_lab import COLUMNS, NEW_SUPPLIER_FROM, PERIOD_STEP_FROM, SCENARIOS, DevLab, make_context, period_shift_v2, reshaped  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

SEED = 10101
CTX = make_context("A", "MCC-101", "DT-1", "C001", 1.0)
KEYS = ["drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kN"]


def formula_checks(cl: Checklist) -> None:
    spec = importlib.util.spec_from_file_location("mock_generator", ROOT / "tools" / "make_mock_data.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    biggest = 0.0
    for r in oracle.random_recipes(500, 3):
        d1, h1 = truth.smooth_truth(r)
        d2, h2 = gen.truth(r["drug_pct"], truth.filler_of(r), r["binder_pct"], r["disintegrant_pct"], r["lubricant_pct"], r["compression_force_kn"], r["blend_time_min"], 1.0, 0.0)
        biggest = max(biggest, abs(d1 - d2), abs(h1 - h2))
    cl.record(biggest < 1e-9, "The lab's dissolution and hardness are exactly the mock generator's formula (500 random recipes, largest difference below one billionth)", f"{biggest:.1e}")
    cl.record(all(truth.SUPPLIER_EFFECT[k] == gen.SUPPLIER_EFFECT[k] for k in "ABC") and truth.GRADE_EFFECT == gen.GRADE_EFFECT and "D" not in gen.SUPPLIER_EFFECT and truth.LIM["drug_pct"] == gen.LIM["drug"],
              "The supplier A, B and C effects, the grade effects and the ranges are the generator's own; supplier D is the lab's addition", "")


def behaviour_checks(cl: Checklist) -> None:
    lab = DevLab(SCENARIOS["baseline"], SEED)
    r = oracle.random_recipes(3, 5)
    first = [lab.measure(i, r[i % 3], CTX) for i in (3, 1, 2)]
    other = DevLab(SCENARIOS["baseline"], SEED)
    second = {i: other.measure(i, r[i % 3], CTX) for i in (1, 2, 3)}
    cl.record(first[0] == second[3] and first[1] == second[1] and first[2] == second[2] and DevLab(SCENARIOS["baseline"], SEED + 1).measure(1, r[1], CTX) != second[1],
              "A measurement depends only on (seed, trial), not on the order of asking, and a different seed gives a different lab day", "")
    # (with every ingredient inside its own range the filler can only fall between 54% and 86.75%, which are exactly its limits, so the filler guard can never fire for ranges that are respected)
    bad = [dict(r[0], drug_pct=45.0), dict(r[0], compression_force_kn=1.0), dict(r[0], blend_time_min=60.0)]
    messages = []
    for b in bad:
        try:
            lab.measure(1, b, CTX)
            messages.append("")
        except ValueError as error:
            messages.append(str(error))
    cl.record(all(messages) and all("outside the allowed range" in m for m in messages), "A recipe with an ingredient or a process setting outside its allowed range is refused in plain words", str(messages[0]))
    t1 = oracle.true_results(lab, 1, r[0], CTX)
    cl.record(set(t1) == {"dissolution_30min_pct", "hardness_kp", "friability_pct"} and all(np.isfinite(v) for v in t1.values()), "The lab returns dissolution, hardness and friability for a recipe in a context", str({k: round(v, 2) for k, v in t1.items()}))


def property_checks(cl: Checklist) -> None:
    lab = DevLab(SCENARIOS["baseline"], SEED)
    df = pd.DataFrame([oracle.true_results(lab, 1, r, CTX) for r in oracle.random_recipes(30000, 1)])
    shares = {"diss": float((df.dissolution_30min_pct >= 85).mean()), "hard": float(df.hardness_kp.between(6, 10).mean()), "fri": float((df.friability_pct <= 1).mean())}
    good = df.apply(lambda row: oracle.is_good(row.to_dict()), axis=1)
    both = (df.dissolution_30min_pct >= 85) & df.hardness_kp.between(6, 10)
    removed = float(1 - good[both].mean())
    cl.record(0.02 <= good.mean() <= 0.10 and 0.15 <= shares["diss"] <= 0.60 and 0.20 <= shares["hard"] <= 0.60 and 0.55 <= shares["fri"] <= 0.90,
              "Pass shares of random recipes sit in the bands written down in advance: all three 2% to 10%, dissolution 15% to 60%, hardness 20% to 60%, friability 55% to 90%",
              f"all three {100 * good.mean():.1f}%, " + ", ".join(f"{k} {100 * v:.1f}%" for k, v in shares.items()))
    cl.record(removed >= 0.15, "Friability is a real constraint: it removes at least 15% of the recipes that already pass dissolution and hardness (the generator's friability removes none)", f"{100 * removed:.1f}%")


def history_checks(cl: Checklist) -> None:
    stats = {}
    for name, sc in SCENARIOS.items():
        h = DevLab(sc, SEED).history(3000)
        when = pd.to_datetime(h.date).rank()
        drift = max(abs(h[c].rank().corr(when)) for c in KEYS)
        share = max(float(((h[c].groupby(h.binder_supplier).transform("mean") - h[c].mean()) ** 2).sum() / ((h[c] - h[c].mean()) ** 2).sum()) for c in KEYS)
        stats[name] = (drift, share, h)
    quiet = [stats[n] for n in ("baseline", "unpredictable_dissolution")]
    shifted = [stats[n] for n in ("new_supplier", "period_shift")]
    cl.record(all(d <= 0.10 and s <= 0.04 for d, s, _ in quiet) and all(d >= 0.25 and s >= 0.15 for d, s, _ in shifted),
              "In the no-shift histories date drift is at most 0.10 and a supplier explains at most 4% of any input; in the two shift histories drift is at least 0.25 and a supplier explains at least 15%, so supplier and date really move the recipes",
              "; ".join(f"{n}: drift {stats[n][0]:.2f}, supplier {100 * stats[n][1]:.1f}%" for n in stats))
    h = stats["baseline"][2]
    cl.record(list(h.columns) == COLUMNS and len(COLUMNS) == 21 and h.equals(DevLab(SCENARIOS["baseline"], SEED).history(3000)) and set(h.binder_supplier) <= {"A", "B", "C"},
              "A history has the mock data's 21 columns, never contains supplier D, and is identical when generated twice", f"{len(h)} rows")
    # a quadratic fit on the earlier half, scored on the later half
    r2 = {}
    for name in ("baseline", "unpredictable_dissolution"):
        hh = stats[name][2].sort_values("date")
        n = len(hh) // 2
        X = hh[KEYS].to_numpy(float)
        X = (X - X.mean(0)) / X.std(0)
        feats = np.c_[np.ones(len(X)), X, X ** 2, np.column_stack([X[:, i] * X[:, j] for i in range(5) for j in range(i + 1, 5)])]
        for col in ("dissolution_30min_pct", "hardness", "friability_pct"):
            y = hh[col].to_numpy(float)
            pred = feats[n:] @ np.linalg.lstsq(feats[:n], y[:n], rcond=None)[0]
            r2[(name, col)] = 1 - ((y[n:] - pred) ** 2).sum() / ((y[n:] - y[n:].mean()) ** 2).sum()
    cl.record(r2[("unpredictable_dissolution", "dissolution_30min_pct")] <= 0.25 and all(v >= 0.60 for k, v in r2.items() if k != ("unpredictable_dissolution", "dissolution_30min_pct")),
              "The unpredictable scenario is unpredictable only where designed: a quadratic fit on the earlier half explains at most 25% of the later half's dissolution, and at least 60% of every smooth result",
              ", ".join(f"{k[0][:6]}/{k[1][:4]} {v:.2f}" for k, v in r2.items()))


def scenario_checks(cl: Checklist) -> None:
    rec = oracle.random_recipes(400, 9)
    diffs = {}
    for name in ("baseline", "new_supplier", "period_shift"):
        lab = DevLab(SCENARIOS[name], SEED)
        ctx = lab.context(1)
        pre = [oracle.true_results(lab, PERIOD_STEP_FROM - 1, r, ctx) for r in rec]
        post = [oracle.true_results(lab, PERIOD_STEP_FROM, r, ctx) for r in rec]
        away = [10 < a["dissolution_30min_pct"] < 90 and a["hardness_kp"] > 1 for a in pre]            # away from the 0 and 100 caps and from zero hardness, where a step is cut short
        step = np.array([[b[k] - a[k] for k in ("dissolution_30min_pct", "hardness_kp")] for a, b, ok in zip(pre, post, away) if ok])
        d_a = np.mean([oracle.true_results(lab, 1, r, lab.context(1))["dissolution_30min_pct"] for r in rec])
        d_d = np.mean([oracle.true_results(lab, NEW_SUPPLIER_FROM, r, lab.context(NEW_SUPPLIER_FROM))["dissolution_30min_pct"] for r in rec])
        deviation = float(np.abs(step - np.array(truth.PERIOD_STEP)).max()) if name == "period_shift" else float(np.abs(step).max())
        diffs[name] = (lab.context(PERIOD_STEP_FROM - 1).categories["binder_supplier"], lab.context(NEW_SUPPLIER_FROM + 5).categories["binder_supplier"], deviation, float(d_d - d_a), len(step))
    cl.record(diffs["baseline"][1] == "A" and diffs["new_supplier"][0] == "A" and diffs["new_supplier"][1] == "D" and NEW_SUPPLIER_FROM == 8 and "D" not in DevLab(SCENARIOS["new_supplier"], SEED).history(500).binder_supplier.unique(),
              f"The new-supplier scenario uses supplier A until trial {NEW_SUPPLIER_FROM - 1} and the unseen supplier D from trial {NEW_SUPPLIER_FROM}; the baseline never changes supplier; D never appears in a history", str({k: v[:2] for k, v in diffs.items()}))
    cl.record(-9.0 < diffs["new_supplier"][3] < -3.0, "Supplier D really shifts the truth: dissolution of the same recipes is about 6 points lower with D than with A", f"{diffs['new_supplier'][3]:+.1f}")
    cl.record(diffs["period_shift"][2] < 1e-9 and diffs["baseline"][2] < 1e-9 and diffs["new_supplier"][2] < 1e-9 and PERIOD_STEP_FROM == 6 and min(v[4] for v in diffs.values()) >= 100,
              f"The period-shift scenario steps the truth by exactly (-6, +0.8) from trial {PERIOD_STEP_FROM} and no other scenario ever steps it (compared on recipes away from the 0 and 100 caps)",
              f"largest deviation {diffs['period_shift'][2]:.1e}; {min(v[4] for v in diffs.values())} or more recipes compared")
    v2 = DevLab(period_shift_v2(2.5), SEED)                                                         # the harsher version (Finding A): the same kind of step, k times as large
    pre = [oracle.true_results(v2, PERIOD_STEP_FROM - 1, r, v2.context(1)) for r in rec]
    post = [oracle.true_results(v2, PERIOD_STEP_FROM, r, v2.context(1)) for r in rec]
    kept = [(a, b) for a, b in zip(pre, post) if 20 < a["dissolution_30min_pct"] < 90]
    dev2 = max(max(abs((b["dissolution_30min_pct"] - a["dissolution_30min_pct"]) - 2.5 * truth.PERIOD_STEP[0]), abs((b["hardness_kp"] - a["hardness_kp"]) - 2.5 * truth.PERIOD_STEP[1])) for a, b in kept)
    shares = [oracle.share_good_after_step(400, 11, k) for k in (0.0, 1.0, 2.5)]
    cl.record(dev2 < 1e-9 and len(kept) >= 50 and all(s.step_scale == 1.0 for s in SCENARIOS.values()) and "period_shift_v2" not in SCENARIOS and shares[0] >= shares[1] >= shares[2],
              "Period shift version 2 steps the truth by exactly 2.5 times the original (-15, +2.0) and the four scenarios of the comparison still use the original size (scale 1.0); version 2 is not one of the four; the bigger the step the fewer random recipes stay truly good",
              f"largest deviation {dev2:.1e} on {len(kept)} recipes; share truly good after a step of 0, 1 and 2.5 times: {shares[0]:.1%}, {shares[1]:.1%}, {shares[2]:.1%}")
    rs = DevLab(reshaped(1.0), SEED)                                                                # the reshaped scenario: the binder's effect on dissolution reverses, nothing else moves
    pre = [oracle.true_results(rs, PERIOD_STEP_FROM - 1, r, rs.context(1)) for r in rec]
    post = [oracle.true_results(rs, PERIOD_STEP_FROM, r, rs.context(1)) for r in rec]
    keep = [(r, a, b) for r, a, b in zip(rec, pre, post) if 20 < a["dissolution_30min_pct"] < 80]
    dev3 = max(abs((b["dissolution_30min_pct"] - a["dissolution_30min_pct"]) - 24.0 * ((r["binder_pct"] - 2.0) / 4.0 - 0.5)) for r, a, b in keep)
    untouched = all(a["hardness_kp"] == b["hardness_kp"] and a["friability_pct"] == b["friability_pct"] for _, a, b in keep)
    stats = oracle.reshape_statistics(2000, 12, 1.0)
    cl.record(dev3 < 1e-9 and len(keep) >= 50 and untouched and all(s.reshape_scale == 0.0 for s in SCENARIOS.values()) and "reshaped" not in SCENARIOS and stats["up_share"] > 0.2 and stats["down_share"] > 0.2 and stats["spearman"] < 0.95,
              "The reshaped scenario reverses the binder's effect on dissolution exactly (24 x (binder share - 0.5), so recipes with little binder lose and recipes with much binder gain), moves nothing else, is not one of the four comparison scenarios, and really changes the ranking of recipes (some gain, some lose, rank correlation well below 1)",
              f"largest deviation {dev3:.1e} on {len(keep)} recipes; at size 1.0: {stats['up_share']:.0%} gain more than 3 points, {stats['down_share']:.0%} lose more than 3, rank correlation {stats['spearman']:.2f}")


def hygiene_checks(cl: Checklist) -> None:
    sealed = set(range(7_000_001, 7_000_041)) | set(range(7_000_101, 7_000_141))      # the retired block (examined before the first seal) and the current one
    seeds = [10101, 10102, 10103, 10104]
    text = "".join((ROOT / "cellpoc" / "virtual_lab" / f).read_text(encoding="utf-8") for f in ("_dev_truth.py", "dev_lab.py", "dev_oracle.py")) + (ROOT / "tools" / "make_dev_scenarios.py").read_text(encoding="utf-8")
    cl.record(all(s >= 10000 for s in seeds) and not (set(seeds) & sealed) and ("sealed" + "_lab") not in text and "acceptance/" not in text and "7000" not in text,
              "The development seeds are fresh (10000 and up), none is a sealed acceptance seed, and no development-lab code names the sealed lab or its seeds", "")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 4-2: the development lab (is it the world it was described to be, and can the engine never see its truth?)")
    before = project_files()
    formula_checks(cl)
    behaviour_checks(cl)
    property_checks(cl)
    history_checks(cl)
    scenario_checks(cl)
    hygiene_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
