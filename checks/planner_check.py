"""Health check for the motion planner (Stage 6): does it generate plans that obey every rule, from any recipe the setup allows, and refuse the rest in plain words?

In plain words it checks that: a plan generated for the hand-authored example's recipe passes every plan rule and the JSON schema, has the same actions in the same order on the same objects and places as the hand-authored
plan, and its steps add up to the setup's step times exactly; 300 random recipes (inside every ingredient's range, adding up to 100%) all give valid plans with the right amounts (each ingredient's percentage of the batch, and the
amounts add up to the batch); a recipe outside a range, one that does not add up, one with an ingredient missing, a step too short for its actions, a blend longer than its step, a layout without a station, are each refused with a plain
message and never turned into a broken plan; the friability steps are in the plan exactly when the setup needs them (four setups); the plan is INTENT ONLY (no outcome, reading, fault or recovery in it); the same inputs give the same
plan; every rule can fail (twelve planted defects are each caught); the package's copy of each rule agrees with the one `check_formats.bat` uses; and the planner imports no other part. Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import copy
import json
import random
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.planner import PlanError, plan_problems, plan_trial, pour_seconds  # noqa: E402
from cellpoc.planner import rules  # noqa: E402
from checks import architecture, formats_check  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

EX = ROOT / "cellpoc" / "formats" / "examples"
SCHEMAS = ROOT / "cellpoc" / "formats" / "schemas"
SETUP = yaml.safe_load((EX / "setup_example.yaml").read_text(encoding="utf-8"))
LAYOUT = json.loads((EX / "cell_layout_example.json").read_text(encoding="utf-8"))
HAND_PLAN = json.loads((ROOT / "docs" / "platform_formats" / "motion_plan_example.json").read_text(encoding="utf-8"))
RECIPE = HAND_PLAN["recipe"]
SCHEMA = json.loads((SCHEMAS / "plan.schema.json").read_text(encoding="utf-8"))
STRUCTURE_KEYS = ("id", "step", "phase", "type", "object", "from", "to", "into", "at", "amount_g", "style", "force_kn", "quantity")


def plan(setup=SETUP, layout=LAYOUT, recipe=RECIPE, trial=8, start=1680, why="Chosen from 7 measured results (illustrative text)."):
    return plan_trial(setup, layout, recipe, trial, start, why)


def schema_errors(doc: dict) -> list[str]:
    return [e.message[:100] for e in Draft202012Validator(SCHEMA).iter_errors(doc)]


def random_recipe(rng: random.Random) -> dict:
    """A recipe inside every range that adds up to 100%, the balance ingredient (filler) taking the rest."""
    while True:
        r = {i["id"]: rng.uniform(i["min"], i["max"]) for i in SETUP["ingredients"] if i["role"] != "balance"}
        filler = 100.0 - sum(r.values())
        spec = next(i for i in SETUP["ingredients"] if i["role"] == "balance")
        if spec["min"] <= filler <= spec["max"]:
            r[spec["id"]] = filler
            r.update({p["id"]: rng.uniform(p["min"], p["max"]) for p in SETUP["process_factors"]})
            return {k: round(v, 3) for k, v in r.items()}


def raises(fn) -> str | None:
    try:
        fn()
    except PlanError as error:
        return str(error)
    return None


def generated_checks(cl: Checklist) -> None:
    p = plan()
    problems, errors = plan_problems(p, SETUP, LAYOUT), schema_errors(p)
    totals = {s: sum(a["duration_s"] for a in p["actions"] if a["step"] == s) for s in p["step_totals_s"]}
    want = {s["name"]: s["time_min"] * 60 for s in SETUP["equipment"]["steps"]}
    cl.record(not problems and not errors and totals == want and p["step_totals_s"] == want and p["plan_id"] == "T008" and p["trial"] == 8 and p["trial_start_minute"] == 1680,
              "A plan generated for the example recipe passes every plan rule and the JSON schema, and each step's actions add up to the setup's step time exactly (1,800 / 2,700 / 1,800 / 4,500 / 3,600 s)", f"{len(p['actions'])} actions; problems {problems[:2]}; schema {errors[:2]}; totals {totals}")
    mine = [tuple(a.get(k) for k in STRUCTURE_KEYS) for a in p["actions"]]
    hand = [tuple(a.get(k) for k in STRUCTURE_KEYS) for a in HAND_PLAN["actions"]]
    cl.record(mine == hand,
              "The generated plan has the same actions in the same order on the same objects, stations and slots, with the same amounts and force, as the hand-authored plan (only some durations differ, since the hand-authored ones were chosen by hand)", f"{len(mine)} against {len(hand)} actions")
    cl.record(all("origin" not in a and "outcome" not in a and "reading" not in a and "fault" not in a and "recovers" not in a for a in p["actions"]) and "faults" not in p and "ILLUSTRATIVE" in p["label"] and "INTENT ONLY" in p["label"],
              "The plan is INTENT ONLY: no action carries an outcome, a reading, a fault or a recovery, and the plan says it is illustrative and intent only", "")


def random_checks(cl: Checklist) -> None:
    rng = random.Random(20261013)
    bad, amounts_bad, n = [], [], 300
    for k in range(n):
        r = random_recipe(rng)
        p = plan(recipe=r, trial=k + 1, start=k * 210)
        issues = plan_problems(p, SETUP, LAYOUT) + schema_errors(p)
        pours = {a["object"]: a["amount_g"] for a in p["actions"] if a["type"] == "pour" and a.get("at") == "balance"}
        total = sum(pours.values())
        if abs(total - SETUP["batch_size_g"]) > 0.005:
            amounts_bad.append((k, total))
        for ing in SETUP["ingredients"]:
            b = f"bottle_{ing['id'].replace('_pct', '')}"
            if b in pours and abs(pours[b] - r[ing["id"]] / 100 * SETUP["batch_size_g"]) > (0.03 if ing["role"] == "balance" else 0.0051):       # the balancing filler takes the rounding residue (at most 5 x 0.005 g) so the amounts add up to the batch exactly
                amounts_bad.append((k, ing["id"]))
        if issues:
            bad.append((k, issues[:1]))
    cl.record(not bad and not amounts_bad, f"{n} random recipes (inside every range, adding up to 100%) all give valid plans, and the amounts poured are each ingredient's share of the batch (within 0.005 g; the balancing filler within 0.03 g, since it takes the rounding residue) and add up to the batch (within 0.005 g)", f"invalid {bad[:2]}; amounts {amounts_bad[:2]}")


def refusal_checks(cl: Checklist) -> None:
    def with_step(name, minutes):
        s = copy.deepcopy(SETUP)
        next(x for x in s["equipment"]["steps"] if x["name"] == name)["time_min"] = minutes
        return s

    no_press = copy.deepcopy(LAYOUT)
    no_press["stations"] = [s for s in no_press["stations"] if s["type"] != "hand_press"]
    cases = {
        "an ingredient outside its range": raises(lambda: plan(recipe={**RECIPE, "binder_pct": 9.0, "filler_pct": 71.1})),
        "ingredients that do not add up": raises(lambda: plan(recipe={**RECIPE, "filler_pct": 60.0})),
        "an ingredient missing": raises(lambda: plan(recipe={k: v for k, v in RECIPE.items() if k != "drug_pct"})),
        "a process setting outside its range": raises(lambda: plan(recipe={**RECIPE, "compression_force_kn": 99})),
        "a dispense step too short": raises(lambda: plan(setup=with_step("dispense", 10))),
        "a blend longer than its mix step": raises(lambda: plan(setup=with_step("mix", 20))),
        "a layout without a press": raises(lambda: plan(layout=no_press)),
        "a cleaning step shorter than the thinking time": raises(lambda: plan(setup=with_step("clean", 25))),
    }
    plain = all(m and not re.search(r"Traceback|KeyError|NoneType|\{|\}", m) and len(m) > 25 for m in cases.values())
    cl.record(plain, "Eight things the planner cannot plan (an ingredient out of range, not adding up, missing, a process setting out of range, a step too short for its actions, a blend longer than its step, a layout without a press, cleaning shorter than the thinking time) are each refused with a plain message, never turned into a broken plan",
              "; ".join(f"{k}: {(v or 'NOT REFUSED')[:60]}" for k, v in list(cases.items())[:3]))


def friability_checks(cl: Checklist) -> None:
    def variant(objective: bool, required: bool | None):
        s = copy.deepcopy(SETUP)
        if not objective:
            s["targets"]["objectives"] = [o for o in s["targets"]["objectives"] if o["quantity"] != "friability_pct"]
        c = next(c for c in s["targets"]["constraints"] if c["response"] == "friability_pct")
        if required is None:
            s["targets"]["constraints"].remove(c)
        else:
            c["required"] = required
        return s
    results = {}
    for name, (obj, req, expect) in {"objective, not required": (True, False, True), "no objective, not required": (False, False, False), "no objective, required": (False, True, True), "no objective, no constraint": (False, None, False)}.items():
        s = variant(obj, req)
        p = plan(setup=s)
        has = any(a["type"] == "read" and a.get("quantity") == "friability_pct" for a in p["actions"]) and any("friabilator" in (a.get("to"), a.get("from"), a.get("at")) for a in p["actions"])
        results[name] = (has == expect and not plan_problems(p, s, LAYOUT) and not schema_errors(p) and rules.needs_friability(s) == formats_check.needs_friability(s) == expect)
    cl.record(all(results.values()), "Friability steps are in the plan exactly when the setup needs them (an objective on friability, or a required constraint on it) and nowhere else, in four setups, and the package's rule agrees with the format check's", str(results))


def determinism_checks(cl: Checklist) -> None:
    a, b = plan(), plan()
    c = plan(trial=9, start=1890)
    pours = [pour_seconds(x) for x in (0.0, 0.12, 1.0, 2.82, 15.16, 40.0)]
    cl.record(a == b and c["plan_id"] == "T009" and c["trial_start_minute"] == 1890 and pours == sorted(pours) and min(pours) == 60 and max(pours) == 300 and all(x % 10 == 0 for x in pours),
              "The same inputs give the identical plan, the trial number and start minute are carried into it, and weighing time rises with the amount between one and five minutes, in steps of 10 s", f"weighing times {pours}")


def planted_checks(cl: Checklist) -> None:
    base = plan()
    def mutate(fn):
        p = copy.deepcopy(base)
        fn(p)
        return plan_problems(p, SETUP, LAYOUT)
    cases = {
        "a gap between two actions": lambda p: p["actions"][5].__setitem__("start_s", p["actions"][5]["start_s"] + 10),
        "two actions overlapping": lambda p: p["actions"][5].__setitem__("start_s", p["actions"][5]["start_s"] - 10),
        "a step that does not add up": lambda p: p["actions"][3].__setitem__("duration_s", p["actions"][3]["duration_s"] + 30),
        "a wait with no reason": lambda p: p["actions"][3].pop("reason"),
        "a wait whose reason is just 'waiting for filler'": lambda p: p["actions"][3].__setitem__("reason", "waiting for filler time"),
        "a pick of an object that is somewhere else": lambda p: p["actions"][0].__setitem__("from", "balance"),
        "a pour while holding nothing": lambda p: p["actions"].pop(4),
        "an action type that is not one of the ten": lambda p: p["actions"][1].__setitem__("type", "teleport"),
        "a repeated id": lambda p: p["actions"][2].__setitem__("id", "A001"),
        "steps out of order": lambda p: p["actions"].insert(0, {**p["actions"][-1], "id": "A900", "start_s": 0}),
        "friability measured though not needed": lambda p: None,
        "a phase that disagrees with the setup": lambda p: p["actions"][0].__setitem__("phase", "sense"),
    }
    caught = {k: bool(mutate(fn)) for k, fn in cases.items() if k != "friability measured though not needed"}
    s = copy.deepcopy(SETUP)
    s["targets"]["objectives"] = [o for o in s["targets"]["objectives"] if o["quantity"] != "friability_pct"]
    caught["friability measured though not needed"] = bool(plan_problems(base, s, LAYOUT))
    cl.record(all(caught.values()), "Self-test: every plan rule can fail (a gap, an overlap, a step that does not add up, a wait with no reason, a vague reason, a wrong pick, a missing action, an unknown action type, a repeated id, steps out of order, friability measured though not needed, a wrong phase)",
              str({k: v for k, v in caught.items() if not v}) or f"{len(caught)} of {len(caught)} caught")


def agreement_checks(cl: Checklist) -> None:
    """The package's rules against the format check's copies, on the hand-authored plan and on planted defects: the same answers."""
    ex = copy.deepcopy(HAND_PLAN)
    defects = [ex, copy.deepcopy(ex), copy.deepcopy(ex), copy.deepcopy(ex)]
    defects[1]["actions"][5]["start_s"] += 10
    defects[2]["actions"][3].pop("reason")
    defects[3]["actions"][0]["from"] = "balance"
    same = True
    for d in defects:
        a = d["actions"]
        same &= rules.flow_problems(a, LAYOUT) == formats_check.flow_problems(a, LAYOUT)
        same &= rules.timing_problems(a, "start_s", "duration_s") == formats_check.timing_problems(a, "start_s", "duration_s")
        same &= rules.step_sum_problems(a, SETUP, "duration_s") == formats_check.step_sum_problems(a, SETUP, "duration_s")
        same &= rules.phase_problems(a, SETUP, "start_s") == formats_check.phase_problems(a, SETUP, "start_s")
        same &= rules.friability_problems(SETUP, a) == formats_check.friability_problems(SETUP, a)
        same &= [x for x in rules.wait_reason_problems([x for x in a if "reason" in x or x["type"] != "wait"])] == [x for x in formats_check.wait_reason_problems([x for x in a if "reason" in x or x["type"] != "wait"])]
    cl.record(same, "The package's plan rules give exactly the same answers as the format check's own copies, on the hand-authored plan and on three planted defects (so the two can never drift apart unseen)", "")


def action_time_checks(cl: Checklist) -> None:
    """(2026-10-16) The arm's pick, place and scan times come from the layout (robot.action_seconds); without it they are the old 60 s."""
    fast = copy.deepcopy(LAYOUT)
    fast["robot"]["action_seconds"] = {"pick": 30, "place": 20, "scan": 10}
    default_plan, fast_plan = plan(), plan(layout=fast)
    by_type = lambda p, kind: {a["duration_s"] for a in p["actions"] if a["type"] == kind}
    problems = plan_problems(fast_plan, SETUP, fast) + schema_errors(fast_plan)
    totals_same = fast_plan["step_totals_s"] == default_plan["step_totals_s"]
    cl.record(by_type(default_plan, "pick") == {60} and by_type(default_plan, "place") == {60} and by_type(default_plan, "scan") == {60}
              and by_type(fast_plan, "pick") == {30} and by_type(fast_plan, "place") == {20} and by_type(fast_plan, "scan") == {10} and not problems and totals_same,
              "The arm's pick, place and scan times come from the layout (30, 20 and 10 s in a layout that says so, 60 s each in one that says nothing); the faster plan is still a valid plan and every step still adds up to the setup's step time",
              f"fast plan problems {problems[:2]}")
    bad = copy.deepcopy(LAYOUT)
    bad["robot"]["action_seconds"] = {"pick": 2}
    layout_schema = json.loads((SCHEMAS / "layout.schema.json").read_text(encoding="utf-8"))
    refused = [e.message[:80] for e in Draft202012Validator(layout_schema).iter_errors(bad)]
    cl.record(bool(refused) and not list(Draft202012Validator(layout_schema).iter_errors(fast)), "The layout format refuses an absurd arm time (a 2 s pick) and accepts a sensible one", f"refused: {refused[:1]}")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 6 (planner): does it generate plans that obey every rule, and refuse the rest in plain words?")
    before = project_files()
    generated_checks(cl)
    random_checks(cl)
    refusal_checks(cl)
    friability_checks(cl)
    determinism_checks(cl)
    planted_checks(cl)
    agreement_checks(cl)
    action_time_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
