"""The known-answer synthetic scenarios for the group-level warning, S1 to S5, exactly as fixed in docs/decisions.md before the method was tested.

Each function builds made-up groups of recipes with a known truth (same source, a shifted group, an unseen category, a drifted time period, small groups, a large ordinary batch
effect) and measures what the warning does. The check file asserts the criteria that were fixed in advance; nothing here is tuned to make a scenario pass.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from cellpoc.modelling.domain import fit_reference, warn
from cellpoc.modelling.findings import make
from cellpoc.modelling.group_domain import GroupResult, check_group, fit_group_reference, group_findings, null_threshold

P = 40
COLUMNS = [f"x{i}" for i in range(P)]


def make_groups(rng, groups: int, per: int, effect: float = 0.15, shift: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
    """`groups` groups of `per` recipes: bell-shaped noise on every input plus an ordinary effect shared by a group (its batch effect), and optionally a shift on named inputs."""
    ordinary = rng.normal(0.0, effect, (groups, P))
    x = rng.normal(size=(groups * per, P)) + np.repeat(ordinary, per, axis=0)
    for column, amount in (shift or {}).items():
        x[:, column] += amount
    return x, np.repeat(np.arange(groups), per).astype(str)


def standardise(train: np.ndarray, *others: np.ndarray):
    mean, sd = train.mean(axis=0), train.std(axis=0)
    return [(a - mean) / sd for a in (train,) + others]


def flagged_share(trials: int, build, seed: int, **options) -> float:
    """The share of made-up test groups that the group warning flags."""
    flagged = 0
    for t in range(trials):
        rng = np.random.default_rng(seed + t)
        train_x, train_labels = make_groups(rng, options.get("train_groups", 60), options.get("train_per", 40), options.get("effect", 0.15))
        test_x = build(rng)
        train_s, test_s = standardise(train_x, test_x)
        ref = fit_group_reference(train_s, train_labels, COLUMNS)
        w = check_group(ref, test_s)
        flagged += bool(w and w.flagged)
    return flagged / trials


def s1_same_source(trials: int = 200) -> float:
    return flagged_share(trials, lambda rng: make_groups(rng, 1, 30)[0], seed=1000)


def s2_shifted(trials: int = 100) -> dict:
    """A group shifted by 1 standard deviation in 3 of 40 inputs (30 recipes), and what the per-recipe distance check does to the same recipes."""
    group = flagged_share(trials, lambda rng: make_groups(rng, 1, 30, shift={0: 1.0, 1: 1.0, 2: 1.0})[0], seed=2000)
    rows_flagged = []
    for t in range(20):
        rng = np.random.default_rng(2500 + t)
        train_x, labels = make_groups(rng, 60, 40)
        test_x = make_groups(rng, 1, 30, shift={0: 1.0, 1: 1.0, 2: 1.0})[0]
        frame = pd.DataFrame(np.vstack([train_x, test_x]), columns=COLUMNS)
        train = np.arange(len(train_x))
        ref = fit_reference(frame, COLUMNS, [], train, labels)
        rows_flagged.append(float(warn(ref, frame, np.arange(len(train_x), len(frame))).by_distance.mean()))
    return {"group": group, "per_recipe_rows": float(np.mean(rows_flagged))}


def s3_unseen_category() -> dict:
    """A group from a supplier never seen in training: the unseen-category status flags every recipe; the group statistic is reported (the encoded category carries little signal)."""
    rng = np.random.default_rng(3000)
    train_x, labels = make_groups(rng, 60, 40)
    frame = pd.DataFrame(train_x, columns=COLUMNS)
    frame["supplier"] = np.where(np.arange(len(frame)) % 2 == 0, "A", "B")
    test = pd.DataFrame(make_groups(rng, 1, 30)[0], columns=COLUMNS)
    test["supplier"] = "C"
    both = pd.concat([frame, test], ignore_index=True)
    ref = fit_reference(both, COLUMNS, ["supplier"], np.arange(len(frame)), labels)
    w = warn(ref, both, np.arange(len(frame), len(both)))
    return {"category_rows": float(w.by_category.mean()), "names_it": w.unseen.get("supplier") == {"C": 30}}


def s4_later_period(trials: int = 100) -> float:
    """A later time period drifting by 0.5 standard deviations in 10 of 40 inputs (60 recipes), against 30 ordinary periods of 80 recipes."""
    return flagged_share(trials, lambda rng: make_groups(rng, 1, 60, shift={i: 0.5 for i in range(10)})[0], seed=4000, train_groups=30, train_per=80)


def s5a_small_groups(trials: int = 100) -> dict:
    """The S2 shift in groups of 5 recipes: weaker than in groups of 30, but above the false-alarm rate."""
    shift = {0: 1.0, 1: 1.0, 2: 1.0}
    small = flagged_share(trials, lambda rng: make_groups(rng, 1, 5, shift=shift)[0], seed=5000)
    large = flagged_share(trials, lambda rng: make_groups(rng, 1, 30, shift=shift)[0], seed=5000)
    false_alarm = flagged_share(trials, lambda rng: make_groups(rng, 1, 5)[0], seed=5200)
    return {"small": small, "large": large, "false_alarm_small": false_alarm}


def s5b_ordinary_batch_effect(trials: int = 100) -> dict:
    """A large ordinary batch effect and no shift: the group-based threshold flags about 5%; a chance-alone threshold flags far more."""
    based, chance = 0, 0
    for t in range(trials):
        rng = np.random.default_rng(6000 + t)
        train_x, labels = make_groups(rng, 60, 40, effect=0.6)
        test_x = make_groups(rng, 1, 30, effect=0.6)[0]
        train_s, test_s = standardise(train_x, test_x)
        natural = check_group(fit_group_reference(train_s, labels, COLUMNS), test_s)
        merged = np.array([f"m{int(g) % 4}" for g in labels])                 # the same rows with their groups merged into 4, so no ordinary group-to-group variation can be seen
        alone = check_group(fit_group_reference(train_s, merged, COLUMNS), test_s)
        based += bool(natural.flagged)
        chance += bool(alone.flagged)
    return {"group_based": based / trials, "chance_alone": chance / trials}


def s5c_few_groups() -> dict:
    rng = np.random.default_rng(7000)
    train_x, labels = make_groups(rng, 6, 80)
    train_s, test_s = standardise(train_x, make_groups(rng, 1, 30)[0])
    ref = fit_group_reference(train_s, labels, COLUMNS)
    threshold, kind, used = null_threshold(ref, 30)
    found = group_findings("t", "x", [GroupResult("g", check_group(ref, test_s), None)], 0)
    return {"kind": kind, "training_groups_big_enough": used, "message": found[0].rule if found else None}
