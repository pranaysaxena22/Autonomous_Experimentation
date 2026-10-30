r"""The rule-5 recalibration test (docs/decisions.md, "PROPOSAL ... a change to rule 5's response", approved 2026-10-12, with the early-window clarification and the added condition N4).

  calibrate   sets the size of the RESHAPED scenario using the UNGOVERNED engine only (seeds 11300 to 11320): N1 (it is a reshaping), N2 (it hurts an engine that ignores it), N3 (still winnable), N4 (the
              watch's rule fires on the ungoverned engine's own hit sequences in at least 19 of 20 campaigns). The smallest size meeting all four is written to runs\followup\recal\calibration.json; none = stop.
  run         the test, once: period_shift and reshaped (80 paired campaigns, seeds 11400 to 11479; arms G0, R, N, ungoverned) and baseline, new_supplier, unpredictable_dissolution (40 campaigns, seeds 11400 to 11439;
              arms G0 and R). Each campaign is saved as it finishes, so a stopped run carries on.
  report      the success conditions P1 to P4 exactly as fixed, and everything else the record says will be reported.

Run:  .venv\Scripts\python.exe tools\stage4_recalibration_test.py calibrate   (then run, then report)
Synthetic data and development seeds only; the sealed acceptance lab is never touched.
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

from cellpoc.comparison.dev_comparison import paired_difference, verdict  # noqa: E402
from cellpoc.contracts import EngineBrief, Observation  # noqa: E402
from cellpoc.decision_engine.baselines import UngovernedStrategy  # noqa: E402
from cellpoc.decision_engine.governed import GovernedStrategy  # noqa: E402
from cellpoc.decision_engine.recalibrated import RecalibratedStrategy  # noqa: E402
from cellpoc.scoring import score_dev_trial  # noqa: E402
from cellpoc.virtual_lab import dev_oracle  # noqa: E402
from cellpoc.virtual_lab.dev_lab import DESIGN_SPACE, FILLER_RANGE, HISTORY_EXPERIMENTS, HISTORY_SEEDS, INGREDIENTS, SCENARIOS, DevLab, cleaned_history, reshaped, target_specs  # noqa: E402

OUT = ROOT / "runs" / "followup" / "recal"
TRIALS = 30
GRID = (0.5, 0.75, 1.0, 1.5)                                              # fixed in docs/decisions.md before any run
CAL_SEEDS, CAL_RANDOM_SEED, CAL_RANDOM_N = tuple(range(11300, 11320)), 11320, 20000
TEST_SEEDS_80, TEST_SEEDS_40 = tuple(range(11400, 11480)), tuple(range(11400, 11440))
T = ("dissolution_30min_pct", "hardness_kp", "friability_pct")
P1_MIN, P2_MIN, P4_HIT, P4_CHANCE_GOOD = 7.0, -3.0, 0.75, 0.90


def scenario_of(name: str, k: float | None):
    return reshaped(k) if name == "reshaped" else SCENARIOS[name]


def base_of(name: str) -> str:
    """The scenario whose history and brief a scenario uses (the reshaped scenario shares period_shift's)."""
    return "period_shift" if name == "reshaped" else name


def run_one(name: str, k: float | None, strategy: str, seed: int, out_dir: str, label: str) -> dict:
    from threadpoolctl import threadpool_limits

    path = Path(out_dir) / "cache" / f"{label}_{strategy}_{seed}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    base = base_of(name)
    brief = EngineBrief.from_json((ROOT / "runs" / "devlab" / f"brief_dev_{base}.json").read_text(encoding="utf-8"))
    specs = target_specs()
    with threadpool_limits(limits=1):
        history = cleaned_history(DevLab(SCENARIOS[base], HISTORY_SEEDS[base]), HISTORY_EXPERIMENTS)
        args = (brief, specs, history, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)
        engine = {"g0": lambda: GovernedStrategy(*args), "r": lambda: RecalibratedStrategy(*args), "n": lambda: RecalibratedStrategy(*args, naive=True), "ungoverned": lambda: UngovernedStrategy(*args)}[strategy]()
        lab = DevLab(scenario_of(name, k), seed)
        obs, rows = [], []
        for t in range(1, TRIALS + 1):
            ctx = lab.context(t)
            d = engine.propose(t, ctx, obs)
            m = lab.measure(t, d.recipe, ctx)
            obs.append(Observation(t, d.recipe, ctx, m))
            row = {"good": bool(score_dev_trial(lab, specs, t, d.recipe, ctx, m).good), "kind": d.kind, "stale": list(d.stale), "chances": dict(d.chances),
                   "ranges": {r: list(v) for r, v in d.stated_ranges.items()}, "measured": {r: float(v) for r, v in m.items()}}
            log = getattr(engine, "recal_log", {}).get(t)
            row["watch_stale"] = list(log["watch_stale"]) if log is not None else list(d.stale)                # what the watch's own rule said at this decision
            if log is not None:
                row["recal"] = {"classes": log["classes"], "offsets": log["offsets"], "gate": log["gate"], "best_chance": log["best_chance"]}
            rows.append(row)
    rec = {"scenario": name, "k": k, "strategy": strategy, "seed": seed, "trusted": len(engine.trusted), "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def run_many(tasks: list, jobs: int) -> list:
    from joblib import Parallel, delayed

    started, out = time.time(), []
    for start in range(0, len(tasks), jobs * 4):
        out += Parallel(n_jobs=jobs)(delayed(run_one)(*t) for t in tasks[start:start + jobs * 4])
        print(f"  {len(out)} of {len(tasks)} campaigns done ({(time.time() - started) / 60:.1f} min)", flush=True)
    return out


# ---------------------------------------------------------------- the watch's own rule on a recorded run
def watch_states(rec: dict) -> dict:
    """For each target, from the recorded stated ranges and measurements: stale at decision d (13 to 30) if at most 7 of the last 12 checks (trials d-12 to d-1) hit."""
    out = {}
    for t in T:
        hits = [row["ranges"][t][0] <= row["measured"][t] <= row["ranges"][t][1] for row in rec["rows"] if t in row["ranges"]]
        out[t] = {d: sum(hits[d - 13:d - 1]) <= 7 for d in range(13, 31)}
    return out


# ---------------------------------------------------------------- calibrate
def calibrate(jobs: int) -> int:
    tasks = [("reshaped", k, "ungoverned", s, str(OUT), f"cal_k{k}") for k in GRID for s in CAL_SEEDS]
    recs = run_many(tasks, jobs)
    table, chosen = [], None
    for k in GRID:
        mine = [r for r in recs if r["k"] == k]
        stats = dev_oracle.reshape_statistics(CAL_RANDOM_N, CAL_RANDOM_SEED, k)
        before = float(np.mean([[row["good"] for row in r["rows"][:5]] for r in mine]))
        after = float(np.mean([[row["good"] for row in r["rows"][5:]] for r in mine]))
        ratio = after / before if before else float("nan")
        fired, first, per_target = 0, [], {t: 0 for t in T}
        for r in mine:
            states = watch_states(r)
            any_first = [min((d for d, v in states[t].items() if v), default=None) for t in T]
            for t, f in zip(T, any_first):
                per_target[t] += f is not None
            hit = [f for f in any_first if f is not None]
            if hit:
                fired += 1
                first.append(min(hit))
        n1 = stats["spearman"] <= 0.6 and stats["up_share"] >= 0.25 and stats["down_share"] >= 0.25
        n2 = ratio <= 0.5
        n3 = stats["good_share_after"] >= 0.005
        n4 = fired >= 19
        row = {"k": k, **stats, "before": before, "after": after, "ratio": ratio, "fired": fired, "median_first_decision": float(np.median(first)) if first else None, "fired_by_target": per_target,
               "N1": bool(n1), "N2": bool(n2), "N3": bool(n3), "N4": bool(n4)}
        table.append(row)
        if chosen is None and n1 and n2 and n3 and n4:
            chosen = k
    print("\nSize k | rank correlation (N1: <= 0.6) | gain > 3 / lose > 3 (N1: each >= 25%) | ungoverned good 1-5 -> 6-30, ratio (N2: <= 0.5) | random recipes good after (N3: >= 0.5%) | watch fires, of 20 (N4: >= 19), median first decision | N1 N2 N3 N4")
    for r in table:
        print(f"  {r['k']:.2f} | {r['spearman']:.2f} | {r['up_share']:.0%} / {r['down_share']:.0%} | {r['before']:.0%} -> {r['after']:.0%}, {r['ratio']:.2f} | {r['good_share_after']:.2%} | {r['fired']} (by target {r['fired_by_target']}), {r['median_first_decision']} | "
              f"{'yes' if r['N1'] else 'no'} {'yes' if r['N2'] else 'no'} {'yes' if r['N3'] else 'no'} {'yes' if r['N4'] else 'no'}")
    print(f"\nSmallest size meeting N1, N2, N3 and N4: {chosen if chosen is not None else 'NONE: stop and report'}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calibration.json").write_text(json.dumps({"grid": GRID, "seeds": [CAL_SEEDS[0], CAL_SEEDS[-1]], "table": table, "chosen_k": chosen}, indent=1), encoding="utf-8")
    return 0


# ---------------------------------------------------------------- the test
def chosen_k() -> float:
    cal = json.loads((OUT / "calibration.json").read_text(encoding="utf-8"))
    if cal.get("chosen_k") is None:
        raise SystemExit("The reshaped scenario was not calibrated (no size met N1 to N4): the test does not run.")
    return float(cal["chosen_k"])


def plan(partial: bool = False) -> list:
    """The campaigns of the test. `partial` (decided 2026-10-12, docs/decisions.md): no reshaped scenario and no N arm; period_shift with G0, R and the ungoverned engine, and the three no-harm scenarios with G0 and R."""
    k = None if partial else chosen_k()
    tasks = []
    for name in (("period_shift",) if partial else ("period_shift", "reshaped")):
        for st in (("g0", "r", "ungoverned") if partial else ("g0", "r", "n", "ungoverned")):
            tasks += [(name, k if name == "reshaped" else None, st, s, str(OUT), name) for s in TEST_SEEDS_80]
    for name in ("baseline", "new_supplier", "unpredictable_dissolution"):
        for st in ("g0", "r"):
            tasks += [(name, None, st, s, str(OUT), name) for s in TEST_SEEDS_40]
    return tasks


def run(jobs: int, partial: bool = False) -> int:
    tasks = plan(partial)
    print(f"{len(tasks)} campaigns" + ("" if partial else f" (reshaped size k = {chosen_k()})") + (" [partial: no reshaped scenario, no N arm]" if partial else ""))
    run_many(tasks, jobs)
    return 0


def _load(name: str, strategy: str, seeds) -> list:
    return [json.loads((OUT / "cache" / f"{name}_{strategy}_{s}.json").read_text(encoding="utf-8")) for s in seeds]


def _head(recs: list) -> list:
    return [sum(row["good"] for row in r["rows"]) for r in recs]


def _firing(recs: list) -> str:
    firsts = [next((t for t, row in enumerate(r["rows"], 1) if row["watch_stale"]), None) for r in recs]
    fired = [f for f in firsts if f]
    return f"fired in {len(fired)} of {len(recs)}" + (f" (first decision median {np.median(fired):.0f}, range {min(fired)} to {max(fired)})" if fired else "")


def report() -> int:
    k = chosen_k()
    L = []
    fmt = lambda h: f"{np.mean(h):.1f} ({min(h)} to {max(h)})"
    res = {}
    L.append(f"THE RULE-5 RECALIBRATION TEST [SYNTHETIC DATA]: seeds 11400 to 11479 (period_shift and reshaped, 80 paired campaigns) and 11400 to 11439 (the other three, 40); reshaped size k = {k}; truly good recipes per 30-trial campaign (min to max)\n")
    L.append("| Scenario | G0 (current) | R | N (naive) | Ungoverned | R minus G0 (95% interval; wins/ties/losses) | verdict | N minus G0 (95% interval) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name in ("period_shift", "reshaped", "baseline", "new_supplier", "unpredictable_dissolution"):
        seeds = TEST_SEEDS_80 if name in ("period_shift", "reshaped") else TEST_SEEDS_40
        recs = {st: _load(name, st, seeds) for st in (("g0", "r", "n", "ungoverned") if name in ("period_shift", "reshaped") else ("g0", "r"))}
        head = {st: _head(v) for st, v in recs.items()}
        d = paired_difference(head["r"], head["g0"])
        res[name] = {"d": d, "v": verdict(d["lo"], d["hi"]), "recs": recs, "head": head}
        n_txt = u_txt = "-"
        dn = None
        if "n" in head:
            dn = paired_difference(head["n"], head["g0"])
            n_txt, u_txt = fmt(head["n"]), fmt(head["ungoverned"])
        L.append(f"| {name} | {fmt(head['g0'])} | {fmt(head['r'])} | {n_txt} | {u_txt} | **{d['mean']:+.2f}** ({d['lo']:+.2f} to {d['hi']:+.2f}; {d['wins']}/{d['ties']}/{d['losses']}) | **{res[name]['v']}** | "
                 + (f"{dn['mean']:+.2f} ({dn['lo']:+.2f} to {dn['hi']:+.2f}; {verdict(dn['lo'], dn['hi'])})" if dn else "-") + " |")
    # ---- P4
    pr = res["period_shift"]["recs"]["r"]
    rc_hits = [row["ranges"][t][0] <= row["measured"][t] <= row["ranges"][t][1] for r in pr for row in r["rows"] if row.get("recal") and row["recal"]["gate"] is None for t in row["recal"]["offsets"]]
    conf = [row["good"] for r in pr for row in r["rows"] if row["chances"].get("all_targets", 0.0) >= 0.8]
    p4a = float(np.mean(rc_hits)) if rc_hits else float("nan")
    p4b = float(np.mean(conf)) if conf else float("nan")
    # ---- the conditions
    p1 = res["period_shift"]["d"]["lo"] >= P1_MIN
    p2 = res["reshaped"]["d"]["lo"] >= P2_MIN
    p3 = {n: res[n]["v"] != "worse" for n in ("baseline", "new_supplier", "unpredictable_dissolution")}
    p4 = rc_hits != [] and p4a >= P4_HIT and conf != [] and p4b >= P4_CHANCE_GOOD
    L.append("\n## The success conditions, exactly as fixed in advance")
    d1, d2 = res["period_shift"]["d"], res["reshaped"]["d"]
    L.append(f"- **P1** (period_shift, R minus G0: the interval's lower end at least +{P1_MIN:.0f}): {d1['mean']:+.2f}, interval {d1['lo']:+.2f} to {d1['hi']:+.2f} -> **{'MET' if p1 else 'NOT MET'}**")
    L.append(f"- **P2** (reshaped, R minus G0: the interval's lower end at least {P2_MIN:+.0f}): {d2['mean']:+.2f}, interval {d2['lo']:+.2f} to {d2['hi']:+.2f} -> **{'MET' if p2 else 'NOT MET'}**")
    for n, ok in p3.items():
        d = res[n]["d"]
        L.append(f"- **P3** ({n}: R minus G0 not 'worse'): {d['mean']:+.2f} ({d['lo']:+.2f} to {d['hi']:+.2f}), verdict '{res[n]['v']}' -> **{'MET' if ok else 'NOT MET'}**")
    L.append(f"- **P4** (in period_shift: at least {P4_HIT:.0%} of measurements inside the re-centred range over the trials in which R re-centred, and at least {P4_CHANCE_GOOD:.0%} of the decisions stating a chance of at least 0.8 truly good): "
             f"{p4a:.1%} of {len(rc_hits):,} re-centred checks inside; {p4b:.1%} of {len(conf):,} decisions with a stated chance of at least 0.8 truly good -> **{'MET' if p4 else 'NOT MET'}**")
    allmet = p1 and p2 and all(p3.values()) and p4
    if allmet:
        outcome = "A GENUINE IMPROVEMENT TO RULE 5 (P1, P2, P3 and P4 all met; adoption itself is a separate approval)"
    elif p1 and not p2:
        outcome = "WORKS FOR ONE KIND OF SHIFT AND IS NOT A SAFE GENERAL FIX (P1 met, P2 not met): not adopted as a general rule"
    elif not p1:
        outcome = "DOES NOT HELP (P1 not met): not adopted"
    else:
        outcome = "P1 and P2 met but " + ", ".join(n for n, ok in p3.items() if not ok) + (" and P4" if not p4 else "") + " not met: not adopted"
    L.append(f"\n**Outcome by the table fixed in advance: {outcome}.**")
    # ---- everything else the record says is reported
    L.append("\n## Reported without a pass mark")
    for name in ("period_shift", "reshaped"):
        recs = res[name]["recs"]
        L.append(f"- **The watch, {name}:** " + "; ".join(f"{st}: {_firing(recs[st])}" for st in ("g0", "r", "n")) + ". (Pre-stated: it should fire in at least 95% of the reshaped G0 campaigns.)")
        first = [next((row for row in r["rows"] if row.get("recal") and row["watch_stale"]), None) for r in recs["r"]]
        cls = {}
        for row in first:
            if row:
                for t, c in row["recal"]["classes"].items():
                    cls[c] = cls.get(c, 0) + 1
        L.append(f"- **R's evidence classes at the first stale decision, {name}:** {cls} (one count per stale target per campaign)")
        allc = {}
        gate = 0
        for r in recs["r"]:
            for row in r["rows"]:
                if row.get("recal") and row["watch_stale"]:
                    gate += row["recal"]["gate"] == "fallback"
                    for t, c in row["recal"]["classes"].items():
                        allc[c] = allc.get(c, 0) + 1
        L.append(f"- **R's evidence classes over every stale decision, {name}:** {allc}; promise check sent a decision to exploration {gate} times in {len(recs['r'])} campaigns")
        blocks = []
        for a, b in ((6, 12), (13, 18), (19, 24), (25, 30)):
            row_txt = ", ".join(f"{st} {np.mean([sum(not x['good'] for x in r['rows'][a - 1:b]) for r in recs[st]]):.2f}" for st in ("g0", "r", "n", "ungoverned"))
            blocks.append(f"trials {a} to {b}: {row_txt}")
        L.append(f"- **Not-good trials per campaign by block, {name} (is R helping right after the watch fires, or only later?):** " + "; ".join(blocks))
        u, g = res[name]["head"]["ungoverned"], res[name]["head"]["g0"]
        gap = np.mean(u) - np.mean(g)
        L.append(f"- **Share of the gap between G0 and the ungoverned engine closed, {name}:** R {((np.mean(res[name]['head']['r']) - np.mean(g)) / gap if gap > 0 else float('nan')):.0%}, N {((np.mean(res[name]['head']['n']) - np.mean(g)) / gap if gap > 0 else float('nan')):.0%} "
                 f"(G0 {np.mean(g):.1f}, ungoverned {np.mean(u):.1f}); G0 minus ungoverned {paired_difference(g, u)['mean']:+.2f} ({paired_difference(g, u)['lo']:+.2f} to {paired_difference(g, u)['hi']:+.2f})")
    L.append(f"- **R's lower interval end in the other three scenarios (the stricter reading of P3):** " + ", ".join(f"{n} {res[n]['d']['lo']:+.2f}" for n in p3))
    text = "\n".join(L)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def report_partial() -> int:
    """The partial test decided on 2026-10-12 (docs/decisions.md): period_shift with G0, R and the ungoverned engine (P1, P4) and the three no-harm scenarios with G0 and R (P3). P2 is not evaluated."""
    fmt = lambda h: f"{np.mean(h):.1f} ({min(h)} to {max(h)})"
    L, res = [], {}
    L.append("THE RULE-5 RECALIBRATION TEST, PARTIAL (no reshaped scenario) [SYNTHETIC DATA]: seeds 11400 to 11479 (period_shift, 80 paired campaigns) and 11400 to 11439 (the other three, 40); truly good recipes per 30-trial campaign (min to max)\n")
    L.append("| Scenario | G0 (current) | R | Ungoverned | R minus G0 (95% interval; wins/ties/losses) | verdict |")
    L.append("|---|---|---|---|---|---|")
    for name in ("period_shift", "baseline", "new_supplier", "unpredictable_dissolution"):
        seeds = TEST_SEEDS_80 if name == "period_shift" else TEST_SEEDS_40
        recs = {st: _load(name, st, seeds) for st in (("g0", "r", "ungoverned") if name == "period_shift" else ("g0", "r"))}
        head = {st: _head(v) for st, v in recs.items()}
        d = paired_difference(head["r"], head["g0"])
        res[name] = {"d": d, "v": verdict(d["lo"], d["hi"]), "recs": recs, "head": head}
        L.append(f"| {name} | {fmt(head['g0'])} | {fmt(head['r'])} | {fmt(head['ungoverned']) if 'ungoverned' in head else '-'} | **{d['mean']:+.2f}** ({d['lo']:+.2f} to {d['hi']:+.2f}; {d['wins']}/{d['ties']}/{d['losses']}) | **{res[name]['v']}** |")
    pr = res["period_shift"]["recs"]["r"]
    rc_hits = [row["ranges"][t][0] <= row["measured"][t] <= row["ranges"][t][1] for r in pr for row in r["rows"] if row.get("recal") and row["recal"]["gate"] is None for t in row["recal"]["offsets"]]
    conf = [row["good"] for r in pr for row in r["rows"] if row["chances"].get("all_targets", 0.0) >= 0.8]
    p4a = float(np.mean(rc_hits)) if rc_hits else float("nan")
    p4b = float(np.mean(conf)) if conf else float("nan")
    d1 = res["period_shift"]["d"]
    p1 = d1["lo"] >= P1_MIN
    p3 = {n: res[n]["v"] != "worse" for n in ("baseline", "new_supplier", "unpredictable_dissolution")}
    p4 = bool(rc_hits) and p4a >= P4_HIT and bool(conf) and p4b >= P4_CHANCE_GOOD
    L.append("\n## The success conditions, exactly as fixed in advance (P2 is not evaluated: it needs the reshaped scenario, which was not built)")
    L.append(f"- **P1** (period_shift, R minus G0: the interval's lower end at least +{P1_MIN:.0f}): {d1['mean']:+.2f}, interval {d1['lo']:+.2f} to {d1['hi']:+.2f} -> **{'MET' if p1 else 'NOT MET'}**")
    for n, ok in p3.items():
        d = res[n]["d"]
        L.append(f"- **P3** ({n}: R minus G0 not 'worse'): {d['mean']:+.2f} ({d['lo']:+.2f} to {d['hi']:+.2f}), verdict '{res[n]['v']}' -> **{'MET' if ok else 'NOT MET'}**; the stricter reading (lower end at or above 0): {'met' if d['lo'] >= 0 else 'not met'}")
    L.append(f"- **P4** (in period_shift: at least {P4_HIT:.0%} of measurements inside the re-centred range over the trials in which R re-centred, and at least {P4_CHANCE_GOOD:.0%} of the decisions stating a chance of at least 0.8 truly good): "
             f"{p4a:.1%} of {len(rc_hits):,} re-centred checks inside; {p4b:.1%} of {len(conf):,} decisions with a stated chance of at least 0.8 truly good -> **{'MET' if p4 else 'NOT MET'}**")
    if p1 and all(p3.values()) and p4:
        verdict_text = ("R demonstrably fixes the specific problem it was designed for (offset shifts breaking calibration while ranking stays valid), with no harm shown in the other three scenarios. It is NOT shown to be a general fix for rule 5, "
                        "since no reshaping (ranking-breaking) scenario has been found that both breaks the ungoverned engine and remains winnable. (Limits: one mild uniform step, one size of it, in one synthetic lab; adoption itself is a separate approval.)")
    elif not p1 or not all(p3.values()):
        verdict_text = "R is NOT ADOPTED in any form, full stop (" + ", ".join(x for x, ok in (("P1 not met", p1), ("P3 not met in " + ", ".join(n for n, o in p3.items() if not o), all(p3.values()))) if not ok) + ")."
    else:
        verdict_text = "P1 and P3 are met but P4 is not: R is NOT ADOPTED."
    L.append(f"\n**Verdict, by the wording fixed in advance: {verdict_text}**")
    L.append("\n## Reported without a pass mark")
    recs = res["period_shift"]["recs"]
    L.append("- **The watch, period_shift:** " + "; ".join(f"{st}: {_firing(recs[st])}" for st in ("g0", "r")) + ".")
    for name in ("period_shift", "baseline", "new_supplier", "unpredictable_dissolution"):
        rr = res[name]["recs"]["r"]
        first, allc, gate = {}, {}, 0
        for r in rr:
            f = next((row for row in r["rows"] if row.get("recal") and row["watch_stale"]), None)
            if f:
                for t, c in f["recal"]["classes"].items():
                    first[c] = first.get(c, 0) + 1
            for row in r["rows"]:
                if row.get("recal") and row["watch_stale"]:
                    gate += row["recal"]["gate"] == "fallback"
                    for t, c in row["recal"]["classes"].items():
                        allc[c] = allc.get(c, 0) + 1
        fired = sum(1 for r in rr if any(row["watch_stale"] for row in r["rows"]))
        L.append(f"- **R, {name}:** the watch fired in {fired} of {len(rr)} campaigns; evidence classes at the first stale decision {first}; over every stale decision {allc}; promise check sent a decision to exploration {gate} times")
    blocks = []
    for a, b in ((6, 12), (13, 18), (19, 24), (25, 30)):
        blocks.append(f"trials {a} to {b}: " + ", ".join(f"{st} {np.mean([sum(not x['good'] for x in r['rows'][a - 1:b]) for r in recs[st]]):.2f}" for st in ("g0", "r", "ungoverned")))
    L.append("- **Not-good trials per campaign by block, period_shift (is R helping right after the watch fires, or only later?):** " + "; ".join(blocks))
    g, u, rh = res["period_shift"]["head"]["g0"], res["period_shift"]["head"]["ungoverned"], res["period_shift"]["head"]["r"]
    gap = np.mean(u) - np.mean(g)
    du = paired_difference(rh, u)
    L.append(f"- **Share of the gap between G0 and the ungoverned engine closed, period_shift:** R {((np.mean(rh) - np.mean(g)) / gap if gap > 0 else float('nan')):.0%} (G0 {np.mean(g):.1f}, R {np.mean(rh):.1f}, ungoverned {np.mean(u):.1f}); R minus ungoverned {du['mean']:+.2f} ({du['lo']:+.2f} to {du['hi']:+.2f})")
    text = "\n".join(L)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary_partial.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=("calibrate", "run", "report"))
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--partial", action="store_true", help="the partial test decided on 2026-10-12: no reshaped scenario, no N arm (period_shift with G0, R, ungoverned; the three no-harm scenarios with G0, R)")
    args = parser.parse_args()
    if args.job == "report":
        return report_partial() if args.partial else report()
    return {"calibrate": lambda: calibrate(args.jobs), "run": lambda: run(args.jobs, args.partial)}[args.job]()


if __name__ == "__main__":
    sys.exit(main())
