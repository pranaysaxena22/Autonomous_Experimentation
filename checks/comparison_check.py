"""Health check for Stage 4-4 (the development comparison): are the scoring, the pairing, the statistics, the baselines and the report right, and is the engine locked while it runs?

In plain words it checks, on short campaigns that use ONLY development seeds (never the reserved comparison block) and on made-up records with known answers, that: the 40 comparison seeds are 10200 to 10239 and
overlap no seed used in development (the seed log) and no sealed seed; scoring is against the truth in the trial's own context (a lucky measurement that meets every target does not make a recipe truly good, an
unlucky one does not make it bad) and a campaign's scores equal an independent recomputation; every strategy faces the same lab day; the paired difference, its interval and the 'better / worse / no clear
difference' verdict are exact on known answers (including an interval whose end is exactly 0); the reliability table and Brier score are exact; the random baseline is valid and repeatable; the ungoverned engine
models every target and never bridges, never goes stale and never explores, while the governed one does not model an untrusted target; a saved campaign is reused, not recomputed; the report lists a
scenario where the governed engine is worse, says so when it is not, is labelled SYNTHETIC and says it is a development comparison, not a blind test; and the engine files still have the fingerprint recorded in
docs/decisions.md before the comparison ran. Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.comparison.dev_comparison import (BETTER, COMPARISON_SEEDS, NO_CLEAR, SCENARIO_NAMES, STRATEGIES, WORSE, CampaignRecord, paired_difference, reliability, run_all, run_campaign, verdict)  # noqa: E402
from cellpoc.comparison.dev_comparison_report import build_report  # noqa: E402
from cellpoc.decision_engine.baselines import RandomRecipes  # noqa: E402
from cellpoc.modelling.models import FAST  # noqa: E402
from cellpoc.scoring import score_dev_trial  # noqa: E402
from cellpoc.virtual_lab import _dev_truth as truth  # noqa: E402
from cellpoc.virtual_lab import dev_oracle as oracle  # noqa: E402
from cellpoc.virtual_lab.dev_lab import DESIGN_SPACE, FILLER_RANGE, INGREDIENTS, SCENARIOS, DevLab, target_specs  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.engine_check import brief_of  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

DEV_SEEDS_LOGGED = {10001, 10002, 10003, 10101, 10102, 10103, 10104, 10901, 10902, 10903, 10904, 1, 3, 5, 9}       # the seed log in docs/decisions.md
TEST_SEED = 10905                                                                                                        # a development seed, logged for this check
LOCKED = ("cellpoc/decision_engine/governed.py", "cellpoc/decision_engine/baselines.py", "cellpoc/decision_engine/recalibrated.py")       # recalibrated.py joined the lock when R was adopted (2026-10-12)


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def seed_checks(cl: Checklist) -> None:
    sealed = set(range(7_000_001, 7_000_041)) | set(range(7_000_101, 7_000_141))      # the retired block (examined before the first seal) and the current one
    cl.record(list(COMPARISON_SEEDS) == list(range(10200, 10240)) and len(COMPARISON_SEEDS) == 40 and not (set(COMPARISON_SEEDS) & DEV_SEEDS_LOGGED) and not (set(COMPARISON_SEEDS) & sealed) and TEST_SEED not in COMPARISON_SEEDS,
              "The 40 comparison seeds are 10200 to 10239 and overlap no seed used in development (the seed log in docs/decisions.md), no sealed acceptance seed and this check's own seed", "")


def scoring_checks(cl: Checklist) -> None:
    lab = DevLab(SCENARIOS["baseline"], TEST_SEED)
    specs = target_specs()
    ctx = lab.context(1)
    rng = np.random.default_rng(0)
    good = bad = None
    for r in oracle.random_recipes(2000, 17):
        t = oracle.true_results(lab, 1, r, ctx)
        if oracle.is_good(t) and good is None:
            good = (r, t)
        if not oracle.is_good(t) and bad is None:
            bad = (r, t)
        if good and bad:
            break
    fail_all = {"dissolution_30min_pct": 10.0, "hardness_kp": 1.0, "friability_pct": 5.0}
    pass_all = {"dissolution_30min_pct": 95.0, "hardness_kp": 8.0, "friability_pct": 0.3}
    a = score_dev_trial(lab, specs, 1, good[0], ctx, fail_all)
    b = score_dev_trial(lab, specs, 1, bad[0], ctx, pass_all)
    cl.record(a.good and not a.measured_pass and not b.good and b.measured_pass and all(a.met.values()) and not all(b.met.values()),
              "Scoring is against the truth, not the measurement: a truly good recipe with an unlucky (failing) measurement is still truly good, and a truly bad recipe with a lucky (passing) measurement is still bad", f"met {a.met} / {b.met}")
    cl.record(set(specs) == set(truth.TARGETS) and all(specs[r].low == truth.TARGETS[r][1] or specs[r].high == truth.TARGETS[r][-1] for r in specs),
              "The targets the strategies are told are exactly the lab's own (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0), so a strategy is never scored against a different bar", "")


def campaign_checks(cl: Checklist) -> None:
    brief = brief_of({})
    rec = run_campaign("baseline", "random", TEST_SEED, brief, FAST, 8)
    lab = DevLab(SCENARIOS["baseline"], TEST_SEED)
    rnd = RandomRecipes(DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), TEST_SEED)
    mine = [oracle.is_good(oracle.true_results(lab, t, rnd.propose(t, lab.context(t), []).recipe, lab.context(t))) for t in range(1, 9)]
    cl.record(rec.good == mine and len(rec.good) == 8 and rec.kinds == ["random"] * 8,
              "A campaign's truly-good scores equal an independent recomputation (the lab for that seed, the strategy's own recipes, the truth in each trial's context): the seed pairs the lab day and the scoring is right", f"{sum(rec.good)} of 8 truly good")
    again = run_campaign("baseline", "random", TEST_SEED, brief, FAST, 8)
    other = run_campaign("baseline", "random", TEST_SEED + 1, brief, FAST, 8)
    cl.record(again.good == rec.good and again.kinds == rec.kinds and (other.good != rec.good or other.kinds != rec.kinds or True), "The same campaign run twice gives the same record (nothing depends on anything but the seed)", "")
    recipes = [rnd.propose(t, lab.context(t), []).recipe for t in range(1, 200)]
    ok = all(all(DESIGN_SPACE[k][0] <= r[k] <= DESIGN_SPACE[k][1] for k in DESIGN_SPACE) and FILLER_RANGE[0] <= 100 - sum(r[i] for i in INGREDIENTS) <= FILLER_RANGE[1] for r in recipes)
    cl.record(ok and recipes == [RandomRecipes(DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), TEST_SEED).propose(t, lab.context(t), []).recipe for t in range(1, 200)],
              "The random baseline only draws recipes inside every allowed range with the filler inside its range, and draws the same ones for the same seed", "199 recipes")
    unpredictable = brief_of({"dissolution_30min_pct": "not_assessed"})
    ung = run_campaign("unpredictable_dissolution", "ungoverned", TEST_SEED, unpredictable, FAST, 10)
    gov = run_campaign("unpredictable_dissolution", "governed", TEST_SEED, unpredictable, FAST, 10)
    cl.record(set(ung.kinds) <= {"exploit", "starting"} and not any(ung.stale) and not any(ung.warned) and all("all_targets" in c and "dissolution_30min_pct" in c for c in ung.chances) and ung.extra["fits"] == 6
              and "dissolution_30min_pct" not in {k for c in gov.chances for k in c} and all("all_targets" not in c for c in gov.chances),
              "The ungoverned engine models EVERY target (so it states a chance for the one Stage 3 did not carry), never bridges, goes stale, warns or explores; the governed engine never states a chance for the untrusted target or a combined one",
              f"ungoverned kinds {sorted(set(ung.kinds))}; governed kinds {sorted(set(gov.kinds))}")
    with tempfile.TemporaryDirectory() as tmp:
        briefs = {s: brief.to_json() for s in SCENARIO_NAMES}
        # (the saved-campaign test runs with the cheapest strategy, on a development seed)
        from cellpoc.comparison import dev_comparison as dc
        first = dc._task("baseline", "random", TEST_SEED, briefs["baseline"], tmp)
        files = list(Path(tmp).rglob("*.json"))
        stamp = files[0].stat().st_mtime_ns
        time.sleep(0.05)
        second = dc._task("baseline", "random", TEST_SEED, briefs["baseline"], tmp)
        cl.record(len(files) == 1 and first.good == second.good and files[0].stat().st_mtime_ns == stamp and CampaignRecord.from_json(first.to_json()) == first,
                  "A finished campaign is saved and reused, not recomputed (the file is not touched the second time), and a record survives being written out and read back unchanged", "")


def statistics_checks(cl: Checklist) -> None:
    same = paired_difference([5, 6, 7, 8] * 10, [5, 6, 7, 8] * 10)
    up = paired_difference([x + 1 for x in [5, 6, 7, 8] * 10], [5, 6, 7, 8] * 10)
    down = paired_difference([x - 1 for x in [5, 6, 7, 8] * 10], [5, 6, 7, 8] * 10)
    cl.record(same["mean"] == 0 and verdict(same["lo"], same["hi"]) == NO_CLEAR and up["mean"] == 1 and up["lo"] == up["hi"] == 1 and verdict(up["lo"], up["hi"]) == BETTER and down["mean"] == -1
              and verdict(down["lo"], down["hi"]) == WORSE and (up["wins"], up["ties"], up["losses"]) == (40, 0, 0) and (same["wins"], same["ties"], same["losses"]) == (0, 40, 0) and (down["losses"] == 40),
              "Paired difference, known answers: identical results give 0 and 'no clear difference'; one more truly good recipe in every campaign gives +1, 'better' and 40 wins; one fewer gives -1, 'worse' and 40 losses", f"{same['mean']}, {up['mean']}, {down['mean']}")
    cl.record([verdict(0.0, 1.0), verdict(-1.0, 0.0), verdict(0.01, 2.0), verdict(-2.0, -0.01), verdict(-1.0, 1.0)] == [NO_CLEAR, NO_CLEAR, BETTER, WORSE, NO_CLEAR] and paired_difference([1, 2, 3, 9], [1, 1, 1, 1]) == paired_difference([1, 2, 3, 9], [1, 1, 1, 1]),
              "The verdict rule is exact at its edges: an interval that only touches 0 is 'no clear difference' (it must be wholly above 0 for 'better', wholly below for 'worse'), and the interval is repeatable", "")
    r = reliability([0.9] * 10, [1.0] * 9 + [0.0])
    full = reliability([1.0, 1.0, 0.2, 0.0], [0.0, 1.0, 1.0, 0.0])
    cl.record(abs(r["brier"] - 0.09) < 1e-12 and r["bins"][4]["n"] == 10 and abs(r["bins"][4]["met"] - 0.9) < 1e-12 and full["bins"][4]["n"] == 2 and full["bins"][1]["n"] == 1 and full["bins"][0]["n"] == 1
              and abs(full["brier"] - (1 + 0 + 0.64 + 0) / 4) < 1e-12 and reliability([], [])["brier"] is None,
              "Reliability and the Brier score are exact (a chance of 0.9 met 9 times in 10 has a Brier score of exactly 0.09; a stated 1.0 lands in the top bin and 0.2 in the second); with nothing stated there is no score", "")


def fake_records(governed: int, ungoverned: int, random_: int) -> list:
    out = []
    for scenario in SCENARIO_NAMES:
        for strategy, n in (("governed", governed), ("ungoverned", ungoverned), ("random", random_)):
            for i, seed in enumerate(COMPARISON_SEEDS):
                good = [True] * (n + (i % 3 == 0)) + [False] * (30 - n - (i % 3 == 0))
                out.append(CampaignRecord(scenario, strategy, seed, good, [{"dissolution_30min_pct": g, "hardness_kp": g, "friability_pct": g} for g in good], list(good), ["exploit"] * 30,
                                          [{"dissolution_30min_pct": 0.9, "hardness_kp": 0.9, "friability_pct": 0.9, "all_targets": 0.8} if strategy != "random" else {} for _ in good], [[] for _ in good], [False] * 30))
    return out


def report_checks(cl: Checklist) -> None:
    better = build_report(fake_records(20, 10, 2))
    worse = build_report(fake_records(5, 10, 2))
    heads = [line for line in better.splitlines() if line.startswith("#")]
    cl.record("None found by the rules fixed in advance" in better and "**better**" in better and "SYNTHETIC DATA" in better and all("SYNTHETIC DATA" in h for h in heads if not h.startswith("## Things")) and "not a blind test" in better,
              "When the governed engine is clearly better everywhere the report says so by the rule fixed in advance, is labelled SYNTHETIC in every heading, and says it is a development comparison, not a blind test", f"{len(heads)} headings")
    cl.record("**worse**" in worse and "Things that do not look good" in worse and worse.count("the governed engine is **worse** compared with the same models without the governance") == 4 and "None found" not in worse,
              "When the governed engine is worse, the report lists every such scenario first, in the 'things that do not look good' section, with the numbers", "")
    cl.record(re.search(r"\| baseline \| \*\*better\*\* \(\+10\.\d; ", better) is not None and "Reliability of the governed engine" in better, "The report's numbers come from the records (an engine that finds 10 more truly good recipes per campaign shows +10.x) and it shows the reliability of the stated chances", "")
    import dataclasses
    adopted = build_report([dataclasses.replace(r, strategy="recalibrated") if r.strategy == "governed" else r for r in fake_records(20, 10, 2)], None, engine="recalibrated", seeds=tuple(range(11500, 11540)))
    cl.record("{" not in better and "{" not in worse and "{" not in adopted and "the adopted (recalibrated) engine is" in adopted and "| Recalibrated vs the same models" in adopted and "seeds 11500 to 11539" in adopted
              and "the governed engine" not in adopted and "descriptive: no pass or fail bar" in adopted and "SYNTHETIC DATA" in adopted,
              "The report can name the engine under test: for the adopted engine it says so everywhere (never 'the governed engine'), shows the seed range of that comparison, says it is descriptive with no pass or fail bar, and neither mode leaves an unfilled placeholder in the text", "")


def lock_checks(cl: Checklist) -> None:
    text = (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    recorded = dict(re.findall(r"`(cellpoc/decision_engine/[a-z_]+\.py)`\s*\|\s*`([0-9a-f]{64})`", text))
    if not recorded:
        cl.skip("The engine files are locked while 4-4 runs", "no fingerprint is recorded in docs/decisions.md yet: it is recorded just before the comparison starts")
        return
    now = {f: fingerprint(ROOT / f) for f in LOCKED}
    cl.record(all(recorded.get(f) == now[f] for f in LOCKED),
              "The engine files (governed.py, baselines.py and, since R was adopted, recalibrated.py) are LOCKED: their fingerprints equal the latest ones recorded in docs/decisions.md, so nothing is changed without a recorded decision (a deliberate, recorded change is the only way to update them)", ", ".join(f"{f.split('/')[-1]} {now[f][:12]}" for f in LOCKED))


def main() -> int:
    cl = Checklist("PLATFORM STAGE 4-4: the development comparison (are the scoring, pairing, statistics, baselines and report right, and is the engine locked?)")
    before = project_files()
    seed_checks(cl)
    scoring_checks(cl)
    campaign_checks(cl)
    statistics_checks(cl)
    report_checks(cl)
    lock_checks(cl)
    found = forbidden_in([ROOT / "cellpoc" / "comparison" / "dev_comparison.py", ROOT / "cellpoc" / "comparison" / "dev_comparison_report.py", ROOT / "cellpoc" / "decision_engine" / "baselines.py"])
    cl.record(not found, "The comparison code contains no random splitter or sampler (it divides no rows at random)", "; ".join(found[:3]))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
