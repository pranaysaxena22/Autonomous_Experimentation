r"""Rules 3 and 4 diagnosis from the STORED 4-4R campaigns (analysis only): where the adopted engine's remaining gap to the ungoverned engine sits, and where in the trial sequence the rule 3 and rule 4 picks fall.

Design fixed in docs/decisions.md ("PROPOSAL, NOT APPROVED: the rules 3/4 diagnosis from stored 4-4R data", approved by the project owner with one addition: report where in the trial sequence, early against late, by block,
rule 3 and rule 4 picks concentrate). It reads only runs/devcomparison_r/cache (seeds 11500 to 11539), runs no campaign, touches no engine file or constant, uses no other seed and judges nothing new. It writes
runs/rules34/summary.md (not in git). Run:  .venv\Scripts\python.exe tools\analyse_rules34.py

It is an ACCOUNTING, not a causal estimate: after its first different pick the two engines see different histories, so 'the ungoverned engine's flag at the same trial' is a comparison of outcomes, not of identical choices.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.comparison.dev_comparison import paired_difference  # noqa: E402  (the 4-4 bootstrap: 2,000 resamples, seed 20261014)

CACHE = ROOT / "runs" / "devcomparison_r" / "cache"
SEEDS = tuple(range(11500, 11540))                       # the 4-4R block, already spent; nothing else is read
SCENARIOS = ("period_shift", "new_supplier")
EVENT = {"period_shift": 6, "new_supplier": 8}           # the trial from which the scenario's event applies
BLOCKS = ((1, 5), (6, 12), (13, 18), (19, 24), (25, 30))
RULE3, RULE4 = "exploratory", "bridging"
TRIALS = 30
KNOWN = {"period_shift": {"adopted": 28.4, "ungoverned": 30.0, "difference": -1.6, "lo": -1.9, "hi": -1.3},          # the 4-4R table, as recorded in docs/decisions.md
         "new_supplier": {"adopted": 28.4, "ungoverned": 30.0, "difference": -1.6, "lo": -1.9, "hi": -1.2}}


def load(scenario: str, strategy: str, cache: Path = CACHE, seeds=SEEDS) -> list[dict]:
    """The stored campaigns of one strategy in one scenario, in seed order. A missing file is an error (nothing is run to replace it)."""
    out = []
    for seed in seeds:
        path = cache / scenario / f"{strategy}_{seed}.json"
        if not path.exists():
            raise FileNotFoundError(f"The stored campaign {path} is missing. Nothing is run to replace it: run the 4-4R comparison (run_dev_comparison_r.bat) to store it.")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["seed"] != seed or record["scenario"] != scenario or len(record["good"]) != TRIALS:
            raise ValueError(f"{path.name} is not the campaign it should be.")
        out.append(record)
    return out


def block_of(trial: int) -> int:
    return next(i for i, (lo, hi) in enumerate(BLOCKS) if lo <= trial <= hi)


def campaign_accounts(adopted: dict, ungoverned: dict, event: int) -> dict:
    """One campaign's accounting. For each trial, loss = the ungoverned engine's truly-good flag minus the adopted engine's (1 means the adopted engine lost a truly good recipe the other one had).
    The total gap is split by the adopted engine's own kind of pick at that trial."""
    r, u, kinds = adopted["good"], ungoverned["good"], adopted["kinds"]
    loss = [int(u[t]) - int(r[t]) for t in range(TRIALS)]
    parts = {"rule3": 0, "rule4": 0, "other": 0}
    picks = {"rule3": [0] * len(BLOCKS), "rule4": [0] * len(BLOCKS)}
    bad = {"rule3": [0] * len(BLOCKS), "rule4": [0] * len(BLOCKS), "all": [0] * len(BLOCKS)}
    lost = {"rule3": [0] * len(BLOCKS), "rule4": [0] * len(BLOCKS), "other": [0] * len(BLOCKS)}
    before = {"rule3": 0, "rule4": 0, "rule3_loss": 0, "rule4_loss": 0}
    after = {"rule3": 0, "rule4": 0, "rule3_loss": 0, "rule4_loss": 0}
    for t in range(TRIALS):
        trial = t + 1
        b = block_of(trial)
        which = "rule3" if kinds[t] == RULE3 else "rule4" if kinds[t] == RULE4 else "other"
        parts[which] += loss[t]
        lost[which][b] += loss[t]
        bad["all"][b] += int(not r[t])
        if which != "other":
            picks[which][b] += 1
            bad[which][b] += int(not r[t])
            side = before if trial < event else after
            side[which] += 1
            side[which + "_loss"] += loss[t]
    return {"total": sum(loss), **parts, "picks": picks, "bad": bad, "lost": lost, "before": before, "after": after, "adopted_good": int(sum(r)), "ungoverned_good": int(sum(u))}


def interval(values) -> tuple[float, float, float]:
    """(mean, lower, upper) of a per-campaign quantity: the mean and its 95% interval from resampling the campaigns (the 4-4 bootstrap)."""
    x = np.asarray(values, float)
    d = paired_difference(list(x), [0.0] * len(x))
    return float(x.mean()), d["lo"], d["hi"]


def kind_table(records: list[dict]) -> dict:
    """The adopted engine's picks by kind: per campaign, how many, and how many were truly good."""
    kinds = sorted({k for r in records for k in r["kinds"]})
    table = {}
    for kind in kinds:
        picks = [sum(1 for k in r["kinds"] if k == kind) for r in records]
        good = [sum(1 for k, g in zip(r["kinds"], r["good"]) if k == kind and g) for r in records]
        table[kind] = {"picks": float(np.mean(picks)), "good": float(np.mean(good)), "not_good": float(np.mean(picks)) - float(np.mean(good))}
    return table


def analyse(scenario: str, cache: Path = CACHE, seeds=SEEDS) -> dict:
    adopted, ungoverned = load(scenario, "recalibrated", cache, seeds), load(scenario, "ungoverned", cache, seeds)
    event = EVENT[scenario]
    accounts = [campaign_accounts(a, u, event) for a, u in zip(adopted, ungoverned)]
    n = len(accounts)
    diff = paired_difference([a["adopted_good"] for a in accounts], [a["ungoverned_good"] for a in accounts])
    out = {"scenario": scenario, "event": event, "campaigns": n,
           "known": {"adopted": float(np.mean([a["adopted_good"] for a in accounts])), "ungoverned": float(np.mean([a["ungoverned_good"] for a in accounts])), "difference": diff["mean"], "lo": diff["lo"], "hi": diff["hi"]},
           "kinds": kind_table(adopted),
           "gap": {k: interval([a[k] for a in accounts]) for k in ("total", "rule3", "rule4", "other")}}
    out["blocks"] = []
    for b, (lo, hi) in enumerate(BLOCKS):
        row = {"block": f"{lo} to {hi}", "trials": hi - lo + 1,
               "rule3_picks": sum(a["picks"]["rule3"][b] for a in accounts) / n, "rule4_picks": sum(a["picks"]["rule4"][b] for a in accounts) / n,
               "rule3_not_good": sum(a["bad"]["rule3"][b] for a in accounts) / n, "rule4_not_good": sum(a["bad"]["rule4"][b] for a in accounts) / n, "all_not_good": sum(a["bad"]["all"][b] for a in accounts) / n,
               "loss_rule3": sum(a["lost"]["rule3"][b] for a in accounts) / n, "loss_rule4": sum(a["lost"]["rule4"][b] for a in accounts) / n, "loss_other": sum(a["lost"]["other"][b] for a in accounts) / n}
        out["blocks"].append(row)
    total3, total4 = sum(r["rule3_picks"] for r in out["blocks"]), sum(r["rule4_picks"] for r in out["blocks"])
    for r in out["blocks"]:
        share_trials = r["trials"] / TRIALS
        r["rule3_share"] = r["rule3_picks"] / total3 if total3 else None
        r["rule4_share"] = r["rule4_picks"] / total4 if total4 else None
        r["rule3_concentration"] = r["rule3_share"] / share_trials if r["rule3_share"] is not None else None       # 1.0 = in proportion to the block's share of the trials; above 1 = more picks than its share
        r["rule4_concentration"] = r["rule4_share"] / share_trials if r["rule4_share"] is not None else None
    out["event_split"] = {side: {k: sum(a[side][k] for a in accounts) / n for k in ("rule3", "rule4", "rule3_loss", "rule4_loss")} for side in ("before", "after")}
    return out


def reproduces(result: dict) -> bool:
    """The known answer first: the adopted engine's and the ungoverned engine's truly good recipes per campaign and their paired difference (to one decimal) are the 4-4R table's."""
    k, want = result["known"], KNOWN[result["scenario"]]
    return all(round(k[f], 1) == want[f] for f in ("adopted", "ungoverned", "difference", "lo", "hi"))


def f(x, places=2) -> str:
    return "n/a" if x is None else f"{x:.{places}f}"


def report(results: list[dict]) -> str:
    lines = ["# Rules 3 and 4 diagnosis from the stored 4-4R campaigns [SYNTHETIC DATA]", "",
             "**SYNTHETIC DATA** from the development lab. Analysis only: the stored 4-4R campaigns (seeds 11500 to 11539), no campaign run, no engine file or constant changed. It is an accounting, not a causal estimate "
             "(after its first different pick the two engines see different histories). No pass or fail bar.", ""]
    for r in results:
        k = r["known"]
        lines += [f"## {r['scenario']} (event from trial {r['event']}; {r['campaigns']} paired campaigns)", "",
                  f"**Known answer first:** adopted engine {f(k['adopted'], 1)} truly good per campaign, ungoverned {f(k['ungoverned'], 1)}, difference {f(k['difference'], 1)} ({f(k['lo'], 1)} to {f(k['hi'], 1)}). "
                  + ("This is the 4-4R table: **reproduced**." if reproduces(r) else "**This does NOT match the 4-4R table: stop and report before reading anything below.**"), "",
                  "### 1. The adopted engine's picks by kind (per campaign)", "", "| Kind | Picks | Truly good | Not truly good |", "|---|---|---|---|"]
        for kind, v in r["kinds"].items():
            tag = " (rule 3)" if kind == RULE3 else " (rule 4)" if kind == RULE4 else ""
            lines.append(f"| {kind}{tag} | {f(v['picks'])} | {f(v['good'])} | {f(v['not_good'])} |")
        g = r["gap"]
        lines += ["", "### 2. The accounting: truly good recipes the adopted engine lost, by the kind of its own pick at that trial (per campaign; mean and 95% interval)", "",
                  "| Part of the gap | Mean | 95% interval | Share of the total |", "|---|---|---|---|"]
        for key, label in (("total", "Total gap (ungoverned minus adopted)"), ("rule3", "at rule 3 (exploratory) picks"), ("rule4", "at rule 4 (bridging) picks"), ("other", "at all other picks")):
            m, lo, hi = g[key]
            share = "" if key == "total" else (f"{m / g['total'][0]:.0%}" if g["total"][0] else "n/a")
            lines.append(f"| {label} | {f(m)} | {f(lo)} to {f(hi)} | {share} |")
        s = r["event_split"]
        lines += ["", f"### 3. Before and after the event (trial {r['event']})", "", "| | Rule 3 picks | Loss at rule 3 picks | Rule 4 picks | Loss at rule 4 picks |", "|---|---|---|---|---|",
                  f"| before (trials 1 to {r['event'] - 1}) | {f(s['before']['rule3'])} | {f(s['before']['rule3_loss'])} | {f(s['before']['rule4'])} | {f(s['before']['rule4_loss'])} |",
                  f"| from the event (trials {r['event']} to 30) | {f(s['after']['rule3'])} | {f(s['after']['rule3_loss'])} | {f(s['after']['rule4'])} | {f(s['after']['rule4_loss'])} |", "",
                  "### 4. Where in the trial sequence the picks fall, by block (per campaign)", "",
                  "Concentration = a block's share of all rule 3 (or rule 4) picks divided by its share of the 30 trials: 1.0 is in proportion, above 1 is more picks than its share.", "",
                  "| Trials | Rule 3 picks | Concentration | Rule 4 picks | Concentration | Loss at rule 3 | Loss at rule 4 | Loss at other picks | Adopted not-good, all picks |", "|---|---|---|---|---|---|---|---|---|"]
        for b in r["blocks"]:
            lines.append(f"| {b['block']} | {f(b['rule3_picks'])} | {f(b['rule3_concentration'])} | {f(b['rule4_picks'])} | {f(b['rule4_concentration'])} | {f(b['loss_rule3'])} | {f(b['loss_rule4'])} | {f(b['loss_other'])} | {f(b['all_not_good'])} |")
        lines.append("")
    lines += ["## What this does not show", "", "- Anything about real tablets or a client; every figure is from the synthetic development lab.",
              "- Why a rule 3 or rule 4 pick was or was not truly good: only how often, and when. The two engines' histories differ after their first different pick, so the loss at a trial is not the effect of that one pick.",
              "- Whether any constant should change: that is a decision for the project owner, and none is proposed here."]
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        results = [analyse(s) for s in SCENARIOS]
    except (FileNotFoundError, ValueError) as error:
        print(error)
        return 1
    out = ROOT / "runs" / "rules34"
    out.mkdir(parents=True, exist_ok=True)
    text = report(results)
    (out / "summary.md").write_bytes(text.encode("utf-8"))
    print(text)
    print("Written to runs\\rules34\\summary.md" + ("" if all(reproduces(r) for r in results) else "  (WARNING: the known answer was not reproduced)"))
    return 0 if all(reproduces(r) for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
