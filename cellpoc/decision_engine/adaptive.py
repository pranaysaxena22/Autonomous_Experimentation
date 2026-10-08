"""The adaptive strategy: spread a few recipes evenly, then learn from every result.

Phase 1 (first N trials): recipes spread evenly across the allowed ranges, so the engine
sees the whole landscape before it commits.

Phase 2 (every trial after): from ALL measurements so far, fit a statistical model (a
Gaussian process) of how dissolution and hardness respond to the five ingredients, then
pick, from thousands of candidate recipes, the one most likely to pass BOTH specifications.

The engine sees only measurements and the specifications. It never sees the lab's hidden
truth, and it copes with trials that produced no result: they simply are not in `history`,
and their recipes (`skipped`) are kept out of the candidate pool.
"""
from __future__ import annotations

import math
import random
from typing import Sequence

import numpy as np

from ..contracts import Formulation, Measurement, Proposal, margin
from ..settings.models import DesignSpace, EngineSettings, Specifications

_LENGTHSCALES = (0.25, 0.4, 0.6, 0.9, 1.4)   # how quickly results change across the (0-1 scaled) space
_NOISE_LEVELS = (0.01, 0.05, 0.2)            # measurement scatter as a share of the signal
_MIN_RESULTS_TO_LEARN = 3                     # below this, keep spreading recipes out
_TOO_CLOSE = 0.02                             # candidates this near a past recipe are dropped
_LOCAL_SPREAD = 0.07                          # how far to search around the best results so far
_LOCAL_CENTRES = 3
_LOCAL_PER_CENTRE = 400


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    """Standard normal CDF (Abramowitz & Stegun 7.1.26 for erf; accurate to about 1e-7)."""
    x = z / math.sqrt(2.0)
    sign = np.sign(x)
    t = 1.0 / (1.0 + 0.3275911 * np.abs(x))
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = sign * (1.0 - poly * np.exp(-x * x))
    return 0.5 * (1.0 + erf)


def _kernel(a: np.ndarray, b: np.ndarray, lengthscale: float) -> np.ndarray:
    d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    return np.exp(-0.5 * d2 / lengthscale ** 2)


class _Model:
    """A Gaussian process for one measured property, with its own settings chosen from the data."""

    def __init__(self, x: np.ndarray, y: np.ndarray):
        self.x = x
        self.mean = float(y.mean())
        self.scale = float(y.std()) or 1.0
        ys = (y - self.mean) / self.scale
        best = None
        for lengthscale in _LENGTHSCALES:
            base = _kernel(x, x, lengthscale)
            for noise in _NOISE_LEVELS:
                chol = np.linalg.cholesky(base + (noise + 1e-8) * np.eye(len(x)))
                alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, ys))
                score = -0.5 * float(ys @ alpha) - float(np.log(np.diag(chol)).sum())
                if best is None or score > best[0]:
                    best = (score, lengthscale, chol, alpha)
        _, self.lengthscale, self.chol, self.alpha = best  # type: ignore[misc]

    def predict(self, candidates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Expected value and uncertainty (one standard deviation) for each candidate."""
        k = _kernel(candidates, self.x, self.lengthscale)
        mu = k @ self.alpha
        v = np.linalg.solve(self.chol, k.T)
        var = np.maximum(1.0 - (v ** 2).sum(axis=0), 1e-9)
        return mu * self.scale + self.mean, np.sqrt(var) * self.scale


class AdaptiveStrategy:
    name = "adaptive"
    description = "Spread-out starting recipes, then each recipe chosen from all results so far"

    def __init__(self, design_space: DesignSpace, specs: Specifications, engine: EngineSettings, seed: int):
        self._space = design_space
        self._specs = specs
        self._engine = engine
        self._seed = seed
        self._low = np.array([i.min for i in design_space.ingredients])
        self._span = np.array([i.max - i.min for i in design_space.ingredients])
        self._spread = self._spread_design(engine.initial_recipes)

    # ------------------------------------------------------------------ public
    def propose(self, trial_number: int, history: Sequence[Measurement],
                skipped: Sequence[Formulation] = ()) -> Proposal:
        if trial_number <= self._engine.initial_recipes:
            return Proposal(self._to_recipe(self._spread[trial_number - 1]),
                            f"Spread-out starting recipe {trial_number} of {self._engine.initial_recipes}: "
                            "the first recipes are placed evenly across the allowed ranges so the engine "
                            "can see the whole landscape before it starts choosing")
        if len(history) < _MIN_RESULTS_TO_LEARN:
            return self._fallback(trial_number, history, skipped)
        return self._learned(trial_number, history, skipped)

    # ------------------------------------------------------------------ phase 1
    def _spread_design(self, n: int) -> np.ndarray:
        """n points, one per slice of each ingredient's range, chosen to be as far apart as possible."""
        rng = np.random.default_rng(self._rng_seed("spread"))
        d = len(self._low)
        best, best_gap = None, -1.0
        for _ in range(400):
            slices = np.column_stack([rng.permutation(n) for _ in range(d)])
            points = (slices + rng.random((n, d))) / n
            gaps = ((points[:, None, :] - points[None, :, :]) ** 2).sum(axis=2) + np.eye(n) * 1e9
            gap = float(gaps.min())
            if gap > best_gap:
                best, best_gap = points, gap
        return best  # type: ignore[return-value]

    def _fallback(self, trial_number, history, skipped) -> Proposal:
        """Too few results to learn from (skipped trials removed them): keep exploring evenly."""
        rng = np.random.default_rng(self._rng_seed(f"fallback:{trial_number}"))
        past = self._past_points(history, skipped)
        candidates = rng.random((200, len(self._low)))
        if len(past):
            gaps = ((candidates[:, None, :] - past[None, :, :]) ** 2).sum(axis=2).min(axis=1)
            pick = candidates[int(gaps.argmax())]
        else:
            pick = candidates[0]
        return Proposal(self._to_recipe(pick),
                        f"Only {len(history)} usable result(s) so far, too few to learn from, so this recipe "
                        "is placed as far as possible from everything tried before")

    # ------------------------------------------------------------------ phase 2
    def _learned(self, trial_number, history, skipped) -> Proposal:
        specs = self._specs
        x = np.array([self._to_unit(m.formulation) for m in history])
        dissolution = _Model(x, np.array([m.dissolution_pct for m in history]))
        hardness = _Model(x, np.array([m.hardness_kp for m in history]))

        rng = np.random.default_rng(self._rng_seed(f"choose:{trial_number}"))
        past = self._past_points(history, skipped)
        best_results = sorted(history, key=lambda m: margin(m.dissolution_pct, m.hardness_kp, specs), reverse=True)
        candidates = self._candidates(rng, best_results[:_LOCAL_CENTRES])
        gaps = ((candidates[:, None, :] - past[None, :, :]) ** 2).sum(axis=2).min(axis=1)
        far_enough = candidates[gaps > _TOO_CLOSE ** 2]
        if len(far_enough):
            candidates = far_enough

        mu_d, sd_d = dissolution.predict(candidates)
        mu_h, sd_h = hardness.predict(candidates)
        p_dissolves = 1.0 - _normal_cdf((specs.dissolution.minimum - mu_d) / sd_d)
        p_hard = (_normal_cdf((specs.hardness.maximum - mu_h) / sd_h)
                  - _normal_cdf((specs.hardness.minimum - mu_h) / sd_h))
        chance = p_dissolves * p_hard
        pick = int(np.argmax(chance))

        nearest = int(np.argmin(((x - candidates[pick]) ** 2).sum(axis=1)))
        distance = float(np.sqrt(((x[nearest] - candidates[pick]) ** 2).sum()))
        return Proposal(self._to_recipe(candidates[pick]), self._why(
            len(history), trial_number, skipped, float(chance[pick]), float(p_dissolves[pick]), float(p_hard[pick]),
            float(mu_d[pick]), float(sd_d[pick]), float(mu_h[pick]), float(sd_h[pick]),
            history[nearest].trial_id, distance, best_results[0]))

    def _candidates(self, rng: np.random.Generator, centres: list[Measurement]) -> np.ndarray:
        d = len(self._low)
        pool = [rng.random((self._engine.candidates_per_decision, d))]
        for m in centres:
            pool.append(np.clip(self._to_unit(m.formulation) + rng.normal(0, _LOCAL_SPREAD, (_LOCAL_PER_CENTRE, d)), 0, 1))
        return np.vstack(pool)

    def _why(self, n_results, trial_number, skipped, chance, p_dissolves, p_hard, mu_d, sd_d, mu_h, sd_h,
             nearest_trial, distance, best: Measurement) -> str:
        s = self._specs
        where = (f"close to trial {nearest_trial}'s recipe, refining what worked there" if distance < 0.15
                 else f"in a part of the space not yet tested (nearest earlier recipe: trial {nearest_trial})")
        text = (f"Chosen from {n_results} measured results. Estimated chance of passing both specifications: {chance:.0%} "
                f"(dissolution of at least {s.dissolution.minimum:g}{s.dissolution.unit}: {p_dissolves:.0%}; "
                f"hardness between {s.hardness.minimum:g} and {s.hardness.maximum:g} {s.hardness.unit}: {p_hard:.0%}). "
                f"Expected dissolution {mu_d:.0f}% (give or take {sd_d:.0f}) and hardness {mu_h:.1f} kP (give or take {sd_h:.1f}). "
                f"This recipe sits {where}. Best result so far: trial {best.trial_id}.")
        if skipped:
            text += f" {len(skipped)} skipped trial(s) with no result are ignored."
        return text

    # ------------------------------------------------------------------ helpers
    def _rng_seed(self, label: str) -> int:
        return random.Random(f"adaptive:{self._seed}:{label}").getrandbits(63)

    def _to_unit(self, formulation: Formulation) -> np.ndarray:
        return (np.array(formulation.as_tuple()) - self._low) / self._span

    def _to_recipe(self, point: np.ndarray) -> Formulation:
        values = np.clip(self._low + np.clip(point, 0, 1) * self._span, self._low, self._low + self._span)
        return Formulation(*[float(v) for v in values])

    def _past_points(self, history, skipped) -> np.ndarray:
        points = [self._to_unit(m.formulation) for m in history] + [self._to_unit(f) for f in skipped]
        return np.array(points) if points else np.empty((0, len(self._low)))
