"""The decision-usefulness replay (Stage 3b-3): had the cell used a model to choose which recipes to run next, would it have chosen better than chance?

SYNTHETIC MOCKS ONLY. The method was fixed before any replay number existed (docs/decisions.md):
- A DECISION WINDOW is one forward step of the Stage 3a later-dates hold-out. Its model was trained on rows dated before the window and nothing else; the replay reuses those saved
  predictions (it fits nothing) and checks every window again for a leak before using it.
- The targets come from the setup (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0 in the mock setups). A candidate passes when its measured value meets the target.
- Candidates are ranked by the model's probability that the target is met: the rule's chosen model's predicted value and its stated 90% range as stated (not recalibrated), read as a
  bell-shaped spread. For all three targets together the three probabilities are multiplied (the three results are not independent: the usual joint-versus-independent limitation).
- The top PICK_SHARE of each window is picked. The comparison is with random picking (the window's own pass rate) and the perfect ranking (passers first).
- The error bar resamples whole batches inside each window. The verdict, and what counts as "no room to improve", are fixed below.
- Whether warned picks did worse is asked for each per-recipe status separately, and only when enough picks were warned. This replay is forward in time, so its own evidence is of the later-dates
  type only: the whole-batch and whole-supplier evidence for the same warning is shown beside it from the saved hold-outs, never merged, together with a plain statement of what the mocks
  cannot show (their recipe inputs neither drift with the date nor differ by supplier).
Nothing measured in a window reaches the ranking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .carry import BORDERLINE, CARRIED, CarryDecision
from .domain import evaluate_kind, fit_reference, warn
from .findings import Finding, make
from .splits import Fold, _labels
from .validate import Validation

PICK_SHARE = 0.10
Z90 = 1.6448536269514722                 # a 90% range is plus or minus this many standard deviations of a bell-shaped spread
DRAWS = 2000
SEED = 20261013
NO_ROOM_RANDOM = 0.98                    # a target met at least this often by random picking leaves nothing to improve
NO_ROOM_GAP = 0.02                       # ... and so does a gap between random and perfect picking of less than this
MIN_WARNED = 30                          # fewest warned picks (or warned rows) before anything is said about them
STATUSES = ("distance", "range", "category")
STATUS_WORDS = {"distance": "distance", "range": "numeric range", "category": "unseen supplier or product"}      # how a status is named in a sentence
ALL_THREE = "all_three"
BEAT, NOT_BEAT, NO_ROOM = "beat random", "did not beat random", "no room to improve"
SYNTHETIC = "synthetic"


class ReplayLeak(Exception):
    """A decision window that could see the future. Raised before anything is ranked."""


class ReplayRefused(Exception):
    """The replay is only run on synthetic tables."""


# ---------------------------------------------------------------- the targets
@dataclass(frozen=True)
class Target:
    result: str
    goal: str                            # at_least, at_most or between
    low: float | None
    high: float | None
    label: str
    unit: str

    def met(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=float)
        ok = np.ones(len(values), bool)
        if self.low is not None:
            ok &= values >= self.low
        if self.high is not None:
            ok &= values <= self.high
        return ok

    @property
    def words(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        if self.goal == "between":
            return f"{self.label} between {self.low:g} and {self.high:g}{unit}"
        return f"{self.label} {'at least' if self.goal == 'at_least' else 'at most'} {(self.low if self.goal == 'at_least' else self.high):g}{unit}"


def targets_from_setup(setup: dict) -> dict[str, Target]:
    """The targets exactly as the setup states them: nothing is added or invented here."""
    out = {}
    for c in setup.get("targets", {}).get("constraints", []):
        goal = c.get("goal")
        low = c.get("value") if goal == "at_least" else c.get("low") if goal == "between" else None
        high = c.get("value") if goal == "at_most" else c.get("high") if goal == "between" else None
        if goal in ("at_least", "at_most", "between") and (low is not None or high is not None):
            out[c["response"]] = Target(c["response"], goal, low, high, c.get("label", c["response"]), c.get("unit", ""))
    return out


def _cdf(x: np.ndarray) -> np.ndarray:
    return np.array([0.5 * (1.0 + math.erf(v / math.sqrt(2.0))) for v in np.atleast_1d(x)])


def probability_met(target: Target, mean: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """The model's probability that each recipe meets the target, from its predicted value and stated 90% range."""
    mean, lo, hi = (np.asarray(a, dtype=float) for a in (mean, lo, hi))
    if not (np.isfinite(mean).all() and np.isfinite(lo).all() and np.isfinite(hi).all()):
        raise ValueError("the model states no range for some recipes, so a probability cannot be worked out")
    sd = np.maximum((hi - lo) / (2.0 * Z90), 1e-9)
    upper = _cdf((target.high - mean) / sd) if target.high is not None else np.ones(len(mean))
    lower = _cdf((target.low - mean) / sd) if target.low is not None else np.zeros(len(mean))
    return upper - lower


# ---------------------------------------------------------------- the guard against seeing the future
def leak_problems(dates: pd.Series, fold: Fold) -> list[str]:
    """Everything that would let a window see the future (empty means safe): a row in both training and window, or a training row dated on or after the window's first date."""
    problems = []
    shared = np.intersect1d(fold.train, fold.test)
    if len(shared):
        problems.append(f"{len(shared)} rows are in both the training rows and the window")
    train, test = pd.to_datetime(dates.iloc[fold.train]).dropna(), pd.to_datetime(dates.iloc[fold.test]).dropna()
    if len(test):
        late = int((train >= test.min()).sum())
        if late:
            problems.append(f"{late} training rows are dated on or after the window's first date")
    return problems


# ---------------------------------------------------------------- one window, picked and scored
@dataclass
class Window:
    number: int
    first: str
    last: str
    p: np.ndarray                        # the model's probability that each candidate meets the target
    passed: np.ndarray                   # whether it really did
    batch: np.ndarray                    # the batch of each candidate
    flags: dict[str, np.ndarray] = field(default_factory=dict)     # per-recipe warning status -> warned


def n_picks(n: int, share: float = PICK_SHARE) -> int:
    return max(1, int(round(share * n)))


def pick(p: np.ndarray, share: float = PICK_SHARE) -> np.ndarray:
    """The top `share` of candidates by probability (ties go to the earlier row: nothing is random). Only the probabilities are used, never an outcome."""
    order = np.argsort(-np.asarray(p, dtype=float), kind="stable")
    mask = np.zeros(len(p), bool)
    mask[order[:n_picks(len(p), share)]] = True
    return mask


@dataclass
class WindowScore:
    number: int
    first: str
    last: str
    n: int
    picks: int
    passers: int
    hits: int                            # picks that really passed
    random_expected: float               # passes expected from picking the same number at random
    perfect: int                         # passes if every pick were a passer, as far as passers go


@dataclass
class Summary:
    windows: list[WindowScore]
    n: int
    picks: int
    picked_rate: float
    random_rate: float
    perfect_rate: float
    captured: float | None               # (picked - random) / (perfect - random)
    gap: float                           # picked - random
    interval: tuple[float, float] | None
    verdict: str


def score_window(w: Window, share: float = PICK_SHARE) -> tuple[WindowScore, np.ndarray]:
    mask = pick(w.p, share)
    k, passers = int(mask.sum()), int(w.passed.sum())
    return WindowScore(w.number, w.first, w.last, len(w.p), k, passers, int(w.passed[mask].sum()), k * passers / len(w.p), min(k, passers)), mask


def verdict_of(random_rate: float, perfect_rate: float, gap: float, lower: float | None) -> str:
    """Fixed in advance: no verdict when there is no room to improve; otherwise 'beat random' needs the picked rate above random AND the error bar's lower end above 0."""
    if random_rate >= NO_ROOM_RANDOM or perfect_rate - random_rate < NO_ROOM_GAP:
        return NO_ROOM
    return BEAT if gap > 0 and lower is not None and lower > 0 else NOT_BEAT


def _bootstrap(windows: list[Window], masks: list[np.ndarray]) -> tuple[float, float] | None:
    """95% interval of (picked rate - random rate), resampling whole batches inside each window."""
    rng = np.random.default_rng(SEED)
    hits = np.zeros(DRAWS)
    expected = np.zeros(DRAWS)
    picks = np.zeros(DRAWS)
    for w, mask in zip(windows, masks):
        names = sorted(set(w.batch))
        b_n = np.array([(w.batch == b).sum() for b in names], float)
        b_pick = np.array([mask[w.batch == b].sum() for b in names], float)
        b_hit = np.array([(mask & w.passed)[w.batch == b].sum() for b in names], float)
        b_pass = np.array([w.passed[w.batch == b].sum() for b in names], float)
        idx = rng.integers(0, len(names), (DRAWS, len(names)))
        n, k, h, ps = b_n[idx].sum(1), b_pick[idx].sum(1), b_hit[idx].sum(1), b_pass[idx].sum(1)
        hits += h
        expected += k * ps / n
        picks += k
    ok = picks > 0
    if not ok.any():
        return None
    gap = (hits[ok] - expected[ok]) / picks[ok]
    return float(np.quantile(gap, 0.025)), float(np.quantile(gap, 0.975))


def summarise(windows: list[Window], share: float = PICK_SHARE) -> tuple[Summary, list[np.ndarray]]:
    scored = [score_window(w, share) for w in windows]
    scores, masks = [s for s, _ in scored], [m for _, m in scored]
    picks = sum(s.picks for s in scores)
    picked, random, perfect = (sum(getattr(s, a) for s in scores) / picks for a in ("hits", "random_expected", "perfect"))
    interval = _bootstrap(windows, masks)
    gap = picked - random
    captured = gap / (perfect - random) if perfect - random > 1e-12 else None
    return Summary(scores, sum(s.n for s in scores), picks, picked, random, perfect, captured, gap, interval,
                   verdict_of(random, perfect, gap, interval[0] if interval else None)), masks


# ---------------------------------------------------------------- did warned picks do worse?
@dataclass
class WarnedPicks:
    status: str
    warned: int
    unwarned: int
    warned_rate: float | None
    unwarned_rate: float | None
    said: bool                            # enough warned picks to compare


def warned_picks(windows: list[Window], masks: list[np.ndarray], status: str) -> WarnedPicks:
    flag = np.concatenate([w.flags[status][m] for w, m in zip(windows, masks)])
    passed = np.concatenate([w.passed[m] for w, m in zip(windows, masks)])
    said = int(flag.sum()) >= MIN_WARNED and int((~flag).sum()) >= MIN_WARNED
    return WarnedPicks(status, int(flag.sum()), int((~flag).sum()), float(passed[flag].mean()) if flag.any() else None,
                       float(passed[~flag].mean()) if (~flag).any() else None, said)


# ---------------------------------------------------------------- what the warning can and cannot be trusted for, by shift type (from the saved hold-outs)
@dataclass
class Reliability:
    kind: str
    heading: str
    rows_warned: list[int]
    lifts: list[float | None]
    ratios: list[float | None]
    range_warned: list[int]
    verdict: str                          # "picks out the large errors", "mixed", "does not", "cannot be judged"


def reliability_word(rows_warned: list[int], lifts: list[float | None]) -> str:
    """Fixed in advance: judged only with at least MIN_WARNED warned rows in every result; the line is chance (a lift of 1)."""
    if not rows_warned or min(rows_warned) < MIN_WARNED or any(v is None for v in lifts):
        return "cannot be judged"
    above = [v > 1.0 for v in lifts]
    return "picks out the large errors" if all(above) else "mixed" if any(above) else "does not"


@dataclass
class Movement:
    drift: float | None                   # the largest rank correlation (either sign) of any numeric input with the date
    drift_input: str
    supplier: float | None                # the largest share of any numeric input's spread explained by the supplier
    supplier_input: str


def movement(table, result: str) -> Movement:
    """How much the inputs themselves move with the date or the supplier: the part of a shift an input-based warning could see."""
    frame, rt = table.frame, table.responses[result]
    drift, drift_input, share, share_input = None, "", None, ""
    if "date" in table.groups:
        when = pd.to_datetime(frame[table.groups["date"].columns[0]]).rank()
        for c in rt.numeric:
            x = frame[c].astype(float)
            if x.nunique() > 2:
                r = abs(float(x.rank().corr(when)))
                if drift is None or r > drift:
                    drift, drift_input = r, c
    if "supplier" in table.groups:
        who = _labels(frame, np.arange(len(frame)), table.groups["supplier"].columns)[0].to_numpy()
        for c in rt.numeric:
            x = frame[c].astype(float)
            if x.nunique() > 2 and x.var() > 0:
                m = x.groupby(who).transform("mean")
                s = float(((m - x.mean()) ** 2).sum() / ((x - x.mean()) ** 2).sum())
                if share is None or s > share:
                    share, share_input = s, c
    return Movement(drift, drift_input, share, share_input)


# ---------------------------------------------------------------- the replay of one table
@dataclass
class TargetReplay:
    key: str                              # a result's name, or ALL_THREE
    heading: str
    results: tuple[str, ...]
    models: dict[str, str]
    exploratory: bool
    summary: Summary
    warned: dict[str, WarnedPicks]
    same_inputs: bool
    findings: list[Finding] = field(default_factory=list)


@dataclass
class TableReplay:
    table: str
    targets: list[TargetReplay]
    reliability: list[Reliability]
    movement: Movement
    not_replayed: list[tuple[str, str]]   # (result, why)


def _reference(table, rt, fold: Fold, cache: dict):
    key = (table.name, tuple(rt.numeric), tuple(rt.categorical), fold.number)
    if key not in cache:
        spec = table.groups["date"]
        cache[key] = fit_reference(table.frame, rt.numeric, rt.categorical, fold.train, _labels(table.frame, fold.train, spec.columns)[0].to_numpy())
    return cache[key]


def build_windows(validation: Validation, results: tuple[str, ...], models: dict[str, str], targets: dict[str, Target], cache: dict | None = None) -> tuple[list[Window], bool]:
    """The decision windows for one target (or all three together): the candidates measured for every result involved, the model's probability for each, and the per-recipe warnings."""
    table, cache = validation.table, {} if cache is None else cache
    frame = table.frame
    dates = frame[table.groups["date"].columns[0]]
    first = table.responses[results[0]]
    same_inputs = all(table.responses[r].numeric == first.numeric and table.responses[r].categorical == first.categorical for r in results)
    runs = {r: validation.runs[(r, "date")] for r in results}
    numbers = sorted(set.intersection(*({f.number for f in runs[r].folds} for r in results)))
    windows = []
    for number in numbers:
        folds = {r: next(f for f in runs[r].plan.folds if f.number == number) for r in results}
        saved = {r: next(f for f in runs[r].folds if f.number == number) for r in results}
        for r in results:
            problems = leak_problems(dates, folds[r])
            if problems:
                raise ReplayLeak(f"{table.name}, {r}, step {number}: " + "; ".join(problems))
        common = sorted(set.intersection(*(set(saved[r].test.tolist()) for r in results)))
        if not common:
            continue
        p, passed = np.ones(len(common)), np.ones(len(common), bool)
        for r in results:
            where = {int(pos): i for i, pos in enumerate(saved[r].test)}
            idx = np.array([where[pos] for pos in common])
            pred = saved[r].preds[models[r]]
            p *= probability_met(targets[r], pred.mean[idx], pred.lo[idx], pred.hi[idx])
            passed &= targets[r].met(saved[r].y[idx])
        positions = np.array(common)
        ref = _reference(table, first, folds[results[0]], cache)
        w = warn(ref, frame, positions)
        windows.append(Window(number, *folds[results[0]].held_out, p, passed, _labels(frame, positions, table.groups["batch"].columns)[0].to_numpy(),
                              {"distance": w.by_distance, "range": w.by_range, "category": w.by_category}))
    return windows, same_inputs


def target_findings(table_name: str, heading: str, summary: Summary, warned: dict[str, WarnedPicks]) -> list[Finding]:
    """The messages about one replayed target: no room to improve (M70) and too few warned picks to say anything (M71, for each status)."""
    found = []
    if summary.verdict == NO_ROOM:
        found.append(make("M70", "", table_name, heading, random=f"{100 * summary.random_rate:.1f}", perfect=f"{100 * summary.perfect_rate:.1f}",
                          line=f"{100 * NO_ROOM_RANDOM:.0f}", gap=f"{100 * NO_ROOM_GAP:.0f}"))
    for s, w in warned.items():
        if not w.said:
            found.append(make("M71", "", table_name, heading, status=STATUS_WORDS[s], n=w.warned, picks=summary.picks, minimum=MIN_WARNED))
    return found


def _replay_target(validation: Validation, key: str, heading: str, results: tuple[str, ...], models: dict[str, str], targets: dict[str, Target],
                   exploratory: bool, cache: dict) -> TargetReplay | None:
    windows, same = build_windows(validation, results, models, targets, cache)
    if not windows:
        return None
    summary, masks = summarise(windows)
    warned = {s: warned_picks(windows, masks, s) for s in STATUSES}
    return TargetReplay(key, heading, results, models, exploratory, summary, warned, same, target_findings(validation.table.name, heading, summary, warned))


def replay_table(validation: Validation, decisions: list[CarryDecision], targets: dict[str, Target], cache: dict | None = None) -> TableReplay:
    """The replay of one SYNTHETIC table, for every carried or borderline result that has a target in the setup, and for all of them together when every target's result is replayable."""
    table = validation.table
    if table.label is None or table.label.status != SYNTHETIC:
        raise ReplayRefused(f"{table.name} is not labelled synthetic: the replay is only run on the synthetic mocks, and no specification window is ever invented for real data.")
    cache = {} if cache is None else cache
    usable, left_out = {}, []
    for d in decisions:
        if d.table != table.name:
            continue
        if d.status not in (CARRIED, BORDERLINE):
            left_out.append((d.result, "not carried in 3b-1, so not replayed"))
        elif d.result not in targets:
            left_out.append((d.result, "the setup states no target for it"))
        elif (d.result, "date") not in validation.runs or not validation.runs[(d.result, "date")].plan.available:
            left_out.append((d.result, "no forward-in-time steps could be run for it"))
        else:
            usable[d.result] = d
    out = []
    for r, d in usable.items():
        out.append(_replay_target(validation, r, f"{table.column_label(r)}: {targets[r].words}" + (f" [{d.tag}]" if d.tag else ""), (r,), {r: d.chosen}, targets,
                                  d.status == BORDERLINE, cache))
    wanted = tuple(targets)
    if len(usable) >= 2 and all(r in usable for r in wanted):
        borderline = any(usable[r].status == BORDERLINE for r in wanted)
        tag = " [EXPLORATORY: borderline result inside it]" if borderline else ""
        out.append(_replay_target(validation, ALL_THREE, "All three targets together: " + "; ".join(targets[r].words for r in wanted) + tag, wanted, {r: usable[r].chosen for r in wanted},
                                  targets, borderline, cache))
    refs: dict = {}
    reliability = []
    for kind in ("batch", "supplier", "date"):
        kinds = [(r, evaluate_kind(validation, r, kind, usable[r].chosen, None, refs)) for r in usable]
        kinds = [(r, k) for r, k in kinds if k is not None]
        if not kinds:
            continue
        rows = [k.parts["distance"].n_warned for _, k in kinds]
        lifts = [k.parts["distance"].lift for _, k in kinds]
        reliability.append(Reliability(kind, kinds[0][1].heading, rows, lifts, [k.parts["distance"].error_ratio for _, k in kinds],
                                       [k.parts["range"].n_warned for _, k in kinds], reliability_word(rows, lifts)))
    first = next(iter(usable)) if usable else next(iter(table.responses))
    return TableReplay(table.name, [t for t in out if t is not None], reliability, movement(table, first), left_out)
