"""Health check for Stage 3b-3 (the decision-usefulness replay): would ranking recipes by a model have chosen better than chance, using only data before each decision?

In plain words it checks, on made-up windows where the answer is known, that: a predictor that knows the truth gets the perfect pass rate, one that says the same for every recipe gets the random
rate (and no 'beat random' verdict), and one that is exactly backwards does worse than random; the verdict, 'no room to improve' and 'cannot be judged' lines sit exactly where they were fixed; a window that
could see the future is refused (a planted leak: a training row from inside the window, a training row dated later than the window's start, a row in both); changing what was MEASURED in a window changes
the pass rates but never which recipes are picked; and the replay refuses any table that is not labelled synthetic. On the saved Stage 3a answers for the two synthetic mocks it checks every
window, that exploratory results carry their label, and that the reports keep their labels, carry the unifying statement and the 'what the mocks cannot show' paragraph, say the fixed sentence for real
batch hardness and tensile strength (with no window of any kind), and never combine the three warning statuses. Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import PROXY_PHRASE, Fold, build_table_for_setup, plan_problems  # noqa: E402
from cellpoc.modelling.carry import BORDERLINE, CARRIED, decide_all  # noqa: E402
from cellpoc.modelling.findings import NO_REPLAY_SENTENCE, UNIFYING_STATEMENT  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.replay import (BEAT, MIN_WARNED, NO_ROOM, NOT_BEAT, STATUSES, Target, Window, ReplayLeak, ReplayRefused, build_windows, leak_problems, n_picks,  # noqa: E402
                                      pick, probability_met, reliability_word, replay_table, summarise, targets_from_setup, verdict_of, warned_picks, Z90)
from cellpoc.modelling.replay_report import build_report, build_summary  # noqa: E402
from cellpoc.modelling.validate import PlanRun, Validation, run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

CACHE = ROOT / "runs" / "modelling" / "cache_full"
MOCKS = ("mock_easy", "mock_hard")


def made_up(rng, windows: int = 4, per: int = 2000, base: float = 0.3) -> list[Window]:
    out = []
    for i in range(windows):
        passed = rng.random(per) < base
        batch = np.array([f"B{j // 50}" for j in range(per)])
        out.append(Window(i + 1, "d1", "d2", np.zeros(per), passed, batch, {s: np.zeros(per, bool) for s in STATUSES}))
    return out


def with_p(windows: list[Window], make) -> list[Window]:
    return [dataclasses.replace(w, p=make(w)) for w in windows]


def known_answer_checks(cl: Checklist) -> None:
    # the probability, against an exact property of a bell curve: the lower end of a stated 90% range has 95% of the probability above it
    got = probability_met(Target("y", "at_least", 10.0 - 3.0 * Z90, None, "y", ""), np.array([10.0]), np.array([10.0 - 3.0 * Z90]), np.array([10.0 + 3.0 * Z90]))[0]
    centre = probability_met(Target("y", "at_least", 5.0, None, "y", ""), np.array([5.0]), np.array([4.0]), np.array([6.0]))[0]
    inside = probability_met(Target("y", "between", 6.0, 10.0, "y", ""), np.array([8.0, 8.0]), np.array([7.9, 4.0]), np.array([8.1, 12.0]))
    cl.record(abs(got - 0.95) < 1e-6 and abs(centre - 0.5) < 1e-9 and inside[0] > 0.999 and inside[1] < 0.8,
              "Probability: a target at the lower end of the model's stated 90% range is met with probability 0.95 (exact); a target at the predicted value is met half the time; a tight range inside a window is almost certain and a wide one is not",
              f"{got:.6f}, {centre:.3f}, {inside.round(3).tolist()}")
    t = {r: Target(r, g, lo, hi, r, "") for r, g, lo, hi in (("a", "at_least", 85.0, None), ("b", "between", 6.0, 10.0), ("c", "at_most", None, 1.0))}
    edges = [t["a"].met(np.array([84.99, 85.0, 85.01])).tolist(), t["b"].met(np.array([5.99, 6.0, 10.0, 10.01])).tolist(), t["c"].met(np.array([0.99, 1.0, 1.01])).tolist()]
    cl.record(edges == [[False, True, True], [False, True, True, False], [True, True, False]], "Targets: 'at least', 'between' and 'at most' include their limits exactly and exclude anything past them", str(edges))
    setup = fixture_setup("mock_easy")
    read = targets_from_setup(setup)
    cl.record({k: (v.low, v.high) for k, v in read.items()} == {"dissolution_30min_pct": (85, None), "hardness_kp": (6, 10), "friability_pct": (None, 1.0)},
              "The targets are read from the mock's setup exactly as stated (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0): nothing is typed into the replay", str({k: (v.low, v.high) for k, v in read.items()}))
    cl.record(targets_from_setup({"targets": {"constraints": []}}) == {} and targets_from_setup({}) == {}, "A setup with no targets gives no targets: no window is ever invented", "")
    cl.record([n_picks(100), n_picks(4), n_picks(1434), n_picks(1)] == [10, 1, 143, 1] and pick(np.array([0.5, 0.9, 0.9, 0.1, 0.9] + [0.0] * 5), 0.3).tolist() == [False, True, True, False, True] + [False] * 5,
              "Picking: the top 10% (at least one) by probability, ties going to the earlier row, nothing random", "")
    rng = np.random.default_rng(1)
    windows = made_up(rng)
    oracle = summarise(with_p(windows, lambda w: w.passed.astype(float)))[0]
    cl.record(abs(oracle.picked_rate - oracle.perfect_rate) < 1e-12 and oracle.captured == 1.0 and oracle.verdict == BEAT and oracle.perfect_rate == 1.0 and abs(oracle.random_rate - 0.3) < 0.04,
              "Known answer: a predictor that knows the truth picks only passers (the perfect pass rate, captured share 1.0) and beats random, while random picking passes about the base rate",
              f"picked {oracle.picked_rate:.3f}, perfect {oracle.perfect_rate:.3f}, random {oracle.random_rate:.3f}")
    flat = summarise(with_p(windows, lambda w: np.full(len(w.p), 0.5)))[0]
    cl.record(abs(flat.gap) < 0.05 and flat.verdict != BEAT, "Known answer: a predictor that says the same for every recipe does about as well as random picking and never gets a 'beat random' verdict", f"gap {flat.gap:+.3f}, verdict '{flat.verdict}'")
    back = summarise(with_p(windows, lambda w: 1.0 - w.passed.astype(float)))[0]
    cl.record(back.picked_rate == 0.0 and back.gap < -0.2 and back.verdict == NOT_BEAT, "Known answer: a predictor that is exactly backwards passes less often than random picking and is called 'did not beat random'", f"picked {back.picked_rate:.3f} against random {back.random_rate:.3f}")
    few = [Window(1, "d1", "d2", np.r_[np.ones(3), np.zeros(37)], np.r_[np.ones(3, bool), np.zeros(37, bool)], np.array(["B"] * 40), {s: np.zeros(40, bool) for s in STATUSES})]
    cl.record(summarise(few, 0.5)[0].windows[0].perfect == 3 and abs(summarise(few, 0.5)[0].perfect_rate - 3 / 20) < 1e-12, "Perfect picking cannot pass more than there are passers: 3 passers among 20 picks is 3/20, not 20/20", "")
    # the lines fixed in advance
    verdicts = [verdict_of(0.98, 1.0, 0.01, 0.0), verdict_of(0.5, 0.51, 0.005, 0.001), verdict_of(0.5, 0.9, 0.1, 0.01), verdict_of(0.5, 0.9, 0.1, 0.0), verdict_of(0.5, 0.9, 0.1, -0.02), verdict_of(0.5, 0.9, -0.1, -0.2), verdict_of(0.5, 0.9, 0.1, None)]
    cl.record(verdicts == [NO_ROOM, NO_ROOM, BEAT, NOT_BEAT, NOT_BEAT, NOT_BEAT, NOT_BEAT],
              "Verdict lines: random at 98% or a gap under 2 points is 'no room to improve'; 'beat random' needs a gain above 0 AND the error bar's lower end above 0 (exactly 0 is not enough)", str(verdicts))
    words = [reliability_word([100, 100, 100], [1.2, 1.5, 2.0]), reliability_word([100, 100, 100], [1.2, 0.9, 2.0]), reliability_word([100, 100, 100], [0.9, 0.8, 0.5]), reliability_word([100, 29, 100], [1.5, 1.5, 1.5]),
             reliability_word([30, 30], [1.1, 1.1]), reliability_word([100, 100], [1.5, None]), reliability_word([100, 100], [1.0, 1.0]), reliability_word([], [])]
    cl.record(words == ["picks out the large errors", "mixed", "does not", "cannot be judged", "picks out the large errors", "cannot be judged", "does not", "cannot be judged"],
              f"Reliability words: a kind of shift is judged only with at least {MIN_WARNED} warned rows in every result (29 is not enough, 30 is); 'picks out the large errors' needs a lift above 1 in every result, 'mixed' in some, exactly 1 is chance", str(words))
    # the same inputs give the same interval every time, and a perfect predictor's interval sits above zero
    a, b = summarise(with_p(windows, lambda w: w.passed.astype(float)))[0], summarise(with_p(windows, lambda w: w.passed.astype(float)))[0]
    cl.record(a.interval == b.interval and a.interval[0] > 0.3, "The error bar is repeatable (same data, same interval) and for the perfect predictor it lies well above zero", f"{a.interval}")
    # did warned picks do worse? built so that the first 100 recipes are the picks and the first 40 of them are warned and all failed
    base = Window(1, "d1", "d2", np.r_[np.ones(100), np.zeros(900)], np.r_[np.zeros(40, bool), np.ones(60, bool), np.zeros(900, bool)], np.array(["B"] * 1000),
                  {"distance": np.r_[np.ones(40, bool), np.zeros(960, bool)], "range": np.zeros(1000, bool), "category": np.zeros(1000, bool)})
    masks = [pick(base.p)]
    d, r = warned_picks([base], masks, "distance"), warned_picks([base], masks, "range")
    few_warned = dataclasses.replace(base, flags={**base.flags, "distance": np.r_[np.ones(29, bool), np.zeros(971, bool)]})
    cl.record(d.warned == 40 and d.warned_rate == 0.0 and d.unwarned_rate == 1.0 and d.said and not r.said and not warned_picks([few_warned], masks, "distance").said,
              f"Warned picks: with 40 warned picks that all failed and 60 unwarned that all passed the comparison is made and shows it; a status that warned none, or only 29, is 'too few to say' (the line is {MIN_WARNED})",
              f"{d.warned_rate}, {d.unwarned_rate}")


def guard_checks(cl: Checklist) -> None:
    dates = pd.Series(pd.date_range("2025-01-01", periods=100, freq="D"))
    ok = Fold(1, np.arange(0, 60), np.arange(60, 80), ("2025-03-02", "2025-03-21"))
    planted = [Fold(1, np.append(np.arange(0, 60), 65), np.arange(60, 80), ("a", "b")), Fold(1, np.append(np.arange(0, 60), 70), np.arange(60, 80), ("a", "b")),
               Fold(1, np.arange(10, 90), np.arange(60, 80), ("a", "b"))]
    problems = [leak_problems(dates, f) for f in planted]
    cl.record(not leak_problems(dates, ok) and all(problems), "Guard: a window whose training rows all come before it is accepted; a planted leak is found every time (a training row from inside the window, a training row dated after the window starts, rows in both)",
              str([len(p) for p in problems]))


def saved_checks(cl: Checklist) -> tuple[dict, dict, list]:
    files = len(list(CACHE.glob("*.pkl"))) if CACHE.exists() else 0
    if files < 280:
        cl.skip("The replay on the saved Stage 3a answers of the synthetic mocks", "they are not on this computer: double-click run_full_validation.bat first")
        return {}, {}, []
    validations = {n: run_validation(build_table_for_setup(fixture_setup(n), None, PROJECT_ROOT, n), FULL, n_jobs=1, cache=CACHE, save=False) for n in MOCKS}
    decisions = decide_all(list(validations.values()))
    replays, cache = {}, {}
    for n, v in validations.items():
        replays[n] = replay_table(v, decisions, targets_from_setup(fixture_setup(n)), cache)
    counts = {n: [(t.key, len(t.summary.windows)) for t in r.targets] for n, r in replays.items()}
    ok_shape = all(len(c) == 4 and c[-1][0] == "all_three" and all(w == 4 for _, w in c) for c in counts.values())
    cl.record(ok_shape, "Each synthetic mock is replayed on its three targets alone and on all three together, over four forward-in-time windows each", str(counts))
    clean = all(not plan_problems(v.runs[(r, "date")].plan, v.table) for v in validations.values() for (r, k) in v.runs if k == "date")
    cl.record(clean, "Every forward-in-time window was checked a second way (the Stage 3a split guard, which finds problems by a different route from the one that built them): none is leaky", "")
    exp = {n: [t.exploratory for t in r.targets] for n, r in replays.items()}
    cl.record(not any(exp["mock_easy"]) and exp["mock_hard"] == [True, False, False, True],
              "Exploratory labelling: on the hard mock only dissolution (the borderline result) and the all-three result that contains it are exploratory; nothing is on the easy mock", str(exp))
    consistent = all((t.summary.verdict != BEAT) or (t.summary.interval and t.summary.interval[0] > 0 and t.summary.gap > 0) for r in replays.values() for t in r.targets)
    cl.record(consistent, "Every 'beat random' verdict has a gain above 0 AND an error bar whose lower end is above 0", "")
    friab = [t for r in replays.values() for t in r.targets if t.key == "friability_pct"]
    cl.record(all(t.summary.verdict == NO_ROOM and any(f.rule == "M70" for f in t.findings) for t in friab) and bool(friab),
              "Friability (met by more than 99% of mock recipes anyway) is given 'no room to improve' and no verdict, with its message", f"{[round(t.summary.random_rate, 3) for t in friab]}")
    quiet = all(any(f.rule == "M71" and f.text for f in t.findings) for r in replays.values() for t in r.targets if not all(w.said for w in t.warned.values()))
    cl.record(quiet, "Where fewer than 30 picks were warned the replay says 'too few warned picks to say' instead of comparing them", "")
    # outcomes never reach the ranking: change every measured value in the windows
    v = validations["mock_hard"]
    r = "dissolution_30min_pct"
    models = {r: next(d.chosen for d in decisions if d.table == "mock_hard" and d.result == r)}
    targets = targets_from_setup(fixture_setup("mock_hard"))
    before, _ = build_windows(v, (r,), models, targets)
    run = v.runs[(r, "date")]
    shuffled = PlanRun(run.plan, [dataclasses.replace(f, y=np.where(np.arange(len(f.y)) % 2 == 0, 100.0, 0.0)) for f in run.folds])
    after, _ = build_windows(Validation(v.table, v.settings, {**v.runs, (r, "date"): shuffled}, v.findings), (r,), models, targets)
    same_picks = all(np.array_equal(pick(a.p), pick(b.p)) and np.array_equal(a.p, b.p) for a, b in zip(before, after))
    changed = any(not np.array_equal(a.passed, b.passed) for a, b in zip(before, after))
    cl.record(same_picks and changed, "Guard: replacing every measured value in the windows changes which recipes passed but not one probability and not one pick: nothing measured in a window reaches the ranking", "")
    # a planted leak in the real folds is refused before anything is ranked
    plan = run.plan
    leaked = dataclasses.replace(plan, folds=[Fold(f.number, np.append(f.train, f.test[0]) if f.number == 2 else f.train, f.test, f.held_out) for f in plan.folds])
    refused = False
    try:
        build_windows(Validation(v.table, v.settings, {**v.runs, (r, "date"): PlanRun(leaked, run.folds)}, v.findings), (r,), models, targets)
    except ReplayLeak:
        refused = True
    cl.record(refused, "Guard (planted leak): when one test recipe of window 2 is slipped into its training rows, the replay refuses to run (ReplayLeak) before ranking anything", "")
    # only synthetic tables
    refusals = []
    for label in (None, dataclasses.replace(v.table.label, files=tuple(dataclasses.replace(f, status="real") for f in v.table.label.files))):
        try:
            replay_table(Validation(dataclasses.replace(v.table, label=label), v.settings, v.runs, v.findings), decisions, targets)
            refusals.append(False)
        except ReplayRefused:
            refusals.append(True)
    cl.record(all(refusals), "The replay refuses any table that is not labelled synthetic (no label, or a 'real' label): it is only ever run on the mocks", str(refusals))
    return validations, replays, decisions


def report_checks(cl: Checklist, validations: dict, replays: dict, decisions: list) -> None:
    texts = {n: build_report(validations[n], replays[n]) for n in replays}
    every_head = all("SYNTHETIC DATA" in line for t in texts.values() for line in t.splitlines() if line.startswith("#"))
    cl.record(every_head, "Every heading of every replay report carries the data-status label (SYNTHETIC DATA)", "")
    hard = texts["mock_hard"]
    section = hard[hard.index("## Replayed, but exploratory"):hard.index("## Can the warning be trusted")]
    heads = [line for line in section.splitlines() if line.startswith("###")]
    cl.record(len(heads) == 2 and all("EXPLORATORY" in h for h in heads) and not any("EXPLORATORY" in line for line in texts["mock_easy"].splitlines() if line.startswith("#")),
              "Exploratory results sit in their own section with EXPLORATORY in every heading, and the easy mock's report has none", f"{len(heads)} headings")
    cl.record(all(UNIFYING_STATEMENT in t and "What these synthetic tables cannot show" in t for t in texts.values()),
              "Every replay report carries the unifying statement and the paragraph on what the synthetic tables cannot show (no supplier or date movement in the inputs)", "")
    rows = {n: [line for line in t.splitlines() if line.startswith("| ") and any(w in line for w in ("whole batches", "whole suppliers", "later dates"))] for n, t in texts.items()}
    words = ("picks out the large errors", "mixed", "does not", "cannot be judged")
    cl.record(all(len(r) == 3 and all(any(w in line for w in words) for line in r) for r in rows.values()),
              "Each report shows the warning's reading separately for whole batches, whole suppliers and later dates, each with its own word: never one lift number for all three", str({n: len(r) for n, r in rows.items()}))
    combined = [w for w in ("any check", "by any", "warned (any", "Warned (any") if any(w in t for t in texts.values())]
    cl.record(not combined and all(all(s in t for s in ("(1) Distance", "(2) Numeric range", "(3) Unseen supplier or product")) for t in texts.values()),
              "The warned-pick comparison keeps distance, numeric range and unseen supplier or product as three separate statuses, with no combined flag", str(combined))
    cl.record(not any(PROXY_PHRASE in t for t in texts.values()), "The mock reports do not use the stand-in-supplier wording (the mocks' binder suppliers are confirmed)", "")
    decisions_text = (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    cl.record(UNIFYING_STATEMENT in decisions_text.replace("**", "") and NO_REPLAY_SENTENCE in decisions_text,
              "docs/decisions.md contains the unifying statement and the fixed real-data sentence word for word", "")


def summary_checks(cl: Checklist, validations: dict, replays: dict, decisions: list) -> None:
    everything = all(fixture_available(n) for n in NAMES)
    if everything:
        full = {n: run_validation(build_table_for_setup(fixture_setup(n), None, PROJECT_ROOT, n), FULL, n_jobs=1, cache=CACHE, save=False) for n in NAMES if n not in MOCKS}
        full.update(validations)
        ordered = [full[n] for n in NAMES]
        decisions = decide_all(ordered)
    else:
        ordered = list(validations.values())
        cl.skip("The replay summary on every table (the real public data is not on this computer)", "only the synthetic mocks were summarised")
    summary = build_summary(ordered, decisions, replays)
    cl.record(UNIFYING_STATEMENT in summary and "What the synthetic tables cannot show" in summary and "SYNTHETIC DATA" in summary.splitlines()[0],
              "The summary opens with the synthetic label and carries the unifying statement and what the mocks cannot show", "")
    if not everything:
        return
    lines = [line for line in summary.splitlines() if line.startswith("- **batch_production,")]
    carried = [d for d in decisions if d.table == "batch_production" and d.status in (CARRIED, BORDERLINE)]
    said = [line for line in lines if line.endswith(NO_REPLAY_SENTENCE)]
    cl.record(len(carried) == 2 and len(said) == 2 and all("REAL" in line.upper() for line in said),
              "Real batch hardness and tensile strength: the summary says, word for word, 'Decision-usefulness replay not run; no client-specified target exists for this result...' for each, labelled as real public data", f"{len(said)} of {len(carried)}")
    after = [line.split("): ", 1)[1] for line in said]
    cl.record(all(a == NO_REPLAY_SENTENCE for a in after) and "batch_production" not in " ".join(r.table for r in replays.values()) and not any(w in " ".join(after) for w in ("kP", "between", "at least", "at most")),
              "No window or target of any kind appears for the real data: nothing but the fixed sentence", "")
    not_carried = [line for line in lines if "replay not run; it was not carried" in line]
    cl.record(len(not_carried) >= 2, "Real results that were not carried in 3b-1 are listed as not replayed, with the reason", f"{len(not_carried)} lines")
    named = [line for line in summary.splitlines() if "api_code" in line]
    cl.record(all(PROXY_PHRASE in line for line in named), "Any line naming api_code says 'proxy, not a confirmed supplier'", f"{len(named)} lines")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 3b-3: the decision-usefulness replay (synthetic mocks only: would ranking recipes by a model have chosen better than chance?)")
    before = project_files()
    known_answer_checks(cl)
    guard_checks(cl)
    validations, replays, decisions = saved_checks(cl)
    if replays:
        report_checks(cl, validations, replays, decisions)
        summary_checks(cl, validations, replays, decisions)
        for n, rep in replays.items():
            for t in rep.targets:
                s = t.summary
                cl.headline(f"{n}, {t.key}{' (exploratory)' if t.exploratory else ''}: picked {100 * s.picked_rate:.1f}% against random {100 * s.random_rate:.1f}% and perfect {100 * s.perfect_rate:.1f}% ({s.verdict})")
    found = forbidden_in(sorted((ROOT / "cellpoc" / "modelling").glob("*.py")))
    cl.record(not found, "The modelling code, including the replay, contains no random splitter or sampler", "; ".join(found[:3]))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
