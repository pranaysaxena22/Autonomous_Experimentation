r"""The all-stale exploration test (docs/decisions.md, "The all-stale exploration change: approved, with S1 and S2 tightened"): 4 scenarios x 40 paired campaigns (seeds 11000 to 11039) x 3 strategies.

  G0         the governed engine exactly as committed at f647f5d (every modelled target stale: always the farthest candidate), loaded from a copy made at run time under runs\followup\g0\ (not kept in the project)
  G1         the governed engine as changed (every modelled target stale: alternate the farthest candidate with a local search near the best measured passes, the engine's existing rule 2)
  ungoverned the same models without governance (it never enters the changed branch, so it is the same engine as in 4-4)

Run:  .venv\Scripts\python.exe tools\stage4_exploration_test.py run        (about 20 minutes on 6 cores; each campaign is saved as it finishes, so a stopped run carries on)
      .venv\Scripts\python.exe tools\stage4_exploration_test.py report     (the success conditions S1, S2 and S3 exactly as fixed in advance)
Synthetic data only; development seeds only; the sealed acceptance lab is never touched.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.comparison.dev_comparison import EVENT_TRIAL, paired_difference, verdict  # noqa: E402
from cellpoc.contracts import EngineBrief, Observation  # noqa: E402
from cellpoc.decision_engine.baselines import UngovernedStrategy  # noqa: E402
from cellpoc.decision_engine.governed import GovernedStrategy  # noqa: E402
from cellpoc.scoring import score_dev_trial  # noqa: E402
from cellpoc.virtual_lab.dev_lab import DESIGN_SPACE, FILLER_RANGE, HISTORY_EXPERIMENTS, HISTORY_SEEDS, INGREDIENTS, SCENARIOS, DevLab, cleaned_history, target_specs  # noqa: E402

G0_DIR = ROOT / "runs" / "followup" / "g0"
G0_COMMIT = "f647f5d"
# the two tests: the first (seeds 11000 to 11039, all four scenarios; result: S1 not met, change reverted) and the second, pre-registered separately in docs/decisions.md (seeds 11100 to 11179, period_shift only)
SETS = {"first": {"out": ROOT / "runs" / "followup" / "exploration_test", "seeds": tuple(range(11000, 11040)), "scenarios": tuple(SCENARIOS)},
        "second": {"out": ROOT / "runs" / "followup" / "exploration_test_2", "seeds": tuple(range(11100, 11180)), "scenarios": ("period_shift",)}}
OUT, SEEDS, SCENARIO_NAMES = SETS["first"]["out"], SETS["first"]["seeds"], SETS["first"]["scenarios"]


def select(name: str) -> None:
    global OUT, SEEDS, SCENARIO_NAMES
    OUT, SEEDS, SCENARIO_NAMES = SETS[name]["out"], SETS[name]["seeds"], SETS[name]["scenarios"]


STRATEGIES = ("g0", "g1", "ungoverned")
TRIALS, S1_MIN = 30, 5.0
_g0_class = None


def load_g0():
    """The committed engine, byte for byte, with its relative imports made absolute so it can sit outside the package. Returns (class, the number of lines that differ from the current governed.py)."""
    global _g0_class
    if _g0_class is not None:
        return _g0_class
    raw = subprocess.run(["git", "show", f"{G0_COMMIT}:cellpoc/decision_engine/governed.py"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    fix = lambda text: (text.replace("from ..contracts", "from cellpoc.contracts").replace("from ..modelling", "from cellpoc.modelling").replace("from .adaptive", "from cellpoc.decision_engine.adaptive"))
    G0_DIR.mkdir(parents=True, exist_ok=True)
    path = G0_DIR / "governed_g0.py"
    data = fix(raw).replace("\r\n", "\n").encode("utf-8")
    if not path.exists() or path.read_bytes() != data:                            # written once by the main process before the workers start, never rewritten while they read it
        path.write_bytes(data)
    spec = importlib.util.spec_from_file_location("governed_g0", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["governed_g0"] = module
    spec.loader.exec_module(module)
    _g0_class = module.GovernedStrategy
    return _g0_class


def g0_difference() -> list:
    """The lines on which G0 and the current governed.py differ (should be exactly the all-stale branch)."""
    load_g0()
    old = (G0_DIR / "governed_g0.py").read_text(encoding="utf-8").splitlines()
    new = (ROOT / "cellpoc" / "decision_engine" / "governed.py").read_text(encoding="utf-8").replace("from ..contracts", "from cellpoc.contracts").replace("from ..modelling", "from cellpoc.modelling").replace("from .adaptive", "from cellpoc.decision_engine.adaptive").splitlines()
    return [line for line in difflib.unified_diff(old, new, lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def run_one(scenario: str, strategy: str, seed: int, out: Path) -> dict:
    from threadpoolctl import threadpool_limits

    path = out / "cache" / f"{scenario}_{strategy}_{seed}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    brief = EngineBrief.from_json((ROOT / "runs" / "devlab" / f"brief_dev_{scenario}.json").read_text(encoding="utf-8"))
    specs = target_specs()
    cls = {"g0": load_g0, "g1": lambda: GovernedStrategy, "ungoverned": lambda: UngovernedStrategy}[strategy]()
    with threadpool_limits(limits=1):
        history = cleaned_history(DevLab(SCENARIOS[scenario], HISTORY_SEEDS[scenario]), HISTORY_EXPERIMENTS)
        engine = cls(brief, specs, history, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)
        lab = DevLab(SCENARIOS[scenario], seed)
        obs, rows = [], []
        for t in range(1, TRIALS + 1):
            ctx = lab.context(t)
            d = engine.propose(t, ctx, obs)
            m = lab.measure(t, d.recipe, ctx)
            obs.append(Observation(t, d.recipe, ctx, m))
            rows.append({"good": bool(score_dev_trial(lab, specs, t, d.recipe, ctx, m).good), "kind": d.kind, "stale": list(d.stale)})
    rec = {"scenario": scenario, "strategy": strategy, "seed": seed, "trusted": len(engine.trusted), "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def run(jobs: int) -> int:
    from joblib import Parallel, delayed

    diff = g0_difference()
    print(f"G0 (commit {G0_COMMIT}) against the current governed.py: {len([d for d in diff if d[0] == '-'])} line(s) removed, {len([d for d in diff if d[0] == '+'])} added:")
    for line in diff:
        print("   " + line[:160])
    if len(diff) != 4 or "_farthest(unit, everything, rows)" not in " ".join(d for d in diff if d[0] == "-"):
        print("\nG0 and G1 differ by something other than the approved change: STOP.")
        return 2
    global _g0_class
    _g0_class = None                                                              # each worker loads its own copy; the parent must not hand the loaded class to them
    sys.modules.pop("governed_g0", None)
    out = OUT
    tasks = [(s, st, seed, out) for s in SCENARIO_NAMES for st in STRATEGIES for seed in SEEDS]
    started, done = time.time(), 0
    for start in range(0, len(tasks), jobs * 4):
        chunk = tasks[start:start + jobs * 4]
        Parallel(n_jobs=jobs)(delayed(run_one)(*t) for t in chunk)
        done += len(chunk)
        print(f"  {done} of {len(tasks)} campaigns done ({(time.time() - started) / 60:.1f} min)", flush=True)
    return 0


def _load(scenario: str, strategy: str) -> list:
    return [json.loads((OUT / "cache" / f"{scenario}_{strategy}_{s}.json").read_text(encoding="utf-8")) for s in SEEDS]


def report() -> int:
    lines, s1, s2 = [], None, {}
    lines.append(f"THE ALL-STALE EXPLORATION TEST [SYNTHETIC DATA]: seeds {SEEDS[0]} to {SEEDS[-1]}, {len(SEEDS)} paired campaigns per scenario, 30 trials; truly good recipes per campaign (min to max)\n")
    lines.append("| Scenario | G0 (current) | G1 (changed) | Ungoverned | G1 minus G0 (95% interval; wins/ties/losses) | verdict | G1 minus ungoverned | share of the gap to ungoverned closed |")
    lines.append("|---|---|---|---|---|---|---|---|")
    extra = []
    for sc in SCENARIO_NAMES:
        recs = {st: _load(sc, st) for st in STRATEGIES}
        head = {st: [sum(r_["good"] for r_ in r["rows"]) for r in recs[st]] for st in STRATEGIES}
        d = paired_difference(head["g1"], head["g0"])
        v = verdict(d["lo"], d["hi"])
        du = paired_difference(head["g1"], head["ungoverned"])
        gap = float(np.mean(head["ungoverned"]) - np.mean(head["g0"]))
        closed = f"{d['mean'] / gap:.0%}" if gap > 0 else "n/a (ungoverned not ahead)"
        fmt = lambda h: f"{np.mean(h):.1f} ({min(h)} to {max(h)})"
        lines.append(f"| {sc} | {fmt(head['g0'])} | {fmt(head['g1'])} | {fmt(head['ungoverned'])} | **{d['mean']:+.2f}** ({d['lo']:+.2f} to {d['hi']:+.2f}; {d['wins']}/{d['ties']}/{d['losses']}) | **{v}** | {du['mean']:+.2f} ({du['lo']:+.2f} to {du['hi']:+.2f}) | {closed} |")
        if sc == "period_shift":
            s1 = (d["mean"] >= S1_MIN and d["lo"] >= S1_MIN, d)
        else:
            s2[sc] = (v != "worse", d["lo"] >= 0, d, v)
        e = EVENT_TRIAL.get(sc)
        if e:
            after = {st: np.mean([sum(r_["good"] for r_ in r["rows"][e - 1:]) for r in recs[st]]) for st in STRATEGIES}
            extra.append(f"- {sc}: truly good from trial {e} on (of {TRIALS - e + 1}): G0 {after['g0']:.1f}, G1 {after['g1']:.1f}, ungoverned {after['ungoverned']:.1f}")
        for st in ("g0", "g1"):
            picks = [(row["good"]) for r in recs[st] for row in r["rows"] if row["kind"] == "stale_exploration" and len(row["stale"]) == r["trusted"]]
            allk = [row["kind"] for r in recs[st] for row in r["rows"]]
            extra.append(f"- {sc}, {st}: picks made while every modelled target was stale: {len(picks)} ({len(picks) / len(SEEDS):.1f} per campaign), truly good {np.mean(picks):.1%}" if picks else f"- {sc}, {st}: no picks made while every modelled target was stale; stale-exploration picks {allk.count('stale_exploration')} in all")
    lines.append("\nReported without a pass mark (S3):\n" + "\n".join(extra))
    ok1 = s1[0]
    ok2 = all(v[0] for v in s2.values())
    lines.append("\n## The success conditions, exactly as fixed in advance")
    lines.append(f"- **S1** (period_shift: mean at least +5 AND the interval's lower end at least +5): mean {s1[1]['mean']:+.2f}, interval {s1[1]['lo']:+.2f} to {s1[1]['hi']:+.2f} -> **{'MET' if ok1 else 'NOT MET'}**")
    for sc, (ok, strict, d, v) in s2.items():
        lines.append(f"- **S2** ({sc}: the interval must not be wholly below 0, i.e. the verdict must not be 'worse'): {d['mean']:+.2f} ({d['lo']:+.2f} to {d['hi']:+.2f}), verdict '{v}' -> **{'MET' if ok else 'NOT MET'}**; the stricter reading (lower end at or above 0): {'met' if strict else 'not met'}")
    if s2:
        lines.append(f"\n**S1 {'met' if ok1 else 'NOT met'}, S2 {'met in all three' if ok2 else 'NOT met in every scenario'}: the change is {'ADOPTED' if ok1 and ok2 else 'NOT ADOPTED (both must hold)'}.**")
    else:                                                                          # the second test: period_shift only; S2 was met in the first test and is not re-run
        lines.append(f"\n**S1 {'met' if ok1 else 'NOT met'} (the second test, period_shift only; S2 is not re-run, it was met in the first test): the change is {'ADOPTED' if ok1 else 'NOT ADOPTED'}.**")
    text = "\n".join(lines)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=("run", "report"))
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--set", choices=tuple(SETS), default="first", help="'first' (seeds 11000 to 11039, four scenarios) or 'second' (seeds 11100 to 11179, period_shift only)")
    args = parser.parse_args()
    select(args.set)
    return run(args.jobs) if args.job == "run" else report()


if __name__ == "__main__":
    sys.exit(main())
