r"""Replay of the 40 governed period_shift campaigns of the 4-4 comparison (seeds 10200 to 10239), to recover the recipes the stored records do not hold, and the distance analysis fixed in docs/decisions.md
("Finding A closed ... where the governed engine explores") BEFORE this was run.

This is a DIAGNOSIS of an outcome already reached. It does not re-judge the governed-against-ungoverned result and uses no seed to judge any engine change (see the seed log in docs/decisions.md).

  replay      re-runs the 40 campaigns exactly as run_campaign does, records each trial's recipe, and for every stale-exploration pick the distance to the pre-shift anchors and its position in the engine's own
              random candidate pool; then the MANDATORY GATE: every pick kind, truly-good flag and stale flag must equal the stored record, or the replay is discarded, the mismatch is reported, and nothing else is done
  analyse     only if the gate passed: the readings fixed in advance

Run:  .venv\Scripts\python.exe tools\stage4_replay_analysis.py replay      then      ... analyse
Everything is written under runs\followup\replay\ (not in git). Synthetic data only; the sealed acceptance lab is never touched.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.comparison.dev_comparison import COMPARISON_SEEDS, CampaignRecord, build_strategy  # noqa: E402
from cellpoc.contracts import EngineBrief, Observation  # noqa: E402
from cellpoc.scoring import score_dev_trial  # noqa: E402
from cellpoc.virtual_lab.dev_lab import SCENARIOS, DevLab, target_specs  # noqa: E402

OUT = ROOT / "runs" / "followup" / "replay"
STORED = ROOT / "runs" / "devcomparison" / "cache" / "period_shift"
SCENARIO, TRIALS, ANCHORS, STEP_TRIAL, NEAR = "period_shift", 30, 3, 6, 0.15


def replay_one(seed: int) -> dict:
    from threadpoolctl import threadpool_limits

    brief = EngineBrief.from_json((ROOT / "runs" / "devlab" / f"brief_dev_{SCENARIO}.json").read_text(encoding="utf-8"))
    specs = target_specs()
    with threadpool_limits(limits=1):                                           # as the comparison ran
        lab = DevLab(SCENARIOS[SCENARIO], seed)
        engine = build_strategy("governed", SCENARIO, brief, seed, None)
        obs, anchors, trials = [], None, []
        for t in range(1, TRIALS + 1):
            ctx = lab.context(t)
            if t == STEP_TRIAL:                                                 # the best measured recipes before the step, as the engine itself ranks them (its own margin)
                anchors = engine._unit(engine._best_measured(engine._rows(obs), ANCHORS))
            d = engine.propose(t, ctx, obs)
            row = {"trial": t, "kind": d.kind, "stale": list(d.stale), "chances": dict(d.chances), "recipe": d.recipe}
            if d.kind == "stale_exploration":
                unit, is_local, _ = engine._candidates(t, engine._rows(obs), obs, ctx)           # the engine's own candidate pool for this trial; the random part is the spread-evenly baseline
                pool = unit[~is_local]
                pick = engine._unit(__import__("pandas").DataFrame([d.recipe]))[0]
                dist = lambda u: np.sqrt(((u[:, None, :] - anchors[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
                pool_d, pick_d = dist(pool), float(dist(pick[None, :])[0])
                row.update({"distance": pick_d, "position": float((pool_d < pick_d).mean()), "pool_size": int(len(pool)), "pool_near_share": float((pool_d <= NEAR).mean()), "all_stale": len(d.stale) == len(engine.trusted)})
            m = lab.measure(t, d.recipe, ctx)
            obs.append(Observation(t, d.recipe, ctx, m))
            row["good"] = bool(score_dev_trial(lab, specs, t, d.recipe, ctx, m).good)
            trials.append(row)
    return {"seed": seed, "trials": trials}


def gate(replayed: dict) -> list:
    """Every pick kind, truly-good flag and stale flag against the stored record, campaign by campaign. Returns the list of mismatches (empty = passed)."""
    problems = []
    for seed, rec in replayed.items():
        path = STORED / f"governed_{seed}.json"
        if not path.exists():
            problems.append(f"seed {seed}: no stored record")
            continue
        stored = CampaignRecord.from_json(path.read_text(encoding="utf-8"))
        for i, row in enumerate(rec["trials"]):
            if row["kind"] != stored.kinds[i] or row["good"] != bool(stored.good[i]) or list(row["stale"]) != list(stored.stale[i]):
                problems.append(f"seed {seed}, trial {i + 1}: replay (kind {row['kind']}, good {row['good']}, stale {row['stale']}) against stored (kind {stored.kinds[i]}, good {stored.good[i]}, stale {stored.stale[i]})")
    return problems


def replay(jobs: int) -> int:
    from joblib import Parallel, delayed

    started = time.time()
    results = Parallel(n_jobs=jobs)(delayed(replay_one)(s) for s in COMPARISON_SEEDS)
    print(f"  replayed {len(results)} campaigns in {(time.time() - started) / 60:.1f} min")
    replayed = {r["seed"]: r for r in results}
    problems = gate(replayed)
    chance_diffs = sum(1 for seed, rec in replayed.items() for i, row in enumerate(rec["trials"])
                       if {k: round(v, 12) for k, v in row["chances"].items()} != {k: round(v, 12) for k, v in CampaignRecord.from_json((STORED / f"governed_{seed}.json").read_text(encoding="utf-8")).chances[i].items()})
    if problems:
        shutil.rmtree(OUT, ignore_errors=True)
        print(f"\nVERIFICATION FAILED: {len(problems)} mismatches. The replay is DISCARDED and no analysis is run. The first few:")
        for p in problems[:10]:
            print("  " + p)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for seed, rec in replayed.items():
        (OUT / f"governed_{seed}.json").write_text(json.dumps(rec), encoding="utf-8")
    (OUT / "GATE_PASSED.txt").write_text(f"all {len(replayed)} campaigns: pick kind, truly-good flag and stale flag equal the stored record for all {sum(len(r['trials']) for r in replayed.values())} trials; stated chances differing: {chance_diffs}\n", encoding="utf-8")
    print(f"\nVERIFICATION PASSED: all {len(replayed)} campaigns match the stored records on every pick kind, truly-good flag and stale flag ({sum(len(r['trials']) for r in replayed.values())} trials); stated chances that differ: {chance_diffs}")
    return 0


def analyse() -> int:
    if not (OUT / "GATE_PASSED.txt").exists():
        print("The verification gate has not passed: no analysis.")
        return 2
    camps = [json.loads((OUT / f"governed_{s}.json").read_text(encoding="utf-8")) for s in COMPARISON_SEEDS]
    picks = [row for c in camps for row in c["trials"] if row["kind"] == "stale_exploration"]
    pos = np.array([p["position"] for p in picks])
    med = float(np.median(pos))
    reading = "CONCENTRATED" if med < 0.25 else "EVENLY SPREAD (or farther than even)" if med >= 0.40 else "INCONCLUSIVE"
    print(f"stale-exploration picks: {len(picks)} across {len(camps)} campaigns ({len(picks) / len(camps):.1f} per campaign)")
    print(f"position in the engine's own random pool (0 = nearest to the pre-shift best recipes, 0.5 = middle, 1 = farthest): median {med:.3f}; quartiles {np.quantile(pos, 0.25):.3f} to {np.quantile(pos, 0.75):.3f}; mean {pos.mean():.3f}")
    print(f"READING (fixed in advance: concentrated < 0.25, evenly spread >= 0.40, otherwise inconclusive): {reading}")
    print(f"campaign medians: min {min(np.median([r['position'] for r in c['trials'] if r['kind'] == 'stale_exploration']) for c in camps if any(r['kind'] == 'stale_exploration' for r in c['trials'])):.3f}, "
          f"max {max(np.median([r['position'] for r in c['trials'] if r['kind'] == 'stale_exploration']) for c in camps if any(r['kind'] == 'stale_exploration' for r in c['trials'])):.3f}")
    print("\nwithout a threshold:")
    for name, sel in (("all three targets stale (the engine takes the candidate farthest from everything measured)", [p for p in picks if p["all_stale"]]),
                      ("only some targets stale (even trials: local search near the best measured passes)", [p for p in picks if not p["all_stale"]])):
        if not sel:
            print(f"  {name}: no picks")
            continue
        q = np.array([p["position"] for p in sel])
        near = np.mean([p["distance"] <= NEAR for p in sel])
        pool_near = np.mean([p["pool_near_share"] for p in sel])
        print(f"  {name}: {len(sel)} picks; median position {np.median(q):.3f}; within {NEAR} of an anchor {near:.1%} (the random pool: {pool_near:.1%}); truly good {np.mean([p['good'] for p in sel]):.1%}")
    ds = np.array([p["distance"] for p in picks])
    print(f"\ndistance to the nearest pre-shift anchor, in the engine's 0-1 scaled space ({len(ds)} picks): median {np.median(ds):.3f}, quartiles {np.quantile(ds, 0.25):.3f} to {np.quantile(ds, 0.75):.3f}")
    allnear = np.mean([p["distance"] <= NEAR for p in picks])
    print(f"share of ALL stale-exploration picks within {NEAR} of an anchor: {allnear:.1%}; of the random pool: {np.mean([p['pool_near_share'] for p in picks]):.1%}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=("replay", "analyse"))
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    return replay(args.jobs) if args.job == "replay" else analyse()


if __name__ == "__main__":
    sys.exit(main())
