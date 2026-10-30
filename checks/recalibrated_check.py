"""Health check for the recalibrated response to a stale target (R), the rule 5 response adopted on 2026-10-12 as the platform engine's (docs/decisions.md, 'Adoption of R').

In plain words it checks that: the evidence classes are exact (at most 2 misses in the last 6 is FINE; at least 3 misses with at least 5 of the 6 signed errors the same way is an OFFSET corrected by their median; at
least 3 misses without that is MIXED), the judgement uses the SIGNED error (errors of equal size and opposite sign are never an offset), fewer than 6 measurements never claim an offset; the engine makes exactly
the same decisions as the current governed engine while the watch has not fired; there is no gap after the watch fires (the very first decision at which a target is stale already classes it from the last 6
measurements); a correction moves a stated range and the predicted mean by exactly that amount and leaves the width alone, and the chance is recomputed from the moved values; the promise check sends a hopeless
corrected model to the current response (exploration) and leaves a promising one alone; a MIXED target keeps the current response; the naive variant always re-centres and never falls back; a measurement from the
decision's own trial or later is still refused; a sealed seed is still refused; the adoption scope statement equals the one recorded in docs/decisions.md word for word, and the engine lock covers this file; and nothing is written into the project. It never touches the sealed lab.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.contracts import Observation  # noqa: E402
from cellpoc.contracts.seeds import SealedSeedError  # noqa: E402
from cellpoc.decision_engine.governed import FutureLeak, GovernedStrategy  # noqa: E402
from cellpoc.comparison.dev_comparison import build_strategy  # noqa: E402
from cellpoc.decision_engine.recalibrated import ADOPTED_SCOPE, FINE, MIXED, OFFSET, PROMISE, RECAL_WINDOW, RecalibratedStrategy, classify  # noqa: E402
from checks import comparison_check  # noqa: E402
from cellpoc.modelling.models import FAST  # noqa: E402
from checks import architecture, engine_check as ec  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402


def recal_of(eng: GovernedStrategy, naive: bool = False, seed: int = 10901) -> RecalibratedStrategy:
    return RecalibratedStrategy(eng.brief, eng.targets, eng.history, eng.space, eng.ingredients, eng.balance, seed, FAST, naive=naive)


def class_checks(cl: Checklist) -> None:
    cases = {
        "2 misses, any signs: FINE": ([-5, -4, -6, 5, 1, 0.5], [1, 1, 0, 0, 0, 0], (FINE, 0.0)),
        "2 misses, all one sign: still FINE": ([-5, -4, -6, -5, -4, -5], [1, 1, 0, 0, 0, 0], (FINE, 0.0)),
        "3 misses, 6 of 6 one sign: OFFSET by the median": ([-5, -4, -6, -5, -4, -5], [1, 1, 1, 0, 0, 0], (OFFSET, -5.0)),
        "3 misses, 5 of 6 one sign: OFFSET": ([-5, -4, -6, -5, -4, 1], [1, 1, 1, 0, 0, 0], (OFFSET, -4.5)),
        "3 misses, 4 of 6 one sign: MIXED": ([-5, -4, -6, -5, 4, 5], [1, 1, 1, 0, 0, 0], (MIXED, 0.0)),
        "equal and opposite errors are never an offset (signed, not absolute)": ([5, -5, 5, -5, 5, -5], [1, 1, 1, 1, 1, 1], (MIXED, 0.0)),
        "fewer than 6 measurements never claim an offset": ([-5, -5, -5, -5, -5], [1, 1, 1, 1, 1], (MIXED, 0.0)),
        "a positive offset is corrected positively": ([4, 5, 3, 6, 4, 5], [1, 1, 0, 1, 0, 1], (OFFSET, 4.5)),
    }
    got = {k: classify(res, [bool(m) for m in miss]) for k, (res, miss, _) in cases.items()}
    bad = {k: (got[k], cases[k][2]) for k in cases if got[k][0] != cases[k][2][0] or abs(got[k][1] - cases[k][2][1]) > 1e-12}
    cl.record(RECAL_WINDOW == 6 and not bad, "The evidence classes are exact: at most 2 misses of the last 6 is FINE; at least 3 misses with at least 5 of 6 signed errors the same way is an OFFSET corrected by their median; otherwise MIXED; the judgement uses the signed error; fewer than 6 measurements never claim an offset",
              f"{len(cases) - len(bad)} of {len(cases)} cases; wrong: {list(bad)[:2]}")


def same_as_current_checks(cl: Checklist) -> None:
    lab, g = ec.world("period_shift")
    lab2, _ = ec.world("period_shift")
    r = recal_of(g)
    obs_g = ec.campaign(lab, g, 12)
    obs_r = ec.campaign(lab2, r, 12)
    same = all(g.log[t].recipe == r.log[t].recipe and g.log[t].kind == r.log[t].kind for t in range(1, 13))
    quiet = all(not r.recal_log[t]["watch_stale"] for t in range(1, 13))
    cl.record(same and quiet and len(obs_g) == len(obs_r) == 12, "While the watch has not fired (it cannot before the 13th decision) the recalibrated engine makes exactly the same decisions as the current governed engine, trial for trial", f"12 decisions compared, the watch fired in {sum(1 for t in range(1, 13) if r.recal_log[t]['watch_stale'])}")


def no_gap_checks(cl: Checklist) -> None:
    lab, g = ec.world("period_shift", n=3000)                                    # the real history size: in a small history a refit absorbs a few shifted rows at once and FINE is then the right class
    r = recal_of(g)
    ec.campaign(lab, r, 16)
    first = min((t for t, v in r.recal_log.items() if v["watch_stale"]), default=None)
    log = r.recal_log.get(first, {})
    classed = bool(log) and set(log["classes"]) == set(log["watch_stale"]) and all(c in (FINE, OFFSET, MIXED) for c in log["classes"].values())
    direction = {"dissolution_30min_pct": -1, "hardness_kp": 1, "friability_pct": -1}                       # the step lowers dissolution, raises hardness, and so lowers friability
    right_way = bool(log.get("offsets")) and all(np.sign(v) == direction[k] for k, v in log["offsets"].items())
    cl.record(first is not None and first >= 13 and classed and OFFSET in log["classes"].values() and right_way,
              "No gap after the watch fires: at the very first decision at which a target is stale (13 or later) every stale target is already classed from its last 6 measurements, and in the period shift at least one is recognised as an OFFSET, every correction in the direction the step moves that result",
              f"first stale decision {first}; classes {log.get('classes')}; offsets {({k: round(v, 2) for k, v in log.get('offsets', {}).items()})}")


def correction_checks(cl: Checklist) -> None:
    lab, g = ec.world("period_shift")
    r = recal_of(g)
    ec.campaign(lab, r, 12)
    frame = r._candidates(13, r.history, [], lab.context(13))[2].iloc[:40]
    r._offsets = {}
    p0 = r._predict(frame)
    r._offsets = {"hardness_kp": 1.5}
    p1 = r._predict(frame)
    w = lambda p, k: p[k]["hi"] - p[k]["lo"]
    moved = np.allclose(p1["hardness_kp"]["mean"], p0["hardness_kp"]["mean"] + 1.5) and np.allclose(p1["hardness_kp"]["lo"], p0["hardness_kp"]["lo"] + 1.5) and np.allclose(p1["hardness_kp"]["hi"], p0["hardness_kp"]["hi"] + 1.5)
    same_width = np.allclose(w(p1, "hardness_kp"), w(p0, "hardness_kp"))
    others = all(np.array_equal(p1[k][f], p0[k][f]) for k in ("dissolution_30min_pct", "friability_pct") for f in ("mean", "lo", "hi", "chance"))
    chance_changed = not np.allclose(p1["hardness_kp"]["chance"], p0["hardness_kp"]["chance"])
    r._offsets = {}
    cl.record(moved and same_width and others and chance_changed,
              "A correction moves a target's predicted mean and stated range by exactly that amount, leaves the width alone, changes no other target, and the chance is worked out again from the moved values", f"{len(frame)} candidates compared")


def routing_checks(cl: Checklist) -> None:
    lab, g = ec.world("period_shift")
    r = recal_of(g)
    obs = ec.campaign(lab, r, 12)
    every = tuple(t.result for t in r.trusted)
    r._stale = lambda done: every                                              # force every modelled target stale (the watch itself is tested in engine_check)
    results = {}
    for name, answer in (("hopeless", {t: (OFFSET, -1000.0) for t in every}), ("promising", {t: (OFFSET, 0.0) for t in every}), ("fine", {t: (FINE, 0.0) for t in every}), ("mixed", {t: (MIXED, 0.0) for t in every})):
        e = recal_of(g)
        e._stale = lambda done: every
        e._classes = lambda done, stale, a=answer: {t: a[t] for t in stale}
        ec.campaign(lab, e, 12)
        d = e.propose(13, lab.context(13), obs)
        results[name] = (d.kind, d.stale, e.recal_log[13]["gate"])
    ok_hopeless = results["hopeless"][2] == "fallback" and results["hopeless"][0] == "stale_exploration" and set(results["hopeless"][1]) == set(every)
    ok_promising = results["promising"][2] is None and results["promising"][1] == () and results["promising"][0] != "stale_exploration"
    ok_fine = results["fine"][1] == () and results["fine"][2] is None and results["fine"][0] != "stale_exploration"
    ok_mixed = set(results["mixed"][1]) == set(every) and results["mixed"][0] == "stale_exploration"
    cl.record(PROMISE == 0.5 and ok_hopeless and ok_promising and ok_fine and ok_mixed,
              "Routing: a corrected model that sees no promising recipe (best chance below 0.5) falls back to the current response (exploration, the targets reported stale); a promising one keeps choosing by the ranking; FINE keeps choosing as normal; MIXED keeps the current response",
              str({k: (v[0], v[2]) for k, v in results.items()}))
    naive = recal_of(g, naive=True)
    naive._stale = lambda done: every
    naive._classes = lambda done, stale: {t: (OFFSET, -1000.0) for t in stale}
    ec.campaign(lab, naive, 12)
    dn = naive.propose(13, lab.context(13), obs)
    real_naive = recal_of(g, naive=True)
    ec.campaign(lab, real_naive, 12)
    classes = real_naive._classes(obs, every)
    cl.record(naive.recal_log[13]["gate"] is None and dn.stale == () and all(c == OFFSET for c, _ in classes.values()),
              "The naive variant always re-centres every stale target (the real class of each is OFFSET, whatever the evidence) and never falls back, even when the corrected model sees nothing promising", f"classes {({k: v[0] for k, v in classes.items()})}")


def other_checks(cl: Checklist) -> None:
    lab, g = ec.world()
    r = recal_of(g)
    obs = ec.campaign(lab, r, 5)
    try:
        recal_of(g).propose(6, lab.context(6), obs[:5] + [Observation(9, obs[0].recipe, obs[0].context, obs[0].results)])
        leak = False
    except FutureLeak:
        leak = True
    try:
        RecalibratedStrategy(g.brief, g.targets, g.history, g.space, g.ingredients, g.balance, 7_000_105, FAST)
        sealed = False
    except SealedSeedError:
        sealed = True
    again = r.propose(3, lab.context(3), obs[:2])
    cl.record(leak and sealed and again == r.log[3], "A measurement from a later trial is still refused, a sealed seed is still refused, and asking twice gives the same decision", f"leak refused {leak}, sealed refused {sealed}")


def adoption_checks(cl: Checklist) -> None:
    """R is the adopted platform engine: its scope statement must equal, word for word, the one recorded in docs/decisions.md; the comparison machinery can build it; and its file is under the engine lock."""
    text = (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    recorded = ADOPTED_SCOPE in text.replace("\n", " ")
    built = isinstance(build_strategy("recalibrated", "baseline", ec.brief_of({}), 10_931), RecalibratedStrategy) and not isinstance(build_strategy("governed", "baseline", ec.brief_of({}), 10_931), RecalibratedStrategy)
    locked = "cellpoc/decision_engine/recalibrated.py" in comparison_check.LOCKED
    cl.record(recorded and built and locked,
              "The adopted engine's scope statement (ADOPTED_SCOPE) equals, word for word, the text recorded in docs/decisions.md (so a summary or scorecard that carries it cannot drift); the comparison machinery builds the adopted engine as 'recalibrated' and the 4-4 engine as 'governed'; the engine lock covers recalibrated.py",
              f"recorded verbatim {recorded}, builds {built}, locked {locked}")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 4: the recalibrated response to a stale target, the adopted rule 5 response (are its classes, its correction and its safeguards exact, and is its scope recorded?)")
    before = project_files()
    class_checks(cl)
    same_as_current_checks(cl)
    no_gap_checks(cl)
    correction_checks(cl)
    routing_checks(cl)
    other_checks(cl)
    adoption_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
