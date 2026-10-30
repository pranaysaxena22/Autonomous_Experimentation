"""Health check for the rules 3/4 diagnosis tool (tools/analyse_rules34.py): does it count what it says, from the stored campaigns only, and does it reproduce the 4-4R table before saying anything else?

In plain words it checks that: on two small made-up campaigns whose every trial was worked out by hand, the tool's accounting gives exactly the hand-worked numbers (the total gap, the part at rule 3 picks, the part at rule 4 picks and the part
at all other picks, the picks and the losses in each block of trials, and the concentration of each kind of pick); a trial where the ungoverned engine did WORSE than the adopted one counts as a gain, not as zero; the parts always add up to
the total; the picks of each kind sit in the block where the trial number puts them (trial 5 in the first block, trial 25 in the last); a missing stored campaign is an error that says nothing is run to replace it, not a silent skip; the tool's
source never runs a campaign, never builds a lab or an engine, and never names a seed outside 11500 to 11539; and, when the stored 4-4R campaigns are on this computer, the tool reproduces the 4-4R table for both scenarios (28.4 and 30.0
truly good recipes per campaign, the paired difference of -1.6 and its interval) and its parts add up to the table's gap. Nothing is written into the project.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import analyse_rules34 as T  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402


def campaign(strategy: str, seed: int, kinds: list[str], zeros: list[int], scenario: str = "period_shift") -> dict:
    """A made-up stored campaign: every trial is truly good except the trials listed in `zeros`."""
    return {"scenario": scenario, "strategy": strategy, "seed": seed, "good": [t not in zeros for t in range(1, 31)], "kinds": kinds, "met": [], "measured_pass": [], "chances": [], "stale": [], "warned": []}


def kinds_of(special: dict[int, str]) -> list[str]:
    return [special.get(t, "exploit") for t in range(1, 31)]


def main() -> int:
    cl = Checklist("RULES 3/4 DIAGNOSIS TOOL: it counts what it says, from the stored campaigns only, and reproduces the 4-4R table first")
    before = project_files()
    # Campaign A: the adopted engine is not good at trials 5 and 25 (rule 3 picks); at trial 10 (a rule 3 pick) it is good where the ungoverned engine is not.
    a_r = campaign("recalibrated", 11500, kinds_of({5: "exploratory", 10: "exploratory", 25: "exploratory"}), zeros=[5, 25])
    a_u = campaign("ungoverned", 11500, kinds_of({}), zeros=[10])
    # Campaign B: bridging picks at 8, 9, 10 (good, not good, not good); the ungoverned engine is good at all of them; and an ordinary pick at 15 is not good where the ungoverned engine's is.
    b_r = campaign("recalibrated", 11501, kinds_of({8: "bridging", 9: "bridging", 10: "bridging"}), zeros=[9, 10, 15])
    b_u = campaign("ungoverned", 11501, kinds_of({}), zeros=[])
    a, b = T.campaign_accounts(a_r, a_u, 6), T.campaign_accounts(b_r, b_u, 8)
    # worked out by hand: A total 1 - 1 + 1 = ... trial 5: 1-0 = 1, trial 25: 1-0 = 1, trial 10: 0-1 = -1  -> total 1, all at rule 3.  B: trial 9: 1, trial 10: 1 (rule 4), trial 15: 1 (other)  -> total 3: rule 4 gets 2, other 1.
    cl.record((a["total"], a["rule3"], a["rule4"], a["other"]) == (1, 1, 0, 0) and (b["total"], b["rule3"], b["rule4"], b["other"]) == (3, 0, 2, 1),
              "On two made-up campaigns worked out by hand, the accounting is exactly right: A loses 1 in all (all at rule 3: two lost at trials 5 and 25, one gained at trial 10), B loses 3 (2 at rule 4, 1 at an ordinary pick)",
              f"A {a['total']}/{a['rule3']}/{a['rule4']}/{a['other']}; B {b['total']}/{b['rule3']}/{b['rule4']}/{b['other']}")
    cl.record(all(c["total"] == c["rule3"] + c["rule4"] + c["other"] for c in (a, b)) and a["total"] == a["ungoverned_good"] - a["adopted_good"] and b["total"] == b["ungoverned_good"] - b["adopted_good"],
              "The three parts always add up to the total, and the total equals the ungoverned engine's truly good recipes minus the adopted engine's")
    cl.record(a["picks"]["rule3"] == [1, 1, 0, 0, 1] and b["picks"]["rule4"] == [0, 3, 0, 0, 0] and a["lost"]["rule3"] == [1, -1, 0, 0, 1] and b["lost"]["rule4"] == [0, 2, 0, 0, 0] and b["lost"]["other"] == [0, 0, 1, 0, 0],
              "Each kind of pick and each loss is counted in the block where its trial number puts it (trial 5 in the first block, 10 in the second, 15 in the third, 25 in the last), and a trial where the adopted engine did better counts as a gain of 1 (-1), not as zero",
              f"A rule 3 picks by block {a['picks']['rule3']}; B rule 4 picks by block {b['picks']['rule4']}")
    cl.record(a["before"] == {"rule3": 1, "rule4": 0, "rule3_loss": 1, "rule4_loss": 0} and a["after"] == {"rule3": 2, "rule4": 0, "rule3_loss": 0, "rule4_loss": 0}
              and b["before"] == {"rule3": 0, "rule4": 0, "rule3_loss": 0, "rule4_loss": 0} and b["after"] == {"rule3": 0, "rule4": 3, "rule3_loss": 0, "rule4_loss": 2},
              "Before and after the event are split at the right trial (A's event is trial 6: the pick at trial 5 is before it; B's is trial 8: the bridging picks at 8, 9 and 10 are from it)")
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        (cache / "period_shift").mkdir()
        import json
        for rec in (a_r, a_u, b_r, b_u):
            seed = 11500 if rec["seed"] == 11500 else 11501
            (cache / "period_shift" / f"{rec['strategy']}_{seed}.json").write_text(json.dumps(rec), encoding="utf-8")
        result = T.analyse("period_shift", cache, seeds=(11500, 11501))
        blocks = result["blocks"]
        cl.record(abs(result["gap"]["total"][0] - 2.0) < 1e-9 and abs(result["gap"]["rule3"][0] - 0.5) < 1e-9 and abs(result["gap"]["rule4"][0] - 1.0) < 1e-9 and abs(result["gap"]["other"][0] - 0.5) < 1e-9
                  and [round(x["rule3_picks"], 6) for x in blocks] == [0.5, 0.5, 0.0, 0.0, 0.5] and [round(x["rule4_picks"], 6) for x in blocks] == [0.0, 1.5, 0.0, 0.0, 0.0]
                  and abs(blocks[1]["rule4_concentration"] - 1.0 / (7 / 30)) < 1e-9 and blocks[0]["rule3_concentration"] == (0.5 / 1.5) / (5 / 30),
                  "Read back from stored files, the per-campaign means are the hand-worked ones (total 2.0, rule 3 0.5, rule 4 1.0, other 0.5; rule 3 picks per block 0.5, 0.5, 0, 0, 0.5; rule 4 picks 1.5 in the second block), and the concentration is a block's share of the picks over its share of the trials",
                  f"means {[round(result['gap'][k][0], 3) for k in ('total', 'rule3', 'rule4', 'other')]}")
        try:
            T.load("period_shift", "recalibrated", cache, seeds=(11500, 11501, 11502))
            message = None
        except FileNotFoundError as error:
            message = str(error)
        cl.record(bool(message) and "Nothing is run to replace it" in message and not re.search(r"Traceback|KeyError|\{", message), "A stored campaign that is missing is an error in plain words ('nothing is run to replace it'), not a silent skip", (message or "NOT REFUSED")[:100])
    source = (ROOT / "tools" / "analyse_rules34.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    body = re.sub(r'""".*?"""', "", code, flags=re.S)
    seeds = {int(s) for s in re.findall(r"\b(1[0-9]{4}|[0-9]{7})\b", body)}
    cl.record(not re.search(r"run_campaign|run_all|DevLab|\.measure\(|build_strategy|RecalibratedStrategy|GovernedStrategy|UngovernedStrategy", body) and all(11500 <= s <= 11540 for s in seeds),
              "The tool never runs a campaign, never builds a lab or an engine, and names no seed outside the 4-4R block 11500 to 11539 (11540 is only the end of its range)", f"numbers that look like seeds: {sorted(seeds)}")
    cache = T.CACHE
    if all((cache / s).exists() for s in T.SCENARIOS):
        results = [T.analyse(s) for s in T.SCENARIOS]
        cl.record(all(T.reproduces(r) for r in results), "Run on the stored 4-4R campaigns, the tool reproduces the 4-4R table for both scenarios: 28.4 and 30.0 truly good recipes per campaign and the paired difference with its interval", "; ".join(f"{r['scenario']}: {r['known']['adopted']:.1f} vs {r['known']['ungoverned']:.1f}, {r['known']['difference']:.1f} ({r['known']['lo']:.1f} to {r['known']['hi']:.1f})" for r in results))
        cl.record(all(abs(r["gap"]["total"][0] - (r["gap"]["rule3"][0] + r["gap"]["rule4"][0] + r["gap"]["other"][0])) < 1e-9 and abs(r["gap"]["total"][0] + r["known"]["difference"]) < 1e-9 for r in results),
                  "...and on that real data the parts add up to the total, and the total equals the table's gap exactly (the same campaigns, counted a second way)", "; ".join(f"{r['scenario']}: total {r['gap']['total'][0]:.3f}" for r in results))
    else:
        cl.skip("The tool reproduces the 4-4R table on the stored campaigns", "the stored 4-4R campaigns are not on this computer (run_dev_comparison_r.bat makes them)")
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
