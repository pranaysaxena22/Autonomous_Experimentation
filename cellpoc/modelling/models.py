"""The candidate models and the two naive baselines, all behind one small interface: fit on training rows, then predict a value and a 90% range.

Every model is fitted only on the training rows of one fold. Scaling and the coding of categories are learned from those rows alone (`Encoder`), so nothing
about the test rows leaks in. Settings are fixed in advance (`Settings`) and never tuned to a table. Everything is deterministic: the same fold always gives the
same predictions.

How each model is fitted across results (stated in every report as a limitation, not left implicit):
- jointly across results: the Gaussian process, in its joint variant only (one shared set of length scales for all results, trained on the rows that have every result);
- independently, one model per result: everything else, including the ordinary Gaussian process.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.linear_model import Ridge
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import PolynomialFeatures

Z90 = 1.6448536269514722      # a 90% range is the prediction plus and minus this many standard deviations (a bell-shaped spread)
MAX_EXACT_GP_ROWS = 5000      # the exact Gaussian process is skipped above this many training rows (extrapolated limit, not measured)
MAX_ARD_INPUTS = 30           # up to this many inputs the Gaussian process learns one length scale per input; above it, one shared length scale
MIN_CALIBRATION_ROWS = 10     # fewest rows of calibration groups for a conformal range


class ModelSkipped(Exception):
    """A model that cannot be fitted on this fold, with a plain-English reason."""


@dataclass(frozen=True)
class Settings:
    """Fixed in advance. Fast mode does less work (fewer search rows, trees, members); the numbers it gives are not final."""
    mode: str
    gp_search_rows: int
    gbt_iterations: int
    rf_trees: int
    mlp_members: int
    mlp_iterations: int
    rf_jobs: int = -1


FULL = Settings("full", 500, 200, 300, 5, 500)
FAST = Settings("fast", 100, 100, 100, 3, 200)


@dataclass
class Prediction:
    mean: np.ndarray
    lo: np.ndarray            # the lower end of the 90% range (NaN when the model gives none)
    hi: np.ndarray


# ---------------------------------------------------------------- preparing inputs (learned on training rows only)
class Encoder:
    """Standardises numeric inputs and codes categories as 0/1 columns, using the training rows only. A category never seen in training becomes all zeros."""

    def __init__(self, numeric: list[str], categorical: list[str]):
        self.numeric, self.categorical = list(numeric), list(categorical)

    def fit(self, frame: pd.DataFrame) -> "Encoder":
        data = frame[self.numeric].to_numpy(dtype=float)
        self.mean_ = data.mean(axis=0) if self.numeric else np.zeros(0)
        spread = data.std(axis=0) if self.numeric else np.ones(0)
        self.scale_ = np.where(spread > 0, spread, 1.0)
        self.levels_ = {c: sorted(frame[c].astype(str).unique()) for c in self.categorical}
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        parts = [(frame[self.numeric].to_numpy(dtype=float) - self.mean_) / self.scale_] if self.numeric else []
        for c in self.categorical:
            values = frame[c].astype(str).to_numpy()
            parts.append(np.column_stack([(values == level).astype(float) for level in self.levels_[c]]))
        return np.hstack(parts) if parts else np.zeros((len(frame), 0))

    @property
    def n_numeric(self) -> int:
        return len(self.numeric)

    def names(self) -> list[str]:
        """The name of every encoded column, in order: the numeric inputs, then one per category value written as input=value."""
        return list(self.numeric) + [f"{c}={level}" for c in self.categorical for level in self.levels_[c]]


def _nan(n: int, k: int | None = None) -> np.ndarray:
    return np.full(n if k is None else (n, k), np.nan)


# ---------------------------------------------------------------- the models
class Model:
    key = ""
    label = ""
    family = "candidate"          # baseline or candidate
    joint = False                 # fitted jointly across results?
    interval = ""                 # how its 90% range is made, in words
    complexity = 0                # for the tie rule: lower is simpler and faster

    def fit(self, X: np.ndarray, y: np.ndarray, calibration: np.ndarray | None = None, inner: list | None = None) -> "Model":
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> Prediction:
        raise NotImplementedError


class MeanBaseline(Model):
    key, label, family, complexity = "mean", "Baseline: predict the training mean", "baseline", 0
    interval = "the training mean plus and minus 1.645 training standard deviations"

    def fit(self, X, y, calibration=None, inner=None):
        self.mean_, self.sd_ = y.mean(axis=0), y.std(axis=0, ddof=1) if len(y) > 1 else np.zeros(y.shape[1:])
        return self

    def predict(self, X):
        mean = np.broadcast_to(self.mean_, (len(X),) + np.shape(self.mean_)).copy()
        return Prediction(mean, mean - Z90 * self.sd_, mean + Z90 * self.sd_)


class NearestNeighbour(Model):
    key, label, family, complexity = "nearest", "Baseline: nearest-neighbour lookup", "baseline", 0
    interval = "none (a lookup gives no range)"

    def fit(self, X, y, calibration=None, inner=None):
        self.model_ = KNeighborsRegressor(n_neighbors=1).fit(X, y)
        return self

    def predict(self, X):
        mean = self.model_.predict(X)
        return Prediction(mean, _nan(*mean.shape), _nan(*mean.shape))


PENALTIES = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)      # the ridge penalties tried; fixed in advance
DEFAULT_PENALTY = 1.0                                          # used only when there are too few groups inside the training rows to choose by validation


def choose_penalty(features: np.ndarray, y: np.ndarray, inner: list | None) -> tuple[float, bool, float]:
    """The ridge penalty with the smallest error on held-out groups INSIDE the training rows. `inner` is a list of (fit rows, validation rows), positions within the
    training rows only; the real held-out fold never enters. Returns (penalty, chosen by validation, root-mean-square error on those inner groups, nan if not chosen)."""
    if not inner:
        return DEFAULT_PENALTY, False, float("nan")
    squared = np.zeros(len(PENALTIES))
    n = 0
    for fit, check in inner:
        centre = features[fit].mean(axis=0)
        mean_y = y[fit].mean()
        a, b, held = features[fit] - centre, y[fit] - mean_y, features[check] - centre
        # one decomposition of the SMALLER of the two Gram matrices gives every penalty's answer (the same ridge mathematics, much faster for a wide table)
        if a.shape[0] <= a.shape[1]:
            values, vectors = np.linalg.eigh(a @ a.T)
            reach, weight = (held @ a.T) @ vectors, vectors.T @ b
        else:
            values, vectors = np.linalg.eigh(a.T @ a)
            reach, weight = held @ vectors, vectors.T @ (a.T @ b)
        values = np.clip(values, 0.0, None)
        for i, penalty in enumerate(PENALTIES):
            squared[i] += float(((y[check] - (reach @ (weight / (values + penalty)) + mean_y)) ** 2).sum())
        n += len(check)
    best = int(np.argmin(squared))
    return PENALTIES[best], True, math.sqrt(squared[best] / n)


class _Ridge(Model):
    """Ridge regression whose penalty is chosen by validation on whole groups inside the training rows (never on the held-out fold)."""
    interval = ("the prediction plus and minus 1.645 times the error on held-out groups inside the training rows (the training error when there are too few groups to hold out); "
                "the penalty is chosen on those same inner groups")

    def _features(self, X):
        raise NotImplementedError

    def _prepare(self, X):
        pass

    def fit(self, X, y, calibration=None, inner=None):
        self._prepare(X)
        features = self._features(X)
        self.penalty_, self.by_validation_, cv_error = choose_penalty(features, y, inner)
        self.model_ = Ridge(alpha=self.penalty_).fit(features, y)
        self.sd_ = cv_error if np.isfinite(cv_error) else float((y - self.model_.predict(features)).std())
        return self

    def predict(self, X):
        mean = self.model_.predict(self._features(X))
        return Prediction(mean, mean - Z90 * self.sd_, mean + Z90 * self.sd_)


class LinearRidge(_Ridge):
    key, label, complexity = "linear", "Linear regression (ridge)", 1

    def _features(self, X):
        return X


class QuadraticRidge(_Ridge):
    """Squares and pairwise products of the NUMERIC inputs only. Category columns (0/1 codes for product, strength and the like) enter linearly and are never
    squared or multiplied: squaring a 0/1 column duplicates it, and products of mutually exclusive categories are almost always zero."""
    key, label, complexity = "quadratic", "Quadratic regression (ridge)", 2

    def __init__(self, n_numeric: int):
        self.n_numeric = n_numeric

    def _prepare(self, X):
        self.poly_ = PolynomialFeatures(degree=2, include_bias=False).fit(X[:, :self.n_numeric])

    def _features(self, X):
        return np.hstack([self.poly_.transform(X[:, :self.n_numeric]), X[:, self.n_numeric:]])

class GradientBoostingConformal(Model):
    key, label, complexity = "boosting", "Gradient-boosted trees with conformal ranges", 3
    interval = "split-conformal: the 90th percentile of the errors on whole calibration groups kept apart from the fitting rows"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _new(self):
        return HistGradientBoostingRegressor(max_iter=self.settings.gbt_iterations, learning_rate=0.1, early_stopping=False, random_state=0)

    def fit(self, X, y, calibration=None, inner=None):
        self.q_ = np.nan
        if calibration is not None and calibration.sum() >= MIN_CALIBRATION_ROWS and (~calibration).sum() >= MIN_CALIBRATION_ROWS:
            self.model_ = self._new().fit(X[~calibration], y[~calibration])
            errors = np.abs(y[calibration] - self.model_.predict(X[calibration]))
            n = len(errors)
            self.q_ = float(np.quantile(errors, min(1.0, math.ceil((n + 1) * 0.9) / n), method="higher"))
        else:                       # no whole calibration groups can be spared: the model is fitted on everything and gives no range
            self.model_ = self._new().fit(X, y)
        return self

    def predict(self, X):
        mean = self.model_.predict(X)
        return Prediction(mean, mean - self.q_, mean + self.q_)


class RandomForest(Model):
    key, label, complexity = "forest", "Random forest", 4
    interval = "the prediction plus and minus 1.645 times the spread between the trees"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fit(self, X, y, calibration=None, inner=None):
        self.model_ = RandomForestRegressor(n_estimators=self.settings.rf_trees, min_samples_leaf=2, n_jobs=self.settings.rf_jobs, random_state=0).fit(X, y)
        return self

    def predict(self, X):
        trees = np.stack([t.predict(X) for t in self.model_.estimators_])
        mean, spread = trees.mean(axis=0), trees.std(axis=0)
        return Prediction(mean, mean - Z90 * spread, mean + Z90 * spread)


class NeuralEnsemble(Model):
    key, label, complexity = "ensemble", "Neural-network ensemble", 5
    interval = "the average of the members plus and minus 1.645 times the spread between them"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fit(self, X, y, calibration=None, inner=None):
        self.mean_, spread = y.mean(axis=0), y.std(axis=0)
        self.scale_ = np.where(spread > 0, spread, 1.0)
        self.members_ = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")           # a network that stops at its step limit is normal in a fixed-effort comparison
            for seed in range(self.settings.mlp_members):
                self.members_.append(MLPRegressor(hidden_layer_sizes=(32, 32), max_iter=self.settings.mlp_iterations, early_stopping=False,
                                                  random_state=seed).fit(X, (y - self.mean_) / self.scale_))
        return self

    def predict(self, X):
        each = np.stack([m.predict(X) for m in self.members_]) * self.scale_ + self.mean_
        mean, spread = each.mean(axis=0), each.std(axis=0)
        return Prediction(mean, mean - Z90 * spread, mean + Z90 * spread)


class GaussianProcess(Model):
    key, label, complexity = "gp", "Gaussian process", 6
    interval = "the model's own predictive uncertainty (plus and minus 1.645 standard deviations)"

    def __init__(self, settings: Settings, n_inputs: int):
        self.settings, self.n_inputs = settings, n_inputs

    def _kernel(self):
        scale = np.ones(self.n_inputs) if self.n_inputs <= MAX_ARD_INPUTS else 1.0
        return ConstantKernel(1.0) * Matern(length_scale=scale, nu=2.5) + WhiteKernel(0.1)

    def fit(self, X, y, calibration=None, inner=None):
        if len(X) > MAX_EXACT_GP_ROWS:
            raise ModelSkipped(f"it has {len(X):,} training rows, more than the {MAX_EXACT_GP_ROWS:,} the exact Gaussian process is run on")
        # step 1: the slow search for the settings, on a fixed sample of the training rows only; step 2: the exact model on every training row
        sample = np.random.default_rng(0).choice(len(X), min(len(X), self.settings.gp_search_rows), replace=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")           # a search that reaches the edge of its allowed range is reported by the calibration, not here
            searched = GaussianProcessRegressor(self._kernel(), normalize_y=True, n_restarts_optimizer=0, random_state=0).fit(X[sample], y[sample])
            self.model_ = GaussianProcessRegressor(searched.kernel_, optimizer=None, normalize_y=True).fit(X, y)
        return self

    def predict(self, X):
        mean, spread = self.model_.predict(X, return_std=True)
        spread = spread if spread.shape == mean.shape else spread[:, None]
        return Prediction(mean, mean - Z90 * spread, mean + Z90 * spread)


class GaussianProcessJoint(GaussianProcess):
    key, label, joint, complexity = "gp_joint", "Gaussian process, joint across results", True, 7
    interval = "the model's own predictive uncertainty (plus and minus 1.645 standard deviations), one shared set of length scales for all results"


def single_models(settings: Settings, n_numeric: int, n_inputs: int) -> list[Model]:
    """Every model that is fitted on one result at a time, baselines first."""
    return [MeanBaseline(), NearestNeighbour(), LinearRidge(), QuadraticRidge(n_numeric), GradientBoostingConformal(settings), RandomForest(settings),
            NeuralEnsemble(settings), GaussianProcess(settings, n_inputs)]


def joint_models(settings: Settings, n_inputs: int) -> list[Model]:
    return [GaussianProcessJoint(settings, n_inputs)]


MODELS_BY_KEY = {m.key: m for m in single_models(FAST, 1, 1) + joint_models(FAST, 1)}       # labels and facts about each model, for reports
FIT_WORDS = {False: "independently, one model per result", True: "jointly across results"}
ORDER = ["mean", "nearest", "linear", "quadratic", "boosting", "forest", "ensemble", "gp", "gp_joint"]
