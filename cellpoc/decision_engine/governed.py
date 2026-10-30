"""The governed decision engine (Stage 4-3): it chooses the next recipe, and it behaves honestly about what Stage 3 could and could not vouch for.

It does not predict better than Stage 3. It uses what Stage 3 produced under five rules, with every constant fixed in docs/decisions.md ("Stage 4") before this was written:
 1. ONLY A CARRIED RESULT IS MODELLED. For each target the brief says carried, exploratory or not assessed. Only a carried target gets a model (the one model the Stage 3 rule chose, with its fixed
    settings, on exactly the inputs Stage 3 used) and a stated chance. A target that is not carried is measured every trial and gets no model and no probability. The engine never states a combined
    chance of passing every target while any target is unmodelled.
 2. UNMODELLED TARGETS: candidates are the top TOP_SHARE by chance of meeting the modelled targets among candidates that are not warned. With no measured recipe that meets every target yet, the engine picks the
    one farthest from everything measured; once there is one it alternates that with a local search around the best measured passes (the proof of concept engine's own spread, centres and distances).
 3. UNVOUCHED RECIPES: a candidate warned by the distance, numeric-range or unseen-category check (each on its own, never combined) is never an ordinary pick. It can only be an explicit exploratory pick,
    at most one trial in any EXPLORATORY_EVERY consecutive trials (so at most 6 in 30), labelled as such; its chance is stated as not vouched for.
 4. A NEW CONTEXT VALUE (a supplier, filler grade or tester never seen in the training rows): the model cannot vouch for anything there, so the engine first runs BRIDGING_TRIALS bridging trials, re-measuring the
    best measured passing recipes in the new context, then refits on the new data. (The unseen-category status is the one warning that works reliably under a supplier shift, 3b-2.)
 5. THE STALENESS WATCH: for each modelled target the engine checks every measurement against the 90% range it stated for that recipe before it saw the measurement (the model's range widened by the brief's range
    factor, never narrower). If STALE_MAX_HITS or fewer of the last STALE_WINDOW fall inside, that target is stale: its chance is not used and every pick is exploratory until it holds again. It is built to catch
    a collapse, not a slow or moderate decline (docs/decisions.md).
It sees only measurements, the context a trial ran in and the specifications. It never sees a lab's truth (the guard stops it importing one) and refuses any call whose data would come from the decision's own
trial or later (FutureLeak). It imports only cellpoc.modelling.models and cellpoc.modelling.domain from the modelling part (approved, one direction).
"""
from __future__ import annotations

import math
import zlib
from typing import Sequence

import numpy as np
import pandas as pd

from ..contracts import Decision, EngineBrief, Observation, TargetBrief, TargetSpec, TrialContext
from ..contracts.seeds import refuse_sealed_seed
from ..modelling.domain import fit_reference, warn
from ..modelling.models import FULL, Encoder, Settings, single_models
from .adaptive import _normal_cdf

# ---- constants fixed in writing before this was built (docs/decisions.md, "Stage 4 policy constants")
STALE_WINDOW = 12                 # the staleness watch looks at the last 12 trials in which a target was measured
STALE_MAX_HITS = 7                # and calls the target stale when at most 7 of them fell inside the stated 90% range
EXPLORATORY_EVERY = 5             # at most one exploratory pick in 5 trials
BRIDGING_TRIALS = 3               # bridging trials in a context value never seen before
TOP_SHARE = 0.20                  # the untrusted-target policy chooses among the top 20% of unwarned candidates by chance
MIN_ROWS = 30                     # the modelling part's own minimum: fewer usable rows and no model is fitted
LOCAL_SPREAD, LOCAL_CENTRES, LOCAL_PER_CENTRE, TOO_CLOSE = 0.07, 3, 400, 0.02     # the proof of concept engine's own values
# ---- constants added while building, for cost, and provisional like the others (recorded in docs/decisions.md)
REFIT_EVERY = 5                   # models are refitted every 5 trials, and at once when a new context value has been bridged
CANDIDATES = 2000                 # random candidate recipes per decision (the local ones come on top)
Z90 = 1.6448536269514722


class FutureLeak(Exception):
    """A call that would let a decision use data from its own trial or later."""


def _stream(*key) -> np.random.Generator:
    return np.random.default_rng([zlib.crc32(str(k).encode()) for k in key])


def inner_folds(groups: np.ndarray, k: int = 5) -> list | None:
    """Folds of whole groups INSIDE the training rows, as (fit rows, check rows): the way the Stage 3 harness chooses a ridge penalty (biggest groups first into the fullest-last fold; ties by name)."""
    sizes = pd.Series(groups).value_counts().to_dict()
    if len(sizes) < 2:
        return None
    k = min(k, len(sizes))
    load, placed = [0] * k, {}
    for g in sorted(sizes, key=lambda g: (-sizes[g], g)):
        i = min(range(k), key=lambda i: (load[i], i))
        placed[g] = i
        load[i] += sizes[g]
    fold_of = np.array([placed[g] for g in groups])
    folds = [(np.flatnonzero(fold_of != f), np.flatnonzero(fold_of == f)) for f in sorted(set(placed.values()))]
    return [(fit, check) for fit, check in folds if len(check) >= 5 and len(fit) >= 10] or None


def calibration_mask(groups: np.ndarray) -> np.ndarray | None:
    """One group in four (the first of each four, by name) kept apart to calibrate a conformal range, as Stage 3 does."""
    names = sorted(set(groups))
    if len(names) < 2:
        return None
    mask = np.isin(groups, names[::4])
    return mask if 0 < mask.sum() < len(mask) else None


class GovernedStrategy:
    name = "governed"
    description = "Uses only what Stage 3 carried, says what it cannot vouch for, and checks its own stated ranges"

    def __init__(self, brief: EngineBrief, targets: dict, history: pd.DataFrame, space: dict, ingredients: Sequence[str], balance: tuple, seed: int,
                 settings: Settings = FULL, group_column: str = "batch_id"):
        """`targets` maps each result to its TargetSpec; `space` maps each controllable numeric input to its (low, high); `ingredients` names the percentages (the balance ingredient is 100 minus them);
        `balance` is (its column name, (its lowest, its highest)); `history` holds past experiments with the inputs, the results and the group column."""
        refuse_sealed_seed(seed, "the decision engine", allow_acceptance=True)        # a sealed seed gets through only as the official runner's wrapper (seeds.py); the guard added after 4-4
        self.brief, self.targets, self.space = brief, dict(targets), dict(space)
        self.ingredients, self.balance, self.seed, self.settings, self.group_column = tuple(ingredients), balance, seed, settings, group_column
        self.keys = list(space)
        self._low = np.array([space[k][0] for k in self.keys], float)
        self._span = np.array([space[k][1] - space[k][0] for k in self.keys], float)
        self.trusted: list[TargetBrief] = [t for t in brief.targets if t.usable_for_decisions and t.result in self.targets]
        self.reasons = {t.result: (t.reason or f"Stage 3 did not carry it ({t.status})") for t in brief.targets if not t.usable_for_decisions}
        names = {c for t in self.trusted for c in t.categorical_inputs}
        self.context_names = sorted(names)
        self.history = history.reset_index(drop=True)
        self._scale = {r: float(self.history[r].std()) or 1.0 for r in self.targets if r in self.history}
        self._known = {c: set(self.history[c].astype(str)) for c in self.context_names if c in self.history}
        self.log: dict[int, Decision] = {}
        self.fits: dict = {}                 # result -> (encoder, model, rows used)
        self.references: dict = {}
        self._fit_trial, self._fit_known = None, None
        self.models_fitted: list[tuple[str, str]] = []        # every (result, model key) ever fitted, for inspection
        self.fallbacks = 0                                     # decisions where every candidate was unvouched, so the exploratory cap could not be kept
        self.trace: dict[int, dict] = {}                       # per decision: how many candidates there were, how many were unvouched, whether the best-looking one was, and the pool's lowest chance

    # ------------------------------------------------------------------ public
    def propose(self, trial_number: int, context: TrialContext, measurements: Sequence[Observation]) -> Decision:
        """The recipe for campaign trial `trial_number`, given every measurement of the trials before it. Idempotent: the same trial asked twice returns the same decision."""
        for o in measurements:
            if o.trial_number >= trial_number:
                raise FutureLeak(f"trial {o.trial_number} is not before trial {trial_number}: a decision may only use trials that came before it")
        if trial_number in self.log:
            return self.log[trial_number]
        done = sorted(measurements, key=lambda o: o.trial_number)
        rows = self._rows(done)
        stale = self._stale(done)
        pending = self._pending_context(context, done)
        if pending:
            decision = self._bridge(trial_number, context, rows, done, pending, stale)
        elif not self.trusted:
            decision = self._pick_without_models(trial_number, context, rows, done, stale)
        elif any(rows[t.result].notna().sum() < MIN_ROWS for t in self.trusted):
            decision = self._starting(trial_number, context, rows, done)
        else:
            self._ensure_fits(trial_number, rows, done)
            decision = self._model_pick(trial_number, context, rows, done, stale)
        self.log[trial_number] = decision
        return decision

    # ------------------------------------------------------------------ the data the decision may use: the history and the measurements before it
    def _rows(self, done: Sequence[Observation]) -> pd.DataFrame:
        if not done:
            return self.history
        extra = []
        for o in done:
            row = {**o.recipe, **{k: str(v) for k, v in o.context.categories.items()}, **o.results, self.group_column: o.context.batch_id}
            row[self.balance[0]] = 100.0 - sum(o.recipe[i] for i in self.ingredients)
            extra.append(row)
        return pd.concat([self.history, pd.DataFrame(extra)], ignore_index=True)

    # ------------------------------------------------------------------ rule 5: the staleness watch
    def hit_sequences(self, done: Sequence[Observation]) -> dict:
        """For each modelled target, in trial order, whether each measurement fell inside the range stated for it before it was seen."""
        seqs = {t.result: [] for t in self.trusted}
        for o in done:
            d = self.log.get(o.trial_number)
            if d is None:
                continue
            for r, (lo, hi) in d.stated_ranges.items():
                if r in seqs and r in o.results:
                    seqs[r].append(lo <= o.results[r] <= hi)
        return seqs

    def _stale(self, done: Sequence[Observation]) -> tuple:
        return tuple(r for r, s in self.hit_sequences(done).items() if len(s) >= STALE_WINDOW and sum(s[-STALE_WINDOW:]) <= STALE_MAX_HITS)

    # ------------------------------------------------------------------ rule 4: a context value never seen before
    def _pending_context(self, context: TrialContext, done: Sequence[Observation]) -> tuple:
        """The (name, value) pairs in this context that are new and whose bridging is not finished."""
        out = []
        for name in self.context_names:
            value = str(context.categories.get(name))
            if name not in self._known or value in self._known[name]:
                continue
            bridged = sum(1 for d in self.log.values() if d.kind == "bridging" and (name, value) in d.new_context and any(o.trial_number == d.trial_number for o in done))
            if bridged < BRIDGING_TRIALS:
                out.append((name, value, bridged))
        return tuple(out)

    def _complete_bridging(self, done: Sequence[Observation]) -> None:
        for d in self.log.values():
            for name, value in d.new_context:
                if sum(1 for e in self.log.values() if e.kind == "bridging" and (name, value) in e.new_context and any(o.trial_number == e.trial_number for o in done)) >= BRIDGING_TRIALS:
                    self._known.setdefault(name, set()).add(value)

    # ------------------------------------------------------------------ recipes and candidates
    def _unit(self, frame: pd.DataFrame) -> np.ndarray:
        return (frame[self.keys].to_numpy(float) - self._low) / self._span

    def _recipe(self, unit_row: np.ndarray) -> dict:
        values = self._low + np.clip(unit_row, 0, 1) * self._span
        return {k: float(v) for k, v in zip(self.keys, values)}

    def _filler_ok(self, values: np.ndarray) -> np.ndarray:
        percent = sum(values[:, self.keys.index(i)] for i in self.ingredients)
        filler = 100.0 - percent
        return (filler >= self.balance[1][0]) & (filler <= self.balance[1][1])

    def _margin(self, frame: pd.DataFrame) -> np.ndarray:
        """How comfortably each measured row meets every target (positive: all met): the worst of the targets' slacks, each in units of that result's own spread."""
        slack = []
        for r, t in self.targets.items():
            v = frame[r].to_numpy(float)
            s = self._scale.get(r, 1.0)
            parts = []
            if t.low is not None:
                parts.append((v - t.low) / s)
            if t.high is not None:
                parts.append((t.high - v) / s)
            slack.append(np.minimum.reduce(parts))
        return np.minimum.reduce(slack)

    def _best_measured(self, rows: pd.DataFrame, n: int) -> pd.DataFrame:
        complete = rows.dropna(subset=list(self.targets) + self.keys)
        if complete.empty:
            return complete
        ranked = complete.iloc[np.argsort(-self._margin(complete), kind="stable")]
        return ranked.drop_duplicates(subset=self.keys).iloc[:n]                      # distinct recipes: replicates of one recipe must not fill every slot

    def _has_measured_pass(self, rows: pd.DataFrame) -> bool:
        complete = rows.dropna(subset=list(self.targets))
        return bool(len(complete) and (self._margin(complete) > 0).any())

    def _candidates(self, trial_number: int, rows: pd.DataFrame, done: Sequence[Observation], context: TrialContext) -> tuple:
        g = _stream(self.seed, "candidates", trial_number)
        pool = [g.random((CANDIDATES, len(self.keys)))]
        flags = [np.zeros(CANDIDATES, bool)]
        for _, c in self._best_measured(rows, LOCAL_CENTRES).iterrows():
            centre = (c[self.keys].to_numpy(float) - self._low) / self._span
            pool.append(np.clip(centre + g.normal(0, LOCAL_SPREAD, (LOCAL_PER_CENTRE, len(self.keys))), 0, 1))
            flags.append(np.ones(LOCAL_PER_CENTRE, bool))
        unit, is_local = np.vstack(pool), np.concatenate(flags)
        values = self._low + unit * self._span
        keep = self._filler_ok(values)
        if done:
            tried = np.array([[(o.recipe[k] - self._low[i]) / self._span[i] for i, k in enumerate(self.keys)] for o in done])
            far = ((unit[:, None, :] - tried[None, :, :]) ** 2).sum(axis=2).min(axis=1) > TOO_CLOSE ** 2
            keep &= far
        unit, is_local, values = unit[keep], is_local[keep], values[keep]
        frame = pd.DataFrame(values, columns=self.keys)
        frame[self.balance[0]] = 100.0 - sum(frame[i] for i in self.ingredients)
        for name, value in context.categories.items():
            frame[name] = str(value)
        return unit, is_local, frame

    def _farthest(self, unit: np.ndarray, among: np.ndarray, rows: pd.DataFrame) -> int:
        """The candidate (among the given positions) whose nearest measured recipe is farthest away."""
        measured = self._unit(rows.dropna(subset=self.keys))
        best, best_gap = int(among[0]), -1.0
        for start in range(0, len(among), 500):
            chunk = among[start:start + 500]
            gap = ((unit[chunk][:, None, :] - measured[None, :, :]) ** 2).sum(axis=2).min(axis=1)
            i = int(np.argmax(gap))
            if gap[i] > best_gap:
                best, best_gap = int(chunk[i]), float(gap[i])
        return best

    # ------------------------------------------------------------------ models and warnings (rule 1: only the carried result's chosen model)
    def _ensure_fits(self, trial_number: int, rows: pd.DataFrame, done: Sequence[Observation]) -> None:
        self._complete_bridging(done)
        known = frozenset((n, v) for n, vs in self._known.items() for v in vs)
        if self.fits and self._fit_trial is not None and trial_number - self._fit_trial < REFIT_EVERY and known == self._fit_known:
            return
        self.fits, self.references = {}, {}
        for t in self.trusted:
            cols = list(t.numeric_inputs) + list(t.categorical_inputs)
            use = rows.dropna(subset=cols + [t.result]).reset_index(drop=True)
            groups = use[self.group_column].astype(str).to_numpy()
            encoder = Encoder(list(t.numeric_inputs), list(t.categorical_inputs)).fit(use)
            X = encoder.transform(use)
            model = next(m for m in single_models(self.settings, encoder.n_numeric, X.shape[1]) if m.key == t.model_key)
            model.fit(X, use[t.result].to_numpy(float), calibration_mask(groups), inner_folds(groups))
            self.fits[t.result] = (encoder, model, len(use))
            self.models_fitted.append((t.result, t.model_key))
            key = (tuple(t.numeric_inputs), tuple(t.categorical_inputs))
            if key not in self.references:
                self.references[key] = fit_reference(use, list(t.numeric_inputs), list(t.categorical_inputs), np.arange(len(use)), groups)
        self._fit_trial, self._fit_known = trial_number, known

    def _predict(self, frame: pd.DataFrame) -> dict:
        """For each modelled target: the predicted value and the stated 90% range, widened by the brief's factor and never narrower than the model stated, and the chance of meeting the target."""
        out = {}
        for t in self.trusted:
            encoder, model, _ = self.fits[t.result]
            p = model.predict(encoder.transform(frame))
            if not (np.isfinite(p.lo).all() and np.isfinite(p.hi).all()):
                raise ValueError(f"the model for {t.result} states no range, so a chance cannot be worked out")
            f = max(1.0, t.range_factor or 1.0)
            lo, hi = p.mean - (p.mean - p.lo) * f, p.mean + (p.hi - p.mean) * f
            sd = np.maximum((hi - lo) / (2 * Z90), 1e-9)
            spec = self.targets[t.result]
            upper = _normal_cdf((spec.high - p.mean) / sd) if spec.high is not None else np.ones(len(sd))
            lower = _normal_cdf((spec.low - p.mean) / sd) if spec.low is not None else np.zeros(len(sd))
            out[t.result] = {"mean": p.mean, "lo": lo, "hi": hi, "chance": upper - lower}
        return out

    def _warnings(self, frame: pd.DataFrame) -> dict:
        """The three per-recipe statuses, each on its own, for every candidate (the same recipe is warned by a check if ANY modelled target's reference says so)."""
        n = len(frame)
        out = {"distance": np.zeros(n, bool), "range": np.zeros(n, bool), "category": np.zeros(n, bool)}
        for key, ref in self.references.items():
            w = warn(ref, frame, np.arange(n))
            out["distance"] |= w.by_distance
            out["range"] |= w.by_range
            out["category"] |= w.by_category
        return out

    # ------------------------------------------------------------------ the decisions
    def _unmodelled(self, used: set) -> tuple:
        return tuple(r for r in self.targets if r not in used)

    def _reasons_text(self, unmodelled: tuple, stale: tuple) -> str:
        parts = []
        for r in unmodelled:
            label = self.targets[r].label
            if r in stale:
                parts.append(f"{label} (its stated range stopped holding: {STALE_MAX_HITS} or fewer of the last {STALE_WINDOW} measurements fell inside it)")
            else:
                parts.append(f"{label} ({self.reasons.get(r, 'not carried by Stage 3')})")
        return ("Not modelled: " + "; ".join(parts) + ". A combined chance of passing every target is therefore not stated.") if parts else ""

    def _starting(self, trial_number: int, context: TrialContext, rows: pd.DataFrame, done: Sequence[Observation]) -> Decision:
        unit, _, frame = self._candidates(trial_number, rows, done, context)
        pick = self._farthest(unit, np.arange(len(unit)), rows)
        usable = {t.result: int(rows[t.result].notna().sum()) for t in self.trusted}
        return Decision(trial_number, self._recipe(unit[pick]), "starting",
                        f"Too few usable results to fit a model ({usable}; at least {MIN_ROWS} are needed), so this recipe is placed as far as possible from everything measured.",
                        unmodelled=tuple(self.targets))

    def _bridge(self, trial_number: int, context: TrialContext, rows: pd.DataFrame, done: Sequence[Observation], pending: tuple, stale: tuple) -> Decision:
        name, value, k = pending[0]
        anchors = self._best_measured(rows, BRIDGING_TRIALS)
        passing = anchors[self._margin(anchors) > 0] if len(anchors) else anchors
        if k < len(passing):
            recipe = {key: float(passing.iloc[k][key]) for key in self.keys}
            what = f"the measured recipe that passed with the most room (number {k + 1} of the best {len(passing)})"
        else:
            unit, _, _ = self._candidates(trial_number, rows, done, context)
            recipe = self._recipe(unit[self._farthest(unit, np.arange(len(unit)), rows)])
            what = "a recipe placed far from everything measured (fewer measured passes than bridging trials)"
        text = (f"{name} = {value} has never been seen in the training data, so no model can vouch for anything in this context. Bridging trial {k + 1} of {BRIDGING_TRIALS}: re-measuring {what} "
                f"to learn how this context behaves; the models are refitted on the new data afterwards. {self._reasons_text(tuple(self.targets), stale)}")
        return Decision(trial_number, recipe, "bridging", text, unmodelled=tuple(self.targets), stale=stale, stated_ranges=self._stated_for(recipe, context), new_context=((name, value),))

    def _stated_for(self, recipe: dict, context: TrialContext) -> dict:
        """The 90% range the models already fitted would state for this recipe in this context (a category they never saw counts as unknown to them), so that the staleness watch also counts bridging trials.
        Empty before any model has been fitted."""
        if not self.fits:
            return {}
        frame = pd.DataFrame([{**recipe, **{k: str(v) for k, v in context.categories.items()}}])
        pred = self._predict(frame)
        return {r: (float(p["lo"][0]), float(p["hi"][0])) for r, p in pred.items()}

    def _pick_without_models(self, trial_number: int, context: TrialContext, rows: pd.DataFrame, done: Sequence[Observation], stale: tuple) -> Decision:
        unit, is_local, frame = self._candidates(trial_number, rows, done, context)
        pick, kind = self._untrusted_pick(trial_number, unit, is_local, np.arange(len(unit)), rows)
        return Decision(trial_number, self._recipe(unit[pick]), kind, f"No target is carried by Stage 3, so there is no model: the recipe is chosen by measurement alone ({kind.replace('_', ' ')}). "
                        f"{self._reasons_text(tuple(self.targets), stale)}", unmodelled=tuple(self.targets), stale=stale)

    def _untrusted_pick(self, trial_number: int, unit: np.ndarray, is_local: np.ndarray, pool: np.ndarray, rows: pd.DataFrame) -> tuple:
        """Rule 2: with no measured pass yet, the farthest from everything measured; once there is one, alternate that with a local search around the best measured passes.
        `pool` is already ordered from the most to the least likely to pass, so the first local candidate in it is the most likely one."""
        if self._has_measured_pass(rows) and trial_number % 2 == 0:
            local = pool[is_local[pool]]
            if len(local):
                return int(local[0]), "local_search"
        return self._farthest(unit, pool, rows), "space_filling"

    def _model_pick(self, trial_number: int, context: TrialContext, rows: pd.DataFrame, done: Sequence[Observation], stale: tuple) -> Decision:
        unit, is_local, frame = self._candidates(trial_number, rows, done, context)
        pred = self._predict(frame)
        warned = self._warnings(frame)
        unvouched = warned["distance"] | warned["range"] | warned["category"]
        used = [t.result for t in self.trusted if t.result not in stale]
        chance = np.ones(len(frame))
        for r in used:
            chance = chance * pred[r]["chance"]
        everything = np.arange(len(unit))
        free = np.flatnonzero(~unvouched)
        unmodelled = self._unmodelled(set(used))
        so_far = sum(1 for d in self.log.values() if d.kind == "exploratory")
        recent = any(self.log[t].kind == "exploratory" for t in range(trial_number - EXPLORATORY_EVERY + 1, trial_number) if t in self.log)
        may_explore = trial_number >= EXPLORATORY_EVERY and not recent                # at most one exploratory pick in any five consecutive trials (so at most 6 in 30)
        kind, note, pool_floor = "exploit", "", None
        if not used:                                                                  # every modelled target is stale: nothing can be vouched for, so spread out
            pick, kind = self._farthest(unit, everything, rows), "stale_exploration"
        elif stale:                                                                   # some modelled target is stale: it is treated like an unmodelled one (rule 2), ranked by the targets that still hold,
            order = everything[np.argsort(-chance, kind="stable")]                    # and the one-in-five cap is lifted, so a warned recipe may be chosen: every pick is exploration for the stale target
            pool = order[:max(1, math.ceil(TOP_SHARE * len(order)))]
            pick, pool_floor = self._untrusted_pick(trial_number, unit, is_local, pool, rows)[0], float(chance[pool].min())
            kind = "stale_exploration"
        elif len(free) == 0:                                                          # every candidate is unvouched: the cap cannot be kept, and the decision says so
            pick, kind, note = self._farthest(unit, everything, rows), "exploratory", " Every candidate was unvouched, so the one-in-five cap on exploratory picks could not be kept."
            self.fallbacks += 1
        elif may_explore and unvouched.any():                                    # rule 3: the one place a warned recipe may be chosen
            warned_idx = np.flatnonzero(unvouched)
            pick, kind = int(warned_idx[np.argmax(chance[warned_idx])]), "exploratory"
        elif not unmodelled:                                                          # every target modelled: choose the most likely to pass, among recipes the models can vouch for
            pick = int(free[np.argmax(chance[free])])
        else:                                                                         # rule 2
            order = free[np.argsort(-chance[free], kind="stable")]
            pool = order[:max(1, math.ceil(TOP_SHARE * len(order)))]
            pick, kind = self._untrusted_pick(trial_number, unit, is_local, pool, rows)
            pool_floor = float(chance[pool].min())
        best = int(np.argmax(chance))
        self.trace[trial_number] = {"candidates": int(len(unit)), "unvouched": int(unvouched.sum()), "best_overall_was_unvouched": bool(unvouched[best]), "pool_floor": pool_floor,
                                    "pick_chance": float(chance[pick]),
                                    "warned_by": {k: int(v.sum()) for k, v in warned.items()},                       # how many candidates each check warned, on its own
                                    "best_overall_warned_by": tuple(k for k, v in warned.items() if v[best])}      # and which checks warned the best-looking candidate
        stated = {r: (float(pred[r]["lo"][pick]), float(pred[r]["hi"][pick])) for r in (t.result for t in self.trusted)}
        chances = {r: float(pred[r]["chance"][pick]) for r in used}
        if not unmodelled:                                                            # a combined chance is stated ONLY when every target is modelled and none is stale
            chances["all_targets"] = float(np.prod(list(chances.values())))
        flags = {k: bool(v[pick]) for k, v in warned.items()}
        return Decision(trial_number, self._recipe(unit[pick]), kind, self._explain(kind, chances, pred, pick, flags, unmodelled, stale, trial_number, so_far, note, len(rows)),
                        chances, unmodelled, stale, stated, flags)

    def _explain(self, kind: str, chances: dict, pred: dict, pick: int, flags: dict, unmodelled: tuple, stale: tuple, trial_number: int, so_far: int, note: str, n_rows: int) -> str:
        said = "; ".join(f"{self.targets[r].label}: {c:.0%}" if r != "all_targets" else f"all targets together: {c:.0%}" for r, c in chances.items())
        what = {"exploit": f"Chosen from {n_rows:,} measured results as the recipe the models can vouch for that is most likely to pass. Chance of meeting each modelled target: {said}.",
                "exploratory": (f"An EXPLORATORY pick (at most one in any {EXPLORATORY_EVERY} consecutive trials; number {so_far + 1} so far): this recipe is unvouched, warned by "
                                f"{', '.join(k for k, v in flags.items() if v) or 'no check'}, so its chances ({said}) are NOT vouched for."),
                "stale_exploration": f"A stated range has stopped holding, so exploring: among the top {TOP_SHARE:.0%} of recipes by chance of meeting the targets that still hold ({said or 'none'}), this one is placed to learn the most (far from everything measured, or near the best measured passes).",
                "space_filling": f"Placed as far as possible from everything measured, among the top {TOP_SHARE:.0%} of recipes by chance of meeting the modelled targets ({said}).",
                "local_search": f"A local search around the best measured passes, among the top {TOP_SHARE:.0%} of recipes by chance of meeting the modelled targets ({said})."}[kind]
        return f"{what}{note} {self._reasons_text(unmodelled, stale)}".strip()
