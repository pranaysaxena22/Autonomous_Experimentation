"""Health check for the seed guard: does the code itself refuse a sealed acceptance seed, so seed-blindness does not depend on anyone remembering it?

In plain words it checks that: a seed inside either sealed block (the live 7,000,101 to 7,000,140 or the retired 7,000,001 to 7,000,040), at the first, the last and the middle of each, is refused at once, with a
plain-words message, by every place a development seed can enter (the development lab, its random-recipe draw, the comparison's campaign, strategy builder and runner, the engine check's own world builder, and the three strategy classes themselves: the governed engine, the ungoverned engine and the random-recipe strategy, built directly);
an ordinary development seed, a seed one step outside either block, and a seed in the reserved comparison block do NOT fire; a seed given as a numpy integer or a float is refused too; the wrapper that the
official acceptance runner uses is refused by the development lab, is the only way a LIVE seed gets through code that allows it (the engines allow it, so the runner can drive them), never lets a retired seed through, and a plain integer in the live block never gets
through; the guard's blocks equal the seal manifest's; the wrapper's name appears nowhere but the guard and the acceptance folder; and nothing is written
into the project. It never creates the sealed lab or uses any of its seeds as anything but text and numbers.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.comparison import dev_comparison as dc  # noqa: E402
from cellpoc.contracts.seeds import LIVE_BLOCK, RETIRED_BLOCK, AcceptanceSeed, SealedSeedError, in_sealed_block, refuse_sealed_seed  # noqa: E402
from cellpoc.virtual_lab import dev_oracle  # noqa: E402
from cellpoc.virtual_lab.dev_lab import SCENARIOS, DevLab  # noqa: E402
from cellpoc.decision_engine.baselines import RandomRecipes, UngovernedStrategy  # noqa: E402
from cellpoc.decision_engine.governed import GovernedStrategy  # noqa: E402
from cellpoc.decision_engine.recalibrated import RecalibratedStrategy  # noqa: E402
from cellpoc.virtual_lab.dev_lab import DESIGN_SPACE, FILLER_RANGE, INGREDIENTS, cleaned_history, target_specs  # noqa: E402
from checks import engine_check  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

PLANTED = (7_000_001, 7_000_020, 7_000_040, 7_000_101, 7_000_120, 7_000_140)
ORDINARY = (10_101, 10_901, 10_200, 10_239, 1, 0, 7_000_000, 7_000_041, 7_000_100, 7_000_141, 70_000_101)
N_ENTRY_POINTS = 10                                                            # how many places a development seed can enter (entry_points below)
ALLOWED_WRAPPER_FILES = ("cellpoc/contracts/seeds.py", "checks/seedguard_check.py")
SKIP = {".venv", ".git", "runs", "__pycache__", "acceptance"}


def engine_args(seed, history=None):
    return (target_specs(), history if history is not None else None, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)


def entry_points(seed):
    """Every place a development seed can enter, as (name, a function that takes the seed)."""
    brief = engine_check.brief_of({})
    return [("the development lab", lambda: DevLab(SCENARIOS["baseline"], seed)), ("the random-recipe draw", lambda: dev_oracle.random_recipes(3, seed)),
            ("the comparison's strategy builder", lambda: dc.build_strategy("random", "baseline", brief, seed)), ("the comparison's campaign", lambda: dc.run_campaign("baseline", "random", seed, brief, None, 2)),
            ("the comparison's runner", lambda: dc.run_all({"baseline": brief.to_json()}, None, 1, (seed,), ("baseline",), ("random",))),
            ("the engine check's world builder", lambda: engine_check.world("baseline", engine_seed=seed, n=60)),
            ("the governed engine, built directly", lambda: GovernedStrategy(brief, *engine_args(seed))), ("the ungoverned engine, built directly", lambda: UngovernedStrategy(brief, *engine_args(seed))),
            ("the random-recipe strategy, built directly", lambda: RandomRecipes(DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)),
            ("the recalibrated engine (the platform engine), built directly", lambda: RecalibratedStrategy(brief, *engine_args(seed)))]


def refuses(fn) -> str | None:
    try:
        fn()
    except SealedSeedError as error:
        return str(error)
    return None


def planted_checks(cl: Checklist) -> None:
    missed, messages = [], []
    for seed in PLANTED:
        for name, fn in entry_points(seed):
            m = refuses(fn)
            if m is None:
                missed.append((seed, name))
            else:
                messages.append(m)
    plain = all(str(s) in m and "sealed acceptance block" in m and "official acceptance runner" in m and "development seed" in m for s, m in zip([s for s in PLANTED for _ in range(N_ENTRY_POINTS)], messages))
    cl.record(not missed and len(messages) == len(PLANTED) * N_ENTRY_POINTS and plain,
              "A planted sealed seed (the first, a middle and the last of each block) is refused at once by every place a development seed can enter, with a plain message that names the seed, the block, the official acceptance runner and what to use instead",
              f"{len(messages)} refusals of {len(PLANTED) * N_ENTRY_POINTS}; missed {missed[:2]}")
    live_msg = refuses(lambda: DevLab(SCENARIOS["baseline"], 7_000_101))
    old_msg = refuses(lambda: DevLab(SCENARIOS["baseline"], 7_000_001))
    cl.record(live_msg and old_msg and "live block" in live_msg and "retired block" in old_msg, "The message says which block the seed is in (the live acceptance block, or the retired one)", "")


def ordinary_checks(cl: Checklist) -> None:
    fired = []
    for seed in ORDINARY:
        for name, fn in entry_points(seed)[:2]:                                    # the cheap, pure entry points: the lab and the random draw
            if refuses(fn) is not None:
                fired.append((seed, name))
    brief = engine_check.brief_of({})
    ok = all(not in_sealed_block(s) for s in ORDINARY) and all(in_sealed_block(s) for s in PLANTED) and not fired
    works = dc.run_campaign("baseline", "random", 10_905, brief, None, 2).good is not None and len(DevLab(SCENARIOS["baseline"], 10_101).history(40)) > 0
    cl.record(ok and works, "An ordinary development seed, a seed one step outside either block (7,000,000, 7,000,041, 7,000,100, 7,000,141), a seed in the reserved comparison block (10200 to 10239) and a much larger number "
              "that merely contains digits of a sealed seed do NOT fire, and the lab and a campaign still work", f"{len(ORDINARY)} ordinary seeds; fired: {fired}")
    forms = [np.int64(7_000_101), np.int32(7_000_001), 7_000_101.0, True and 7_000_140]
    cl.record(all(refuses(lambda s=s: DevLab(SCENARIOS["baseline"], s)) for s in forms) and not refuses(lambda: DevLab(SCENARIOS["baseline"], np.int64(10_101))),
              "A sealed seed is refused however it is written (a plain integer, a numpy integer, a number with a decimal point), and an ordinary seed written those ways is not", "")


def wrapper_checks(cl: Checklist) -> None:
    live, retired = AcceptanceSeed(7_000_101), AcceptanceSeed(7_000_001)
    results = {
        "lab refuses the wrapper": refuses(lambda: DevLab(SCENARIOS["baseline"], live)) is not None,
        "allowed: live wrapper passes": refuses(lambda: refuse_sealed_seed(live, "the runner's engine", allow_acceptance=True)) is None,
        "retired wrapper refused even when allowed": refuses(lambda: refuse_sealed_seed(retired, "the runner's engine", allow_acceptance=True)) is not None,
        "plain live int refused even when allowed": refuses(lambda: refuse_sealed_seed(7_000_101, "the runner's engine", allow_acceptance=True)) is not None,
        "live wrapper refused when not allowed": refuses(lambda: refuse_sealed_seed(live, "something else")) is not None,
        "ordinary seed passes everywhere": refuses(lambda: refuse_sealed_seed(10_101, "anything", allow_acceptance=True)) is None and refuses(lambda: refuse_sealed_seed(10_101, "anything")) is None}
    cl.record(all(results.values()), "The wrapper the official acceptance runner uses: the development lab refuses it, a live seed gets through code that allows it ONLY in the wrapper, a retired seed never gets through, and a plain integer in the live block never does",
              str({k: v for k, v in results.items() if not v}) or "all six cases")


def engine_checks(cl: Checklist) -> None:
    """The three strategy classes themselves (added after 4-4): a sealed seed never gets into one except as the runner's wrapper in the live block, and an ordinary seed still builds one."""
    brief = engine_check.brief_of({})
    history = cleaned_history(DevLab(SCENARIOS["baseline"], 10_101), 60)
    builders = {"governed": lambda s: GovernedStrategy(brief, *engine_args(s, history)), "ungoverned": lambda s: UngovernedStrategy(brief, *engine_args(s, history)),
                "random": lambda s: RandomRecipes(DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), s), "recalibrated": lambda s: RecalibratedStrategy(brief, *engine_args(s, history))}

    def builds(build, seed) -> bool:
        try:
            build(seed)
        except Exception:                                                  # noqa: BLE001  (any failure at all means it did not build)
            return False
        return True

    problems = []
    for name, build in builders.items():
        if not builds(build, 10_930):
            problems.append(f"{name}: an ordinary development seed no longer builds")
        if not builds(build, AcceptanceSeed(7_000_120)):
            problems.append(f"{name}: the live wrapper does not get through")
        if refuses(lambda: build(AcceptanceSeed(7_000_020))) is None:
            problems.append(f"{name}: a retired wrapper got through")
        if refuses(lambda: build(7_000_120)) is None:
            problems.append(f"{name}: a plain integer in the live block got through")
    cl.record(not problems, "The strategy classes (governed, ungoverned, random and the recalibrated platform engine) refuse a sealed seed themselves: an ordinary development seed still builds each of them, the official runner's live wrapper gets through, a retired wrapper and a plain integer in the live block never do",
              "; ".join(problems[:3]) or "4 classes x 4 cases")
    cl.record(len(entry_points(0)) == N_ENTRY_POINTS, "The list of places a development seed can enter, counted by the planted-seed check, is complete and agrees with the code (a place added later must be added there too)", f"{len(entry_points(0))} listed, {N_ENTRY_POINTS} expected")


def drift_checks(cl: Checklist) -> None:
    manifest = json.loads((ROOT / "acceptance" / "SEAL.json").read_text(encoding="utf-8"))
    cl.record(LIVE_BLOCK == (manifest["sealed_seed_first"], manifest["sealed_seed_last"]) and RETIRED_BLOCK == (manifest["retired_seed_first"], manifest["retired_seed_last"]),
              "The guard's two blocks equal the seal manifest's (and check_seal.bat checks the lab file against that manifest), so the guard cannot drift from the seal", f"live {LIVE_BLOCK}, retired {RETIRED_BLOCK}")
    stray = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if SKIP & set(p.relative_to(ROOT).parts) or rel in ALLOWED_WRAPPER_FILES:
            continue
        if "AcceptanceSeed" in p.read_text(encoding="utf-8", errors="replace"):
            stray.append(rel)
    cl.record(not stray, "The wrapper's name appears nowhere but the guard itself and the acceptance folder: no development, comparison, tool or check code can quietly make an acceptance seed", f"found in: {stray[:3]}")


def main() -> int:
    cl = Checklist("THE SEED GUARD: does the code itself refuse a sealed acceptance seed?")
    before = project_files()
    planted_checks(cl)
    ordinary_checks(cl)
    wrapper_checks(cl)
    engine_checks(cl)
    drift_checks(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
