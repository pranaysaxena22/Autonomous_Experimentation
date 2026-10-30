r"""Stage 4 follow-up after the 4-4 review (docs/decisions.md, "Stage 4 follow-up"): two jobs, both on DEVELOPMENT seeds, both with the engine unchanged.

  calibrate   Finding A: how large must the period_shift step be for the UNGOVERNED engine to lose at least half of its truly-good recipes? (seeds 10950 to 10969; the governed engine is never run here)
  diagnose    Finding B: records, per trial, what the governed and ungoverned engines stated and what was measured, in period_shift version 1 (seeds 10930 to 10939) and in the unshifted baseline (10940 to 10949)
  report-b    reads what `diagnose` saved and prints the readings fixed in advance

Run:  .venv\Scripts\python.exe tools\stage4_followup.py calibrate     (then diagnose, then report-b)
Everything is written under runs\followup\ (not in git). Everything is synthetic; the sealed acceptance lab is never touched and 10200 to 10239 and 10300 to 10339 are never used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.contracts import EngineBrief, Observation  # noqa: E402
from cellpoc.decision_engine.baselines import UngovernedStrategy  # noqa: E402
from cellpoc.decision_engine.governed import GovernedStrategy  # noqa: E402
from cellpoc.scoring import score_dev_trial  # noqa: E402
from cellpoc.virtual_lab import dev_oracle  # noqa: E402
from cellpoc.virtual_lab.dev_lab import (DESIGN_SPACE, FILLER_RANGE, HISTORY_EXPERIMENTS, HISTORY_SEEDS, INGREDIENTS, SCENARIOS, DevLab, cleaned_history, period_shift_v2, target_specs)  # noqa: E402

OUT = ROOT / "runs" / "followup"
TRIALS = 30
GRID = (1.5, 2.0, 2.5, 3.0, 4.0)                                    # fixed in docs/decisions.md before any run
CALIBRATION_SEEDS = tuple(range(10950, 10970))
RANDOM_SEED, RANDOM_N, MIN_WINNABLE = 10970, 20000, 0.02
B_SHIFT_SEEDS, B_BASE_SEEDS = tuple(range(10930, 10940)), tuple(range(10940, 10950))
DISS = "dissolution_30min_pct"
CLASSES = {"governed": GovernedStrategy, "ungoverned": UngovernedStrategy}


def run_one(label: str, scenario_name: str, step_scale: float | None, strategy: str, seed: int) -> dict:
    """One instrumented campaign. The engine is only called, never changed; what it stated and what was measured is read from its decisions."""
    from threadpoolctl import threadpool_limits

    path = OUT / "cache" / f"{label}_{strategy}_{seed}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    scenario = period_shift_v2(step_scale) if step_scale is not None else SCENARIOS[scenario_name]
    brief = EngineBrief.from_json((ROOT / "runs" / "devlab" / f"brief_dev_{scenario_name}.json").read_text(encoding="utf-8"))
    specs = target_specs()
    with threadpool_limits(limits=1):
        history = cleaned_history(DevLab(SCENARIOS[scenario_name], HISTORY_SEEDS[scenario_name]), HISTORY_EXPERIMENTS)
        engine = CLASSES[strategy](brief, specs, history, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)
        lab = DevLab(scenario, seed)
        obs, rows = [], []
        for t in range(1, TRIALS + 1):
            ctx = lab.context(t)
            d = engine.propose(t, ctx, obs)
            m = lab.measure(t, d.recipe, ctx)
            obs.append(Observation(t, d.recipe, ctx, m))
            s = score_dev_trial(lab, specs, t, d.recipe, ctx, m)
            rows.append({"trial": t, "kind": d.kind, "good": bool(s.good), "stale": list(d.stale), "ranges": {r: list(v) for r, v in d.stated_ranges.items()}, "measured": {r: float(v) for r, v in m.items()}})
    rec = {"label": label, "strategy": strategy, "seed": seed, "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def run_many(tasks: list, jobs: int) -> list:
    from joblib import Parallel, delayed

    started, out = time.time(), []
    for start in range(0, len(tasks), max(1, jobs * 2)):
        out += Parallel(n_jobs=jobs)(delayed(run_one)(*t) for t in tasks[start:start + max(1, jobs * 2)])
        print(f"  {len(out)} of {len(tasks)} campaigns done ({(time.time() - started) / 60:.1f} min)", flush=True)
    return out


# ---------------------------------------------------------------- Finding A
def calibrate(jobs: int) -> int:
    tasks = [(f"cal_k{k}", "period_shift", k, "ungoverned", s) for k in GRID for s in CALIBRATION_SEEDS]
    recs = run_many(tasks, jobs)
    table, chosen = [], None
    for k in GRID:
        mine = [r for r in recs if r["label"] == f"cal_k{k}"]
        before = float(np.mean([[row["good"] for row in r["rows"][:5]] for r in mine]))
        after = float(np.mean([[row["good"] for row in r["rows"][5:]] for r in mine]))
        winnable = dev_oracle.share_good_after_step(RANDOM_N, RANDOM_SEED, k)
        ratio = after / before if before else float("nan")
        c1, c2 = ratio <= 0.5, winnable >= MIN_WINNABLE
        table.append({"k": k, "step": [-6.0 * k, 0.8 * k], "before": before, "after": after, "ratio": ratio, "random_share_good": winnable, "C1": c1, "C2": c2})
        if chosen is None and c1 and c2:
            chosen = k
    # the original size, for reference (already run in 4-4; not part of the grid)
    print("\nStep size (k times -6 dissolution, +0.8 hardness) | ungoverned truly good: trials 1-5 | trials 6-30 | ratio | random recipes truly good after the step | C1 (ratio <= 0.5) | C2 (>= 2%)")
    for r in table:
        print(f"  k = {r['k']:.1f} ({r['step'][0]:+.1f}, {r['step'][1]:+.1f})   {r['before']:.1%}   {r['after']:.1%}   {r['ratio']:.2f}   {r['random_share_good']:.2%}   {'yes' if r['C1'] else 'no'}   {'yes' if r['C2'] else 'no'}")
    print(f"\nSmallest size meeting C1 and C2: {chosen if chosen is not None else 'NONE (stop and report)'}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calibration.json").write_text(json.dumps({"grid": GRID, "seeds": [CALIBRATION_SEEDS[0], CALIBRATION_SEEDS[-1]], "table": table, "chosen_k": chosen}, indent=1), encoding="utf-8")
    return 0


# ---------------------------------------------------------------- Finding B
def diagnose(jobs: int) -> int:
    tasks = [("shift", "period_shift", None, st, s) for st in ("governed", "ungoverned") for s in B_SHIFT_SEEDS] + [("base", "baseline", None, "governed", s) for s in B_BASE_SEEDS]
    run_many(tasks, jobs)
    return 0


def _load(label: str, strategy: str, seeds) -> list:
    return [json.loads((OUT / "cache" / f"{label}_{strategy}_{s}.json").read_text(encoding="utf-8")) for s in seeds]


def _errors(recs: list, result: str, trials: range, kinds=None) -> dict:
    """Over the given trials: hit rate, mean absolute error and mean signed error of the measurement from the middle of the range stated for it."""
    hits, absolute, signed = [], [], []
    for r in recs:
        for row in r["rows"]:
            if row["trial"] in trials and result in row["ranges"] and (kinds is None or row["kind"] in kinds):
                lo, hi = row["ranges"][result]
                m = row["measured"][result]
                hits.append(lo <= m <= hi)
                signed.append(m - (lo + hi) / 2)
                absolute.append(abs(signed[-1]))
    n = len(hits)
    return {"n": n, "hit": float(np.mean(hits)) if n else None, "abs": float(np.mean(absolute)) if n else None, "signed": float(np.mean(signed)) if n else None}


def _fmt(e: dict) -> str:
    return "no data" if not e["n"] else f"n={e['n']}, hit rate {e['hit']:.2f}, mean |error| {e['abs']:.2f}, mean signed error {e['signed']:+.2f}"


def report_b() -> int:
    gov, ung, base = _load("shift", "governed", B_SHIFT_SEEDS), _load("shift", "ungoverned", B_SHIFT_SEEDS), _load("base", "governed", B_BASE_SEEDS)
    groups = {"trials 13-18": range(13, 19), "trials 19-24": range(19, 25), "trials 25-30": range(25, 31)}
    print("PERIOD SHIFT version 1 (seeds 10930 to 10939), dissolution (the target the step moves by -6)")
    for name, recs in (("governed", gov), ("ungoverned", ung)):
        print(f"  {name}:")
        print(f"    trials 1-5 (before the step): {_fmt(_errors(recs, DISS, range(1, 6)))}")
        print(f"    trials 6-12 (after the step, before any alarm): {_fmt(_errors(recs, DISS, range(6, 13)))}")
        for g, rng in groups.items():
            print(f"    {g}: {_fmt(_errors(recs, DISS, rng))}")
    e1, e3 = _errors(gov, DISS, groups["trials 13-18"]), _errors(gov, DISS, groups["trials 25-30"])
    supported = e3["hit"] <= 7 / 12 and e3["abs"] >= 0.8 * e1["abs"] and e3["signed"] < -3.0
    refuted = e3["abs"] <= 0.5 * e1["abs"] or e3["hit"] >= 0.75
    print(f"\n  READING (fixed in advance), governed dissolution: hit rate in trials 25-30 = {e3['hit']:.2f} (supported needs <= 0.58); |error| 25-30 / 13-18 = {e3['abs'] / e1['abs']:.2f} (supported needs >= 0.80, refuted <= 0.50); "
          f"signed error 25-30 = {e3['signed']:+.2f} (supported needs < -3.0)  ->  {'SUPPORTED' if supported and not refuted else 'REFUTED' if refuted and not supported else 'INCONCLUSIVE'}")
    exploit = _errors(gov, DISS, range(6, 13), kinds=("exploit", "exploratory"))
    stale_x = _errors(gov, DISS, range(13, 31), kinds=("stale_exploration",))
    print(f"\n  (b) governed picks, step with no exploration (trials 6-12): {_fmt(exploit)}")
    print(f"      governed picks, step plus exploration (stale-exploration picks, trials 13-30): {_fmt(stale_x)}")
    stale_runs = []
    for r in gov:
        flags = [bool(row["stale"]) for row in r["rows"]]
        first = flags.index(True) if True in flags else None
        stale_runs.append((first + 13 - 12 if first is not None else None, sum(flags[first:]) / len(flags[first:]) if first is not None else None, first is not None and not all(flags[first:])))
    fired = [s for s in stale_runs if s[0] is not None]
    print(f"\n  governed campaigns: watch fired in {len(fired)} of {len(gov)}; share of trials stale from first firing: mean {np.mean([s[1] for s in fired]):.2f}; cleared before the end in {sum(s[2] for s in fired)} campaigns" if fired else "\n  the watch never fired")
    print("\n  the other two targets, governed, same groups:")
    for target in ("hardness_kp", "friability_pct"):
        print(f"    {target}: " + "; ".join(f"{g}: hit {_errors(gov, target, rng)['hit']:.2f}" for g, rng in groups.items()))
    print("\nBASELINE, governed, nothing shifted (seeds 10940 to 10949): the engine's real hit rate for its stated 90% ranges (the plan assumed 0.90)")
    for target in ("dissolution_30min_pct", "hardness_kp", "friability_pct"):
        allk = _errors(base, target, range(1, 31))
        by = {k: _errors(base, target, range(1, 31), kinds=(k,)) for k in ("exploit", "exploratory", "stale_exploration")}
        print(f"    {target}: all picks hit {allk['hit']:.3f} (n={allk['n']}); " + "; ".join(f"{k} {v['hit']:.3f} (n={v['n']})" for k, v in by.items() if v["n"]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=("calibrate", "diagnose", "report-b"))
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    return {"calibrate": lambda: calibrate(args.jobs), "diagnose": lambda: diagnose(args.jobs), "report-b": report_b}[args.job]()


if __name__ == "__main__":
    sys.exit(main())
