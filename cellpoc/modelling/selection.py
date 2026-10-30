"""Which model would be chosen for a result, by the rule approved in the plan (fixed in advance, never changed after seeing a score).

- A model's score is its WORST hold-out type: for each hold-out type that can be run, its error divided by the result's spread; the largest of those is its score.
- A model is only eligible if it beats BOTH naive baselines (the training mean and the nearest-neighbour lookup) in every hold-out type that can be run.
- Among eligible models, the best (lowest) score wins, but ties within 5% go to the simpler or faster model.
- If no model is eligible the answer is "no model beats the baseline" and none is offered. The report shows everything either way.
Only the main comparison is judged this way: an exploratory comparison, or a table that cannot support an accuracy claim, is never given a chosen model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .validate import Validation, score, spread

TIE = 0.05
CANDIDATES = ("linear", "quadratic", "boosting", "forest", "ensemble", "gp", "gp_joint")
SIMPLICITY = {"linear": 1, "quadratic": 2, "boosting": 3, "forest": 4, "ensemble": 5, "gp": 6, "gp_joint": 7}      # lower is simpler and faster
LEAKAGE_R2 = 0.99                                                                                     # a held-out R-squared this high is a warning sign, not a success


@dataclass
class Selection:
    result: str
    kinds: list[str]                                                  # the hold-out types that could be run for this result
    worst: dict[str, float] = field(default_factory=dict)             # model -> its worst error divided by spread
    eligible: list[str] = field(default_factory=list)
    tie: list[str] = field(default_factory=list)                      # the eligible models within 5% of the best score: interchangeable choices
    chosen: str | None = None
    why: str = ""


def select(validation: Validation, result: str) -> Selection:
    kinds = [k for (r, k), run in validation.runs.items() if r == result and run.plan.available]
    sel = Selection(result, kinds)
    if not kinds:
        sel.why = "no hold-out type could be run for this result, so no model can be judged."
        return sel
    sd = spread(validation.table, result)
    by_kind = {k: score(validation.runs[(result, k)]) for k in kinds}
    for key in CANDIDATES:
        if not all(key in by_kind[k] and by_kind[k][key].folds == by_kind[k][key].of_folds for k in kinds):
            continue
        sel.worst[key] = max(by_kind[k][key].rmse / sd for k in kinds)
        if all(by_kind[k][key].rmse < min(by_kind[k][b].rmse for b in ("mean", "nearest") if b in by_kind[k]) for k in kinds):
            sel.eligible.append(key)
    if not sel.eligible:
        sel.why = "no model beats the baseline."
        return sel
    best_key = min(sel.eligible, key=lambda k: sel.worst[k])
    close = [k for k in sel.eligible if sel.worst[k] <= sel.worst[best_key] * (1 + TIE)]
    sel.tie = sorted(close, key=lambda k: (SIMPLICITY[k], sel.worst[k]))
    sel.chosen = sel.tie[0]
    sel.why = (f"the best score is {sel.worst[best_key]:.3f} (error divided by spread, worst hold-out type)" +
               (f"; {len(close)} models are within 5% of it, so the simplest or fastest of them is chosen." if len(close) > 1 else "; no other model is within 5% of it."))
    return sel
