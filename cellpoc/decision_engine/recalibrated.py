"""The recalibrated response to a stale target (R): ADOPTED 2026-10-12 as the platform engine's rule 5 response, under the scope in ADOPTED_SCOPE below (docs/decisions.md, "Adoption of R"). Its naive variant (N) is a
diagnostic arm only and is never to be used as an engine. `RecalibratedStrategy(...)` (naive=False) IS the platform engine; this file is covered by the engine lock (comparison_check.py), like governed.py and baselines.py.

The governed engine (governed.py, not edited: its own rule 5 text describes the response this engine replaces) answers a stale target by dropping its chance and exploring. When the shift is a uniform offset that
discards a ranking that is still good. R keeps the ranking when the evidence says the model is only off by an offset, and falls back to that response when it is not. Everything here was fixed in the record before it
was built; the constants are not tuned.

At every decision, for each target the watch (unchanged: at most 7 hits of the last 12 stated ranges) has marked stale, look at the LAST 6 measurements of that target. Each has a signed residual (the measurement minus the
mean the CURRENT fitted model predicts for that recipe and context) and is a miss if it lies outside the range the model would state for it now.
  FINE    at most 2 of the 6 are misses: the model is working and the watch is only lagging. No correction; the target is treated as modelled.
  OFFSET  at least 3 misses and at least 5 of the 6 residuals have the same sign: the stated range and predicted mean are moved by the median residual (the width is unchanged), the chance is worked out from the
          moved values, and the engine keeps choosing by the chances.
  MIXED   at least 3 misses and fewer than 5 of the same sign: an offset cannot explain it, so the current response is kept for that target (no chance used, exploration).
PROMISE CHECK: if, with the corrections applied, the best vouched candidate's chance of meeting every modelled target together is below 0.5, the corrected model sees no good recipe, so for that decision every stale
target gets the current response instead.
NAIVE (N, a diagnostic arm, never a candidate): every stale target is always re-centred by the median of its last 6 signed residuals, with no classes and no promise check.
The classification needs 6 measurements of the target; the watch cannot fire before 12, so on the first decision at which it is stale they exist. The future is never used: only measurements before the decision.
"""
from __future__ import annotations

import dataclasses
from typing import Sequence

import numpy as np
import pandas as pd

from ..contracts import Observation
from .adaptive import _normal_cdf
from .governed import GovernedStrategy, Z90

# The scope of the adoption, word for word as approved by the project owner on 2026-10-12. It is the one statement to carry into any summary, report or scorecard that describes this engine's rule 5; a check
# (recalibrated_check.py) fails if it differs from the text recorded in docs/decisions.md.
ADOPTED_SCOPE = (
    "R is adopted for its demonstrated purpose: keeping stated ranges and chances honest while reacting to a detected shift, confirmed on an offset-style shift (period_shift) with a +11 to +13 "
    "recipe-per-campaign improvement over the prior response, no clearly demonstrated harm in the other three tested scenarios (though two of those three show intervals including zero, not a clean "
    "positive no-harm result), and no evidence either way on ranking-breaking (reshaping) shifts, since no scenario of that kind has been found that is both genuinely ranking-breaking and winnable. "
    "R is not shown to outperform simply ignoring a false alarm; it is shown to react honestly where the current response reacts dishonestly.")

# ---- constants fixed in writing before this was built (docs/decisions.md); not tuned
RECAL_WINDOW = 6            # the last 6 measurements of a stale target
FINE_MAX_MISSES = 2         # at most 2 misses of the 6: the model is working
SAME_SIGN_MIN = 5           # at least 5 of the 6 residuals the same sign: an offset
PROMISE = 0.5               # the corrected model must still see a vouched candidate with at least this chance of meeting every modelled target
FINE, OFFSET, MIXED = "fine", "offset", "mixed"


def classify(residuals: Sequence[float], misses: Sequence[bool]) -> tuple[str, float]:
    """The evidence class of a stale target from its last 6 signed residuals and which of them were misses, and the correction (the median residual for OFFSET, otherwise 0)."""
    res = np.asarray(residuals, float)
    if len(res) < RECAL_WINDOW:                                           # not enough evidence to claim an offset: keep the current response
        return MIXED, 0.0
    if int(np.sum(misses)) <= FINE_MAX_MISSES:
        return FINE, 0.0
    if max(int((res > 0).sum()), int((res < 0).sum())) >= SAME_SIGN_MIN:
        return OFFSET, float(np.median(res))
    return MIXED, 0.0


class RecalibratedStrategy(GovernedStrategy):
    name = "recalibrated"
    description = "The platform engine: the governed engine, but a stale target is re-centred on its recent signed errors when they show an offset, instead of dropped"

    def __init__(self, *args, naive: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.naive = naive
        self._offsets: dict = {}
        self._last_pred: dict = {}
        self._last_warned: dict = {}
        self.recal_log: dict[int, dict] = {}                              # per decision: the targets the watch marked stale, the class of each, the corrections, and what the promise check did

    # ------------------------------------------------------------------ the decision
    def propose(self, trial_number, context, measurements):
        self._offsets = {}
        return super().propose(trial_number, context, measurements)

    def _model_pick(self, trial_number, context, rows, done, stale):
        log = {"watch_stale": list(stale), "classes": {}, "offsets": {}, "gate": None, "best_chance": None}
        self.recal_log[trial_number] = log
        if not stale:
            return super()._model_pick(trial_number, context, rows, done, stale)
        classes = self._classes(done, tuple(stale))
        log["classes"] = {r: c for r, (c, _) in classes.items()}
        remaining = tuple(r for r, (c, _) in classes.items() if c == MIXED)         # only a MIXED target keeps the current response
        self._offsets = {r: d for r, (c, d) in classes.items() if c == OFFSET}
        log["offsets"] = dict(self._offsets)
        fallbacks = self.fallbacks
        decision = super()._model_pick(trial_number, context, rows, done, remaining)
        if self._offsets and not self.naive:                                         # the promise check
            best = self._best_vouched_chance(remaining)
            log["best_chance"] = best
            if best is not None and best < PROMISE:
                log["gate"] = "fallback"
                self._offsets, self.fallbacks = {}, fallbacks
                decision = super()._model_pick(trial_number, context, rows, done, tuple(stale))
        if log["offsets"] and log["gate"] is None:
            note = " Recalibrated: " + "; ".join(f"{self.targets[r].label} was stale, re-centred by {d:+.2f} (the median of its last {RECAL_WINDOW} signed errors)" for r, d in log["offsets"].items()) + "."
            decision = dataclasses.replace(decision, why=decision.why + note)
        return decision

    # ------------------------------------------------------------------ the evidence
    def _classes(self, done: Sequence[Observation], stale: tuple) -> dict:
        out = {}
        ordered = sorted(done, key=lambda o: o.trial_number)
        for r in stale:
            recent = [o for o in ordered if r in o.results][-RECAL_WINDOW:]
            if len(recent) < RECAL_WINDOW:
                out[r] = (MIXED, 0.0)
                continue
            frame = pd.DataFrame([{**o.recipe, **{k: str(v) for k, v in o.context.categories.items()}} for o in recent])
            frame[self.balance[0]] = 100.0 - sum(frame[i] for i in self.ingredients)
            pred = GovernedStrategy._predict(self, frame)[r]                                  # the model as it is now, uncorrected
            measured = np.array([o.results[r] for o in recent], float)
            residuals = measured - pred["mean"]
            misses = (measured < pred["lo"]) | (measured > pred["hi"])
            if self.naive:
                out[r] = (OFFSET, float(np.median(residuals)))
            else:
                out[r] = classify(residuals, misses)
        return out

    def _best_vouched_chance(self, remaining: tuple):
        """The best chance, among candidates no per-recipe check warns about, of meeting every modelled target together (the stale targets still given the current response left out)."""
        used = [t.result for t in self.trusted if t.result not in remaining]
        if not used or not self._last_pred or not self._last_warned:
            return None
        chance = np.ones(len(self._last_pred[used[0]]["chance"]))
        for r in used:
            chance = chance * self._last_pred[r]["chance"]
        free = ~(self._last_warned["distance"] | self._last_warned["range"] | self._last_warned["category"])
        return float(chance[free].max()) if free.any() else None

    # ------------------------------------------------------------------ the correction itself
    def _predict(self, frame: pd.DataFrame) -> dict:
        out = super()._predict(frame)
        for r, delta in self._offsets.items():
            p = out[r]
            mean, lo, hi = p["mean"] + delta, p["lo"] + delta, p["hi"] + delta
            sd = np.maximum((hi - lo) / (2 * Z90), 1e-9)
            spec = self.targets[r]
            upper = _normal_cdf((spec.high - mean) / sd) if spec.high is not None else np.ones(len(sd))
            lower = _normal_cdf((spec.low - mean) / sd) if spec.low is not None else np.zeros(len(sd))
            out[r] = {"mean": mean, "lo": lo, "hi": hi, "chance": upper - lower}
        self._last_pred = out
        return out

    def _warnings(self, frame: pd.DataFrame) -> dict:
        out = super()._warnings(frame)
        self._last_warned = out
        return out
