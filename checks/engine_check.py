"""Health check for Stage 4-3 (the governed decision engine): does it follow its five rules, on worlds where the right answer is known?

In plain words it checks, with the development lab and a hand-made brief (so the right answer is known), that:
 - RULE 1: a target Stage 3 did not carry (not assessed, or only exploratory) never enters a stated probability: no model is fitted for it, it is never in a decision's chances or stated ranges, a combined
   chance is never stated while any target is unmodelled, the plain-words reason says so, and changing every value of that target changes no prediction of the targets that are modelled;
   only the one model the brief names is ever fitted for a carried target;
 - RULE 2: with a target unmodelled, the engine alternates farthest-from-everything and local search once a measured pass exists, and picks from the top 20% by chance of the modelled targets;
 - RULE 3: a recipe warned by the distance, range or unseen-category check is never an ordinary pick (exploit, spread-out or local) in 270 trials across three scenarios, including the trials where the
   best-looking candidate WAS warned, exploratory picks are labelled and never more than one in any five consecutive trials;
 - RULE 4: a supplier or filler grade never seen in the training data causes exactly three bridging trials, re-measuring the best distinct measured passes, after which the models are refitted on it;
   the baseline never bridges;
 - RULE 5: the staleness watch is silent before 12 measurements, fires at 7 or fewer hits of the last 12 and not at 8, slides, and recovers; a stale target's chance is not used and no combined chance is stated;
 - a stated range is widened by the brief's factor exactly, and is never narrower than the model stated;
 - a LEAK is refused: a measurement from the decision's own trial or any later one raises an error, and changing a later measurement never changes an earlier decision;
 - with too few rows no model is fitted and the engine says so; with nothing carried it works by measurement alone; asking twice gives the same decision; models are refitted every 5 trials; every explanation is in plain words.
Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.contracts import BRIEF_VERSION, Decision, EngineBrief, Observation, TargetBrief, TargetSpec, TrialContext  # noqa: E402
from cellpoc.contracts.seeds import refuse_sealed_seed  # noqa: E402
from cellpoc.decision_engine.governed import (BRIDGING_TRIALS, EXPLORATORY_EVERY, REFIT_EVERY, STALE_MAX_HITS, STALE_WINDOW, TOP_SHARE, FutureLeak, GovernedStrategy)  # noqa: E402
from cellpoc.modelling.models import FAST  # noqa: E402
from cellpoc.virtual_lab import _dev_truth as truth  # noqa: E402
from cellpoc.virtual_lab import dev_oracle as oracle  # noqa: E402
from cellpoc.virtual_lab.dev_lab import SCENARIOS, DevLab  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

NUM = ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kn", "blend_time_min")
CAT = ("binder_supplier", "filler_grade", "dissolution_instrument")
RESULTS = ("dissolution_30min_pct", "hardness_kp", "friability_pct")
MODEL_OF = {"dissolution_30min_pct": "quadratic", "hardness_kp": "linear", "friability_pct": "quadratic"}
SPECS = {"dissolution_30min_pct": TargetSpec("dissolution_30min_pct", "Dissolution", "at_least", 85.0, None), "hardness_kp": TargetSpec("hardness_kp", "Hardness", "between", 6.0, 10.0),
         "friability_pct": TargetSpec("friability_pct", "Friability", "at_most", None, 1.0)}
WORDS = re.compile(r"\b(nan|none|traceback|exception|dataframe|numpy|undefined)\b|\{|\}", re.IGNORECASE)


def brief_of(status: dict, factor: float = 1.0) -> EngineBrief:
    targets = []
    for r in RESULTS:
        s = status.get(r, "carried")
        targets.append(TargetBrief(r, SPECS[r].label, s, MODEL_OF[r] if s != "not_assessed" else None, MODEL_OF[r], "honest", "honest", factor if s != "not_assessed" else None, "made up",
                                   "" if s == "carried" else "not predictable here", (), NUM, CAT))
    return EngineBrief(BRIEF_VERSION, "made_up", "SYNTHETIC DATA", "", tuple(targets), ())


def world(scenario: str = "baseline", status: dict | None = None, n: int = 600, seed: int = 10101, engine_seed: int = 10901, factor: float = 1.0, history: pd.DataFrame | None = None):
    refuse_sealed_seed(engine_seed, "the engine check's world builder")
    lab = DevLab(SCENARIOS[scenario], seed)
    h = history if history is not None else lab.history(n).rename(columns={"compression_force_kN": "compression_force_kn", "hardness": "hardness_kp"})
    eng = GovernedStrategy(brief_of(status or {}, factor), SPECS, h, {k: truth.LIM[k] for k in NUM}, ("drug_pct", "binder_pct", "disintegrant_pct", "lubricant_pct"),
                           ("filler_pct", truth.FILLER_RANGE), engine_seed, FAST)
    return lab, eng


def campaign(lab, eng, trials: int, corrupt: int | None = None, context=None) -> list:
    obs = []
    for t in range(1, trials + 1):
        ctx = context(t) if context else lab.context(t)
        d = eng.propose(t, ctx, obs)
        m = lab.measure(t, d.recipe, ctx)
        if corrupt == t:
            m = {k: v * 100.0 for k, v in m.items()}
        obs.append(Observation(t, d.recipe, ctx, m))
    return obs


def rule1_checks(cl: Checklist) -> None:
    lab, eng = world(status={"dissolution_30min_pct": "not_assessed"})
    campaign(lab, eng, 12)
    ds = list(eng.log.values())
    clean = all("dissolution_30min_pct" not in d.chances and "dissolution_30min_pct" not in d.stated_ranges and "all_targets" not in d.chances for d in ds)
    said = all("Not modelled: Dissolution" in d.why and "not stated" in d.why for d in ds if d.kind != "bridging")
    fitted = {r for r, _ in eng.models_fitted}
    cl.record(clean and said and fitted == {"hardness_kp", "friability_pct"} and all(d.unmodelled == ("dissolution_30min_pct",) for d in ds),
              "RULE 1, untrusted target never enters the probability: with dissolution not assessed, no decision ever states a chance or a range for it, no combined chance is ever stated, no model is fitted for it, and every explanation says it is not modelled",
              f"{len(ds)} decisions; models fitted for {sorted(fitted)}")
    lab2, e1 = world(status={"dissolution_30min_pct": "not_assessed"})
    clean_h = e1.history
    garbage = clean_h.copy()
    garbage["dissolution_30min_pct"] = np.random.default_rng(1).uniform(0, 100, len(garbage))
    _, e2 = world(status={"dissolution_30min_pct": "not_assessed"}, history=garbage)
    for e in (e1, e2):
        e._ensure_fits(1, e.history, [])
    frame = e1._candidates(1, e1.history, [], lab2.context(1))[2]
    p1, p2 = e1._predict(frame), e2._predict(frame)
    same = set(p1) == set(p2) == {"hardness_kp", "friability_pct"} and all(np.array_equal(p1[r][k], p2[r][k]) for r in p1 for k in p1[r])
    cl.record(same and e1.models_fitted == e2.models_fitted,
              "RULE 1, changing every dissolution value in the data (random numbers instead) changes no prediction, range or chance of the modelled targets, and the same models are fitted", f"{frame.shape[0]} candidates compared")
    lab3, e3 = world(status={"dissolution_30min_pct": "exploratory"})
    campaign(lab3, e3, 6)
    cl.record(all(r != "dissolution_30min_pct" for r, _ in e3.models_fitted) and all("dissolution_30min_pct" not in d.chances for d in e3.log.values()),
              "RULE 1, a result that is only carried-but-exploratory is treated exactly like a not-assessed one: no model, no chance", "")
    lab4, e4 = world()
    campaign(lab4, e4, 12)
    cl.record(sorted(set(e4.models_fitted)) == sorted((r, MODEL_OF[r]) for r in RESULTS) and len(e4.models_fitted) == 9 and e4._fit_trial == 11,
              f"Only the one model the brief names is ever fitted for a carried result, and the models are refitted every {REFIT_EVERY} trials (trials 1, 6 and 11 of 12: nine fits in all)", str(sorted(set(e4.models_fitted))))
    combined = [("all_targets" in d.chances) for d in e4.log.values() if d.kind in ("exploit", "exploratory")]
    cl.record(all(combined) and combined, "When every target is modelled and none is stale, a combined chance is stated", f"{len(combined)} decisions")


def rule2_checks(cl: Checklist) -> None:
    lab, eng = world(status={"dissolution_30min_pct": "not_assessed"})
    campaign(lab, eng, 4)
    kinds = [eng.log[t].kind for t in (1, 2, 3, 4)]
    cl.record(kinds == ["space_filling", "local_search", "space_filling", "local_search"],
              "RULE 2, with a target unmodelled and a measured pass available, the engine alternates farthest-from-everything (odd trials) and local search around the best measured passes (even trials)", str(kinds))
    lab, eng = world(status={"dissolution_30min_pct": "not_assessed"})
    campaign(lab, eng, 20)
    floors = [(eng.trace[t]["pool_floor"], eng.trace[t]["pick_chance"]) for t in eng.trace if eng.trace[t]["pool_floor"] is not None]
    cl.record(bool(floors) and all(pick >= floor - 1e-12 for floor, pick in floors) and all(0.0 <= floor <= 1.0 for floor, _ in floors),
              f"RULE 2, every such pick comes from the top {TOP_SHARE:.0%} of candidates by chance of the modelled targets", f"{len(floors)} picks checked")
    _, none = world(status={r: "not_assessed" for r in RESULTS})
    lab, none = world(status={r: "not_assessed" for r in RESULTS})
    campaign(lab, none, 8)
    d = list(none.log.values())
    cl.record(all(x.kind in ("space_filling", "local_search") and not x.chances and not x.stated_ranges for x in d) and not none.models_fitted and all("No target is carried" in x.why for x in d),
              "With nothing carried the engine fits no model, states no chance, works by measurement alone (spread-out and local search) and says why", f"{len(d)} decisions")


def rule3_checks(cl: Checklist) -> None:
    bad, exploratory_flagged, window_ok, total, fallbacks = [], True, True, 0, 0
    kinds = ("distance", "range", "category")
    warned_total, binding, ordinary_warned, exploratory_warned = ({k: 0 for k in kinds} for _ in range(4))
    for scenario in ("baseline", "new_supplier", "period_shift"):
        for seed in (10901, 10902, 10903):
            lab, eng = world(scenario, engine_seed=seed)
            campaign(lab, eng, 30)
            for t, d in eng.log.items():
                total += 1
                if d.kind in ("exploit", "space_filling", "local_search") and any(d.warnings.values()):
                    bad.append((scenario, seed, t, d.kind, d.warnings))
                for k in kinds:
                    ordinary_warned[k] += int(d.warnings.get(k, False) and d.kind in ("exploit", "space_filling", "local_search"))
                    exploratory_warned[k] += int(d.warnings.get(k, False) and d.kind == "exploratory")
                if d.kind == "exploratory" and not any(d.warnings.values()) and "Every candidate was unvouched" not in d.why:
                    exploratory_flagged = False
                if d.kind == "exploratory" and any(eng.log[u].kind == "exploratory" for u in range(t - EXPLORATORY_EVERY + 1, t) if u in eng.log) and "Every candidate was unvouched" not in d.why:
                    window_ok = False
            for v in eng.trace.values():
                for k in kinds:
                    warned_total[k] += v["warned_by"][k]
                    binding[k] += int(k in v["best_overall_warned_by"])
            fallbacks += eng.fallbacks
    cl.record(not bad and total == 270 and not any(ordinary_warned.values()), "RULE 3, unvouched recipe never an ordinary pick: in 270 trials (3 scenarios, 3 engine seeds, 30 trials each) no exploit, spread-out or local-search pick was warned by the distance, range or unseen-category check",
              f"{total} trials; breaches: {bad[:2]}")
    cl.record(binding["distance"] >= 5, "RULE 3 was really tested, for the distance check: in at least five of those trials the best-looking candidate overall WAS warned by distance and the engine did not take it as an ordinary pick",
              f"best-looking candidate warned by distance in {binding['distance']} trials; by range in {binding['range']}; by unseen category in {binding['category']}")
    cl.headline(f"RULE 3, the 270 trials by warning type (measured): candidates warned by distance {warned_total['distance']:,}, by numeric range {warned_total['range']}, by unseen category {warned_total['category']}; exploratory picks warned by "
                f"distance {exploratory_warned['distance']}, range {exploratory_warned['range']}, category {exploratory_warned['category']}. Range and category never fire for an ordinary pick in these worlds (candidates lie inside a design space the training data already spans; "
                f"an unseen category belongs to the whole trial's context, which rule 4 handles), so each type is also tested on its own below")
    cl.record(exploratory_flagged and window_ok and fallbacks == 0, "RULE 3, exploratory picks are labelled, always warned by at least one check, and never more than one in any five consecutive trials (so at most six in 30)", f"{fallbacks} cases where every candidate was unvouched")


def isolated_status_checks(cl: Checklist) -> None:
    """Each warning type tested ON ITS OWN: the warning function is replaced by one that flags only that type, over a known region (drug load above 22), so the right answer is known."""
    for status in ("distance", "range", "category"):
        lab, eng = world()

        def only(frame, status=status):
            n = len(frame)
            flags = {k: np.zeros(n, bool) for k in ("distance", "range", "category")}
            flags[status] = (frame["drug_pct"] > 22.0).to_numpy()
            return flags
        eng._warnings = only
        campaign(lab, eng, 25)
        ordinary = [d for d in eng.log.values() if d.kind in ("exploit", "space_filling", "local_search")]
        exploratory = [d for d in eng.log.values() if d.kind == "exploratory"]
        ok_ordinary = bool(ordinary) and all(not any(d.warnings.values()) and d.recipe["drug_pct"] <= 22.0 for d in ordinary)
        ok_explore = len(exploratory) >= 3 and all(d.warnings[status] and sum(d.warnings.values()) == 1 and d.recipe["drug_pct"] > 22.0 for d in exploratory)
        window = all(not any(eng.log[u].kind == "exploratory" for u in range(t - EXPLORATORY_EVERY + 1, t) if u in eng.log) for t in (d.trial_number for d in exploratory))
        cl.record(ok_ordinary and ok_explore and window,
                  f"RULE 3 for the {status.upper()} warning on its own: no ordinary pick is in the flagged region, every exploratory pick is, each is labelled with only that type, and never more than one in any five consecutive trials",
                  f"{len(ordinary)} ordinary picks all outside the region; {len(exploratory)} exploratory picks all inside it")


def drift_checks(cl: Checklist) -> None:
    """The engine repeats two small Stage 3 helpers (it may not import that module). This fails if the two copies ever disagree on the same input."""
    from cellpoc.decision_engine.governed import calibration_mask as engine_mask
    from cellpoc.decision_engine.governed import inner_folds as engine_folds
    from cellpoc.modelling.splits import _labels, make_fold_plan
    from cellpoc.modelling.validate import calibration_mask as stage3_mask
    from cellpoc.modelling.validate import inner_folds as stage3_folds
    from checks.models_check import random_table
    rng = np.random.default_rng(404)
    compared = folds_seen = 0
    wrong = []
    for i in range(60):
        table = random_table(rng, f"t{i}")
        plan = make_fold_plan(table, "y", "batch")
        if not plan.available:
            continue
        for fold in plan.folds:
            labels = _labels(table.frame, fold.train, table.groups["batch"].columns)[0].to_numpy()
            a, b = stage3_folds(table, plan, fold.train), engine_folds(labels)
            same_folds = (a is None and b is None) or (a is not None and b is not None and len(a) == len(b) and all(np.array_equal(x[0], y[0]) and np.array_equal(x[1], y[1]) for x, y in zip(a, b)))
            m3, me = stage3_mask(table, plan, fold.train), engine_mask(labels)
            same_mask = (m3 is None and me is None) or (m3 is not None and me is not None and np.array_equal(m3, me))
            compared += 1
            folds_seen += 0 if a is None else len(a)
            if not (same_folds and same_mask):
                wrong.append((i, fold.number))
    sensitive = False
    for i in range(10):
        table = random_table(np.random.default_rng(i), "s")
        plan = make_fold_plan(table, "y", "batch")
        for fold in (plan.folds if plan.available else []):
            labels = _labels(table.frame, fold.train, table.groups["batch"].columns)[0].to_numpy()
            a, b = stage3_folds(table, plan, fold.train), engine_folds(labels, k=3)
            if a is not None and b is not None and (len(a) != len(b) or any(not np.array_equal(x[1], y[1]) for x, y in zip(a, b))):
                sensitive = True
    cl.record(not wrong and compared >= 100 and folds_seen >= 300 and sensitive,
              "The two helpers the engine repeats from Stage 3 (the whole-batch inner folds that choose a ridge penalty, and the calibration group kept apart for a conformal range) agree exactly with the Stage 3 originals on "
              "every fold of 60 random tables, and the comparison itself is sensitive (a copy with 3 folds instead of 5 is caught)", f"{compared} folds compared, {folds_seen} inner folds; disagreements {wrong[:3]}")

def rule4_checks(cl: Checklist) -> None:
    lab, eng = world("new_supplier")
    obs = campaign(lab, eng, 14)
    kinds = [eng.log[t].kind for t in range(1, 15)]
    bridged = [t for t in range(1, 15) if kinds[t - 1] == "bridging"]
    named = all(eng.log[t].new_context == (("binder_supplier", "D"),) for t in bridged)
    # the three anchors, worked out independently: the best distinct measured passes, by the worst slack in units of each result's own spread
    # "measured" means the history AND the engine's own earlier campaign trials (trials 1 to 7 were measured before bridging began)
    rows = pd.concat([eng.history[list(NUM) + list(RESULTS)], pd.DataFrame([{**o.recipe, **o.results} for o in obs[:7]])[list(NUM) + list(RESULTS)]], ignore_index=True)
    scale = {r: float(eng.history[r].std()) for r in RESULTS}
    def slack(row):
        return min((row["dissolution_30min_pct"] - 85.0) / scale["dissolution_30min_pct"], (row["hardness_kp"] - 6.0) / scale["hardness_kp"], (10.0 - row["hardness_kp"]) / scale["hardness_kp"],
                   (1.0 - row["friability_pct"]) / scale["friability_pct"])
    ranked = rows.assign(m=rows.apply(slack, axis=1)).sort_values("m", ascending=False, kind="stable").drop_duplicates(subset=list(NUM))
    anchors = [{k: float(ranked.iloc[i][k]) for k in NUM} for i in range(3)]
    same = all(all(abs(eng.log[8 + i].recipe[k] - anchors[i][k]) < 1e-9 for k in NUM) for i in range(3))
    cl.record(bridged == [8, 9, 10] and named and same,
              f"RULE 4, a supplier never seen in the training data (D, from trial 8) causes exactly {BRIDGING_TRIALS} bridging trials (8, 9, 10), each re-measuring one of the best three distinct measured passes, in the order of their margin", f"bridging trials {bridged}")
    counted = all(set(eng.log[t].stated_ranges) == set(RESULTS) for t in (8, 9, 10)) and all(lo < hi for t in (8, 9, 10) for lo, hi in eng.log[t].stated_ranges.values())
    cl.record(counted and len(eng.hit_sequences(obs)["hardness_kp"]) == len([t for t in range(1, 15) if eng.log[t].stated_ranges and t <= 14 and t in {o.trial_number for o in obs}]),
              "Bridging trials carry the range the existing models would have stated, so the staleness watch counts them like every other trial", "")
    cl.record(kinds[10] != "bridging" and ("binder_supplier", "D") in eng._fit_known and "D" in eng.fits["hardness_kp"][0].levels_["binder_supplier"] and eng._fit_trial == 11,
              "RULE 4, after the third bridging trial the models are refitted at once on the new data, so supplier D is a known level and trial 11 is an ordinary decision", f"last fit at trial {eng._fit_trial}")
    base = world("baseline")[1].history
    lab2, eng2 = world("baseline", history=base[base["filler_grade"] == "MCC-101"].reset_index(drop=True))      # a history in which filler grade MCC-102 never occurs

    def second(t):
        ctx = lab2.context(t)
        if t >= 12:
            return TrialContext({**ctx.categories, "filler_grade": "MCC-102"}, ctx.batch_id, ctx.day_fraction)
        return ctx
    campaign(lab2, eng2, 16, context=second)
    again = [t for t in range(1, 17) if eng2.log[t].kind == "bridging"]
    cl.record(again == [12, 13, 14] and all(eng2.log[t].new_context == (("filler_grade", "MCC-102"),) for t in again),
              "RULE 4 again: a filler grade never seen (MCC-102 from trial 12) causes exactly three bridging trials of its own, and nothing bridged before that", f"bridging trials {again}")


def rule5_checks(cl: Checklist) -> None:
    lab, eng = world()
    ctx = lab.context(1)

    def stale_after(hits):
        e = world()[1]
        done = []
        for i, h in enumerate(hits, 1):
            e.log[i] = Decision(i, {}, "exploit", "", stated_ranges={"hardness_kp": (6.0, 10.0)})
            done.append(Observation(i, {}, ctx, {"hardness_kp": 8.0 if h else 20.0}))
        return e._stale(done)
    cases = {"11 misses": ([False] * 11, ()), "12 misses": ([False] * 12, ("hardness_kp",)), "7 hits of 12": ([True] * 7 + [False] * 5, ("hardness_kp",)), "8 hits of 12": ([True] * 8 + [False] * 4, ()),
             "slides: 12 misses then 8 hits": ([False] * 12 + [True] * 8, ()), "slides: 12 misses then 7 hits": ([False] * 12 + [True] * 7, ("hardness_kp",)), "all hits": ([True] * 20, ())}
    got = {k: stale_after(h) for k, (h, _) in cases.items()}
    cl.record(STALE_WINDOW == 12 and STALE_MAX_HITS == 7 and all(got[k] == e for k, (_, e) in cases.items()),
              "RULE 5, the staleness watch is exact: silent with 11 measurements, stale at 7 or fewer hits of the last 12 and not at 8, it slides with new measurements, and it recovers", str({k: bool(v) for k, v in got.items()}))
    lab, eng = world("period_shift")
    campaign(lab, eng, 30)
    stale_trials = [t for t, d in eng.log.items() if d.stale]
    cl.record(bool(stale_trials) and min(stale_trials) >= 13 and all("dissolution_30min_pct" not in eng.log[t].chances for t in stale_trials if "dissolution_30min_pct" in eng.log[t].stale)
              and all("all_targets" not in eng.log[t].chances for t in stale_trials) and all(eng.log[t].kind == "stale_exploration" for t in stale_trials if len(eng.log[t].chances) < 3 and eng.log[t].kind != "bridging"),
              "RULE 5 in action: when the period shifts (true step from trial 6) the watch fires no earlier than trial 13, a stale target's chance is never used, no combined chance is stated while it is stale, and the picks are labelled exploration",
              f"stale at trials {stale_trials[:4]}...")
    f_lab, f2 = world(factor=2.0)
    f_lab, f1 = world(factor=1.0)
    f_lab, f05 = world(factor=0.5)
    frames = []
    for e in (f1, f2, f05):
        e._ensure_fits(1, e.history, [])
        frames.append(e._predict(f1._candidates(1, f1.history, [], f_lab.context(1))[2]))
    width = lambda p, r: p[r]["hi"] - p[r]["lo"]
    ok = all(np.allclose(width(frames[1], r), 2.0 * width(frames[0], r), rtol=1e-9) and np.allclose(width(frames[2], r), width(frames[0], r), rtol=1e-9) and np.allclose(frames[1][r]["mean"], frames[0][r]["mean"]) for r in RESULTS)
    cl.record(ok, "The stated range is widened by the brief's factor exactly (factor 2 doubles it, the prediction is unchanged) and a factor below 1 is treated as 1: a range is never narrower than the model stated", "")


def leak_checks(cl: Checklist) -> None:
    lab, eng = world()
    obs = campaign(lab, eng, 5)
    refused = []
    for trial, extra in ((6, obs[:5] + [Observation(6, obs[0].recipe, obs[0].context, obs[0].results)]), (6, obs[:5] + [Observation(9, obs[0].recipe, obs[0].context, obs[0].results)]),
                         (1, [Observation(1, obs[0].recipe, obs[0].context, obs[0].results)]), (3, obs[:4])):
        try:
            world()[1].propose(trial, lab.context(trial), extra)
            refused.append(False)
        except FutureLeak:
            refused.append(True)
    cl.record(refused == [True] * 4, "LEAK refused: a measurement from the decision's own trial, from a later trial, or a call for a trial that already has a later measurement raises an error before anything is chosen", str(refused))
    lab_a, a = world()
    lab_b, b = world()
    campaign(lab_a, a, 14)
    campaign(lab_b, b, 14, corrupt=8)
    same_before = all(a.log[t].recipe == b.log[t].recipe for t in range(1, 9))
    cl.record(same_before, "LEAK, in the other direction: corrupting the measurement of trial 8 changes no decision up to and including trial 8", f"{sum(a.log[t].recipe != b.log[t].recipe for t in range(9, 15))} of the later 6 decisions differ")
    lab_c, c = world()
    campaign(lab_c, c, 10)
    cl.record(all(a.log[t].recipe == c.log[t].recipe and a.log[t].kind == c.log[t].kind for t in range(1, 11)), "Two engines given the same data make the same decisions (nothing depends on anything but the data and the seed)", "")
    d1 = c.propose(5, lab_c.context(5), [])
    cl.record(d1 is c.log[5], "Asking for the same trial twice returns the same decision", "")


def other_checks(cl: Checklist) -> None:
    lab, eng = world(n=20)
    d = eng.propose(1, lab.context(1), [])
    cl.record(d.kind == "starting" and not eng.models_fitted and "at least 30" in d.why and not d.chances, "With too few usable rows no model is fitted and the decision says so (a spread-out starting recipe)", d.why[:80])
    lab, eng = world("period_shift")
    campaign(lab, eng, 30)
    texts = [d.why for d in eng.log.values()]
    cl.record(all(t and not WORDS.search(re.sub(r"'[^']*'", "", t)) for t in texts), "Every explanation is in plain words (no technical wording, never empty)", f"{len(texts)} explanations")
    ok = all(lo < hi for d in eng.log.values() for lo, hi in d.stated_ranges.values()) and all(0.0 <= c <= 1.0 for d in eng.log.values() for c in d.chances.values())
    cl.record(ok, "Every stated range has its lower end below its upper end and every chance is between 0 and 1", "")
    found = forbidden_in([ROOT / "cellpoc" / "decision_engine" / "governed.py"])       # (the proof of concept engine files next to it use a permutation for their own spread-out design and are not this engine)
    cl.record(not found, "The governed engine contains no random splitter or sampler (it divides no rows at random)", "; ".join(found[:3]))


def main() -> int:
    cl = Checklist("PLATFORM STAGE 4-3: the governed decision engine (does it follow its five rules, on worlds where the right answer is known?)")
    before = project_files()
    rule1_checks(cl)
    rule2_checks(cl)
    rule3_checks(cl)
    isolated_status_checks(cl)
    drift_checks(cl)
    rule4_checks(cl)
    rule5_checks(cl)
    leak_checks(cl)
    other_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
