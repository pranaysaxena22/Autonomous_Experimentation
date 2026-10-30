"""The development comparison (Stage 4-4): the governed engine against the ungoverned one and against random recipes, on the development lab's four scenarios, 40 paired campaigns each.

The design, the measures and the verdict rule were fixed in docs/decisions.md ("Stage 4-4") BEFORE any campaign ran. Campaign i uses seed 10200 + i for the lab's noise and batches and for every strategy's own random
choices, so the three strategies face the identical lab day. Everything is scored after the fact against the lab's truth (cellpoc/scoring.py). The engine is not changed while this runs.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..contracts import EngineBrief, Observation
from ..contracts.seeds import refuse_sealed_seed
from ..decision_engine.baselines import RandomRecipes, UngovernedStrategy
from ..decision_engine.governed import GovernedStrategy
from ..decision_engine.recalibrated import RecalibratedStrategy
from ..scoring import score_dev_trial
from ..virtual_lab.dev_lab import (DESIGN_SPACE, FILLER_RANGE, HISTORY_EXPERIMENTS, HISTORY_SEEDS, INGREDIENTS, NEW_SUPPLIER_FROM, PERIOD_STEP_FROM, SCENARIOS, DevLab, cleaned_history, target_specs)

TRIALS = 30
COMPARISON_SEEDS = tuple(range(10200, 10240))            # 40 paired campaigns, a block never used in development
STRATEGIES = ("governed", "ungoverned", "random")
SCENARIO_NAMES = tuple(SCENARIOS)
EVENT_TRIAL = {"new_supplier": NEW_SUPPLIER_FROM, "period_shift": PERIOD_STEP_FROM}       # the trial from which a scenario's event applies
BOOTSTRAP_DRAWS, BOOTSTRAP_SEED = 2000, 20261014
BINS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))
BETTER, WORSE, NO_CLEAR = "better", "worse", "no clear difference"


@dataclass
class CampaignRecord:
    scenario: str
    strategy: str
    seed: int
    good: list                       # per trial: truly good
    met: list                        # per trial: {target: truly met}
    measured_pass: list              # per trial: the measurement met every target
    kinds: list                      # per trial: what kind of pick
    chances: list                    # per trial: the chances the strategy stated ({} when none)
    stale: list                      # per trial: targets stale at that decision
    warned: list                     # per trial: whether the pick was warned by any per-recipe check
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(text: str) -> "CampaignRecord":
        return CampaignRecord(**json.loads(text))


def build_strategy(name: str, scenario: str, brief: EngineBrief, seed: int, settings=None):
    refuse_sealed_seed(seed, "the development comparison's strategy builder")
    lab = DevLab(SCENARIOS[scenario], HISTORY_SEEDS[scenario])
    history = cleaned_history(lab, HISTORY_EXPERIMENTS)
    args = (target_specs(), history, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)
    extra = {} if settings is None else {"settings": settings}            # None: the engine's own default (the full model settings Stage 3 used)
    if name == "governed":                                                # the 4-4 engine, as it was before rule 5's response was replaced (kept as the reference the 4-4 results were recorded with)
        return GovernedStrategy(brief, *args, **extra)
    if name == "recalibrated":                                            # the platform engine (R adopted 2026-10-12); not in STRATEGIES, so the four-scenario 4-4 comparison is unchanged
        return RecalibratedStrategy(brief, *args, **extra)
    if name == "ungoverned":
        return UngovernedStrategy(brief, *args, **extra)
    if name == "random":
        return RandomRecipes(DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)
    raise ValueError(f"unknown strategy '{name}'")


def run_campaign(scenario: str, strategy_name: str, seed: int, brief: EngineBrief, settings=None, trials: int = TRIALS) -> CampaignRecord:
    """One campaign: `trials` decisions, each measured in the lab and scored against the truth afterwards."""
    refuse_sealed_seed(seed, "the development comparison's campaign")
    started = time.time()
    lab = DevLab(SCENARIOS[scenario], seed)
    strategy = build_strategy(strategy_name, scenario, brief, seed, settings)
    specs = target_specs()
    obs, rec = [], CampaignRecord(scenario, strategy_name, seed, [], [], [], [], [], [], [])
    watch, recal = [], []                                                  # the adopted engine lists as stale only the targets that still get the old response, so its own watch flag and evidence classes are kept too
    for t in range(1, trials + 1):
        ctx = lab.context(t)
        d = strategy.propose(t, ctx, obs)
        log = getattr(strategy, "recal_log", {}).get(t)
        if log is not None:
            watch.append(list(log["watch_stale"]))
            recal.append({"classes": dict(log["classes"]), "gate": log["gate"], "offsets": {k: float(v) for k, v in log["offsets"].items()}})
        m = lab.measure(t, d.recipe, ctx)
        obs.append(Observation(t, d.recipe, ctx, m))
        s = score_dev_trial(lab, specs, t, d.recipe, ctx, m)
        rec.good.append(s.good)
        rec.met.append(s.met)
        rec.measured_pass.append(s.measured_pass)
        rec.kinds.append(d.kind)
        rec.chances.append(dict(d.chances))
        rec.stale.append(list(d.stale))
        rec.warned.append(any(d.warnings.values()))
    rec.seconds = time.time() - started
    rec.extra = {"fallbacks": getattr(strategy, "fallbacks", 0), "fits": len(getattr(strategy, "models_fitted", []))}
    if watch:
        rec.extra["watch_stale"], rec.extra["recal"] = watch, recal
    return rec


def _task(scenario: str, strategy: str, seed: int, brief_text: str, cache: str | None, threads: int = 1) -> CampaignRecord:
    """One campaign as a plain function (so it can run in another process); saved as it finishes so an interrupted run carries on."""
    from threadpoolctl import threadpool_limits

    path = Path(cache) / scenario / f"{strategy}_{seed}.json" if cache else None
    if path is not None and path.exists():
        return CampaignRecord.from_json(path.read_text(encoding="utf-8"))
    with threadpool_limits(limits=threads):
        rec = run_campaign(scenario, strategy, seed, EngineBrief.from_json(brief_text))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rec.to_json(), encoding="utf-8")
    return rec


def run_all(briefs: dict, cache: str | None, jobs: int = 1, seeds=COMPARISON_SEEDS, scenarios=SCENARIO_NAMES, strategies=STRATEGIES, progress=None) -> list:
    """Every campaign, in parallel, resumable. `briefs` maps a scenario to the text of its brief."""
    from joblib import Parallel, delayed

    for seed in seeds:
        refuse_sealed_seed(seed, "the development comparison's runner")                         # refuse before anything is started
    tasks = [(s, st, seed) for s in scenarios for st in strategies for seed in seeds]
    done = []
    for start in range(0, len(tasks), max(1, jobs * 4)):
        chunk = tasks[start:start + max(1, jobs * 4)]
        done += Parallel(n_jobs=jobs)(delayed(_task)(s, st, seed, briefs[s], cache) for s, st, seed in chunk)
        if progress:
            progress(len(done), len(tasks))
    return done


# ---------------------------------------------------------------- the statistics (fixed in advance)
def paired_difference(a: list, b: list, draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED) -> dict:
    """Campaign-by-campaign difference a - b: the mean, a 95% interval from resampling the campaigns, and wins, ties and losses."""
    d = np.asarray(a, float) - np.asarray(b, float)
    g = np.random.default_rng(seed)
    means = g.choice(d, size=(draws, len(d)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {"mean": float(d.mean()), "lo": float(lo), "hi": float(hi), "wins": int((d > 0).sum()), "ties": int((d == 0).sum()), "losses": int((d < 0).sum())}


def verdict(lo: float, hi: float) -> str:
    """'better' only if the interval's lower end is above 0, 'worse' only if its upper end is below 0, otherwise 'no clear difference'."""
    return BETTER if lo > 0 else WORSE if hi < 0 else NO_CLEAR


def reliability(stated: list, outcomes: list) -> dict:
    """How honest stated chances are: in five bins of stated chance, how often the target really was met, and the Brier score (0 is perfect, lower is better)."""
    s, o = np.asarray(stated, float), np.asarray(outcomes, float)
    bins = []
    for i, (lo, hi) in enumerate(BINS):
        pick = (s >= lo) & ((s < hi) if i < len(BINS) - 1 else (s <= hi))
        bins.append({"bin": f"{lo:.0%} to {hi:.0%}", "n": int(pick.sum()), "stated": float(s[pick].mean()) if pick.any() else None, "met": float(o[pick].mean()) if pick.any() else None})
    return {"bins": bins, "brier": float(((s - o) ** 2).mean()) if len(s) else None, "n": int(len(s))}
