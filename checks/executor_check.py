"""Health check for the cell executor (Stage 6): does the Python stand-in run a plan and return what truly happened, including a fault, its recovery and a skipped candidate?

In plain words it checks that: run on the hand-authored example plan with the hand-authored jam, it reproduces the hand-authored executed timeline action by action (ids, origins, types, outcomes, actual start and duration,
instrument readings, the fault block, the recovery ids, the result) and the dispense takes 5,635 s where the plan said 1,800; the fault's cost equals an independent recount from the plan and the setup (for a jam at each
ingredient's pour, in 40 random recipes, and for a press jam), so the fault costs exactly what its recovery actions cost; with no fault every action runs at its planned time; a retry that fails skips the candidate (no result,
nothing planned after the failure runs, the robot puts down what it holds, cleaning still runs when the setup says so and not when it says not); every timeline obeys the timeline rules and the JSON schema; the readings come only
from the injected provider (change them and only the numbers change, never the times; with none, the verdict is 'No result'); the verdict applies the setup's targets; a plan with an action the executor does not support, a plan
that breaks the plan rules and a fault on an action the plan does not have are each refused in plain words; scripted faults win, random faults are repeatable for a trial whatever the order, and their frequency matches the chance;
the executor imports nothing but the planner. Nothing is written into the project and nothing uses the network.
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

from cellpoc.executor import ExecutorRefusal, Fault, NoReadings, PythonStandInExecutor, fault_for_trial  # noqa: E402
from cellpoc.planner import plan_trial, timeline_problems  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402
from checks.planner_check import random_recipe  # noqa: E402

EX = ROOT / "cellpoc" / "formats" / "examples"
SETUP = yaml.safe_load((EX / "setup_example.yaml").read_text(encoding="utf-8"))
LAYOUT = json.loads((EX / "cell_layout_example.json").read_text(encoding="utf-8"))
HAND_PLAN = json.loads((ROOT / "docs" / "platform_formats" / "motion_plan_example.json").read_text(encoding="utf-8"))
HAND_RUN = json.loads((ROOT / "docs" / "platform_formats" / "executed_timeline_example.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "cellpoc" / "formats" / "schemas" / "executed_timeline.schema.json").read_text(encoding="utf-8"))
EXECUTOR = PythonStandInExecutor()
JAM = Fault("dispense", "pour", "binder bottle jam", True, "binder_pct")
KEYS = ("id", "origin", "type", "outcome", "actual_start_s", "actual_duration_s", "reading", "fault", "recovers", "step", "phase")


class Readings:
    def __init__(self, **v):
        self.v = {"hardness_kp": 7.9, "friability_pct": 0.31, "dissolution_30min_pct": 88.2, **v}

    def reading(self, quantity):
        return self.v.get(quantity)


def schema_errors(doc) -> list[str]:
    return [e.message[:100] for e in Draft202012Validator(SCHEMA).iter_errors(doc)]


def known_answer_checks(cl: Checklist) -> None:
    t = EXECUTOR.execute(HAND_PLAN, SETUP, LAYOUT, JAM, Readings(), plan_file="motion_plan_example.json")
    mine = [{k: a.get(k) for k in KEYS} for a in t["actions"]]
    hand = [{k: a.get(k) for k in KEYS} for a in HAND_RUN["actions"]]
    cl.record(mine == hand and t["faults"] == HAND_RUN["faults"] and t["result"] == HAND_RUN["result"] and t["outcome"] == HAND_RUN["outcome"] and t["step_totals_s"] == HAND_RUN["step_totals_s"]
              and t["step_totals_s"]["actual"]["dispense"] == 5635 and t["step_totals_s"]["planned"]["dispense"] == 1800 and t["plan_file"] == HAND_RUN["plan_file"],
              "Run on the hand-authored plan with the hand-authored binder jam, the executor reproduces the hand-authored executed timeline action by action (ids, origins, types, outcomes, actual start and duration, readings, the fault block, recovery ids), its result, and the step totals: dispense 1,800 s planned, 5,635 s actual",
              f"{len(mine)} actions compared; the only differences are in captions and wording")


def recount_checks(cl: Checklist) -> None:
    """The fault's cost from first principles: what the recovery actions cost, minus the part of the failed action that never ran."""
    rng = random.Random(7)
    f = SETUP["faults"]
    purge, tap = f["purge_min"] * 60, f["recovery"]["tap_shake_s"]
    wrong = []
    for k in range(40):
        r = random_recipe(rng)
        plan = plan_trial(SETUP, LAYOUT, r, k + 1, 0, "test")
        for ingredient in ("drug_pct", "binder_pct", "lubricant_pct"):
            pour = next(a for a in plan["actions"] if a["type"] == "pour" and a.get("object") == f"bottle_{ingredient.replace('_pct', '')}")
            d, amount = pour["duration_s"], pour["amount_g"]
            fail = max(5, int(round(0.28 * d / 5) * 5))
            delivered = round(0.36 * amount, 2)
            retry = max(60, int(round(d * round(amount - delivered, 2) / amount / 10) * 10))
            extra = fail + tap + 60 + purge + 60 + retry - d                             # failed part + tap/shake + put back + purge + pick up + retry, instead of the whole pour
            t = EXECUTOR.execute(plan, SETUP, LAYOUT, Fault("dispense", "pour", "jam", True, ingredient), Readings())
            got = t["step_totals_s"]["actual"]["dispense"] - t["step_totals_s"]["planned"]["dispense"]
            end = t["actions"][-1]["actual_start_s"] + t["actions"][-1]["actual_duration_s"]
            if got != extra or end != sum(plan["step_totals_s"].values()) + extra or abs(t["actions"][-1]["actual_start_s"] - (plan["actions"][-1]["start_s"] + extra)) > 0:
                wrong.append((k, ingredient, got, extra))
    plan = plan_trial(SETUP, LAYOUT, random_recipe(rng), 41, 0, "test")
    press_jam = EXECUTOR.execute(plan, SETUP, LAYOUT, Fault("press", "press", "press jam", True), Readings())
    pr = next(a for a in plan["actions"] if a["type"] == "press")
    d = pr["duration_s"]
    fail = max(5, int(round(0.5 * d / 5) * 5))
    extra = fail + 60 + purge + 60 + d - d                                                 # failed part + put the punch back + purge + pick it up + retry the press in full
    got = press_jam["step_totals_s"]["actual"]["press"] - press_jam["step_totals_s"]["planned"]["press"]
    cl.record(not wrong and got == extra,
              "The fault's cost equals an independent recount (the failed part, tap and shake, put back, purge, pick up, retry, minus the part of the action that never ran): for a jam at three ingredients' pours in 40 random recipes (120 timelines), and for a press jam, and every later action is pushed later by exactly that amount",
              f"wrong {wrong[:2]}; press jam extra {got} against {extra}")


def clean_run_checks(cl: Checklist) -> None:
    bad = []
    rng = random.Random(11)
    for k in range(30):
        plan = plan_trial(SETUP, LAYOUT, random_recipe(rng), k + 1, k * 210, "test")
        t = EXECUTOR.execute(plan, SETUP, LAYOUT, None, Readings())
        ok = (t["outcome"] == "completed" and t["faults"] == [] and all(a["actual_start_s"] == a["planned_start_s"] and a["actual_duration_s"] == a["planned_duration_s"] and a["outcome"] == "ok" and a["origin"] == "planned" for a in t["actions"])
              and t["step_totals_s"]["planned"] == t["step_totals_s"]["actual"] and t["result"]["verdict"] in ("Good", "Not good") and not schema_errors(t) and not timeline_problems(t, SETUP, LAYOUT))
        mass = next(a for a in t["actions"] if a["type"] == "read" and a.get("quantity") == "mass_g")
        if not ok or abs(mass["reading"]["value"] - SETUP["batch_size_g"]) > 0.005:
            bad.append(k)
    cl.record(not bad, "With no fault, in 30 random recipes, every action runs at its planned time with outcome ok, the outcome is 'completed', no fault is recorded, the timeline obeys the timeline rules and the schema, and the balance reads the whole batch (20 g)", f"wrong in {bad[:3]}")


def skip_checks(cl: Checklist) -> None:
    plan = plan_trial(SETUP, LAYOUT, HAND_PLAN["recipe"], 19, 0, "test")
    fail = Fault("dispense", "pour", "binder bottle jam", False, "binder_pct")
    with_clean = EXECUTOR.execute(plan, SETUP, LAYOUT, fail, Readings(), clean_after_skip=True)
    without = EXECUTOR.execute(plan, SETUP, LAYOUT, fail, Readings(), clean_after_skip=False)
    steps = lambda t: [a["step"] for a in t["actions"]]
    sk = with_clean
    res_ok = sk["result"] == {"dissolution_30min_pct": None, "hardness_kp": None, "friability_pct": None, "verdict": "No result"}
    cleaning_ok = steps(with_clean)[-1] == "clean" and set(steps(with_clean)) == {"dispense", "clean"} and with_clean["step_totals_s"]["actual"]["clean"] == plan["step_totals_s"]["clean"] and with_clean["step_totals_s"]["actual"]["mix"] == 0
    none_after = "clean" not in steps(without) and set(steps(without)) == {"dispense"}
    placed_back = [a for a in sk["actions"] if a["origin"] == "recovery"][-1]["type"] == "place" and sk["actions"][-1]["type"] == "wait"
    failed_retry = [a for a in sk["actions"] if a["origin"] == "recovery" and a["outcome"] == "failed"]
    cl.record(sk["outcome"] == "skipped" and res_ok and cleaning_ok and none_after and placed_back and len(failed_retry) == 1 and sk["faults"][0]["recovered"] is False and not schema_errors(sk) and not schema_errors(without)
              and not timeline_problems(sk, SETUP, LAYOUT) and not timeline_problems(without, SETUP, LAYOUT),
              "A retry that fails SKIPS the candidate: outcome 'skipped', no result, the failed retry recorded, the robot puts the bottle back, nothing planned after the failure runs except the cleaning step when the setup says so (and not even that when it says not), and both timelines obey the timeline rules and the schema",
              f"steps with cleaning {sorted(set(steps(with_clean)))}; without {sorted(set(steps(without)))}")


def schema_checks(cl: Checklist) -> None:
    rng = random.Random(23)
    bad = []
    faults = [None, Fault("dispense", "pour", "jam", True, "filler_pct"), Fault("press", "press", "press jam", True), Fault("test", "stir", "rod jam", True), Fault("mix", "shake", "shaker fault", False),
              Fault("dispense", "scan", "scanner fault", True), Fault("test", "read", "gauge fault", True, None), Fault("mix", "wait", "x fault", True)]
    for k, fault in enumerate(faults * 4):
        plan = plan_trial(SETUP, LAYOUT, random_recipe(rng), k + 1, 0, "test")
        t = EXECUTOR.execute(plan, SETUP, LAYOUT, fault, Readings())
        rec = [a for a in t["actions"] if a["origin"] == "recovery"]
        ids = {a["id"] for a in t["actions"] if a["origin"] == "planned"}
        ok = (not schema_errors(t) and not timeline_problems(t, SETUP, LAYOUT) and all(a["recovers"] in ids for a in rec) and [a["id"] for a in rec] == [f"R{n:03d}" for n in range(1, len(rec) + 1)]
              and (not fault or t["faults"][0]["recovery_action_ids"][:len(rec)] == [a["id"] for a in rec]) and all(a["phase"] == next(p["phase"] for p in t["actions"] if p["id"] == a["recovers"]) for a in rec))
        if not ok:
            bad.append((k, fault and fault.action))
    cl.record(not bad, "Timelines for 32 trials with a fault at a pour, a press, a stir, a shake, a scan, a read or a wait (retry working or failing) all obey the timeline rules and the schema; recovery ids run R001, R002, and each names an action of the plan and carries its phase", f"wrong {bad[:3]}")


def readings_checks(cl: Checklist) -> None:
    plan = plan_trial(SETUP, LAYOUT, HAND_PLAN["recipe"], 8, 1680, "test")
    a = EXECUTOR.execute(plan, SETUP, LAYOUT, JAM, Readings())
    b = EXECUTOR.execute(plan, SETUP, LAYOUT, JAM, Readings(hardness_kp=5.0, dissolution_30min_pct=70.0))
    c = EXECUTOR.execute(plan, SETUP, LAYOUT, JAM, NoReadings())
    times = lambda t: [(x["id"], x["actual_start_s"], x["actual_duration_s"], x["outcome"]) for x in t["actions"]]
    verdicts = {"good": EXECUTOR.execute(plan, SETUP, LAYOUT, None, Readings())["result"]["verdict"], "soft": b["result"]["verdict"], "none": c["result"]["verdict"],
                "friability_ignored": EXECUTOR.execute(plan, SETUP, LAYOUT, None, Readings(friability_pct=9.9))["result"]["verdict"]}
    cl.record(times(a) == times(b) == times(c) and a["result"]["hardness_kp"] == 7.9 and b["result"]["hardness_kp"] == 5.0 and verdicts == {"good": "Good", "soft": "Not good", "none": "No result", "friability_ignored": "Good"},
              "The readings come only from the injected provider: other numbers change only the numbers and the verdict (never a time), no numbers give 'No result', and the verdict applies the setup's targets (a hardness of 5 kP or a dissolution of 70% is 'Not good'; friability is not required in this setup, so 9.9% does not matter)", str(verdicts))


def refusal_checks(cl: Checklist) -> None:
    plan = plan_trial(SETUP, LAYOUT, HAND_PLAN["recipe"], 8, 0, "test")

    class NoStir(PythonStandInExecutor):
        name = "no_stir"
        supported_actions = PythonStandInExecutor.supported_actions - {"stir"}

    broken = copy.deepcopy(plan)
    broken["actions"][5]["start_s"] += 10
    nothing = copy.deepcopy(plan)
    def refused(fn):
        try:
            fn()
        except ExecutorRefusal as error:
            return str(error)
        return None
    msgs = {"unsupported action": refused(lambda: NoStir().execute(plan, SETUP, LAYOUT, None, Readings())),
            "a plan that breaks the rules": refused(lambda: EXECUTOR.execute(broken, SETUP, LAYOUT, None, Readings())),
            "a fault on an action the plan does not have": refused(lambda: EXECUTOR.execute(nothing, SETUP, LAYOUT, Fault("press", "scan", "x", True), Readings()))}
    ok = all(m and len(m) > 30 and not re.search(r"Traceback|KeyError|\{|\}", m) for m in msgs.values()) and "stir" in msgs["unsupported action"] and "gap" in msgs["a plan that breaks the rules"]
    cl.record(ok, "A plan with an action the executor does not support, a plan that breaks the plan rules, and a fault on an action the plan does not have are each refused with a plain message that names the problem, and nothing is run", "; ".join(f"{k}: {(v or 'NOT REFUSED')[:55]}" for k, v in msgs.items()))


def fault_selection_checks(cl: Checklist) -> None:
    s = copy.deepcopy(SETUP)
    s["faults"]["random"] = [{"where": {"step": "press", "action": "press"}, "cause": "press jam", "chance_per_trial": 0.5, "retry_succeeds_chance": 0.7}]
    scripted = fault_for_trial(s, 8, 2026)
    plain = [fault_for_trial(s, n, 2026) for n in range(1, 2001) if n not in (8, 19)]
    rate = sum(1 for f in plain if f) / len(plain)
    retry_rate = sum(1 for f in plain if f and f.retry_succeeds) / max(1, sum(1 for f in plain if f))
    again = [fault_for_trial(s, n, 2026) for n in range(1, 60)]
    shuffled = {n: fault_for_trial(s, n, 2026) for n in random.Random(1).sample(range(1, 60), 59)}
    none = copy.deepcopy(SETUP)
    none["faults"]["random"] = [{**s["faults"]["random"][0], "chance_per_trial": 0.0}]
    other = [fault_for_trial(s, n, 2027) for n in range(1, 60)]
    cl.record(scripted and scripted.source == "scripted" and scripted.ingredient == "binder_pct" and scripted.retry_succeeds is True and fault_for_trial(s, 19, 2026).retry_succeeds is False
              and abs(rate - 0.5) < 0.04 and abs(retry_rate - 0.7) < 0.05 and all(shuffled[n] == again[n - 1] for n in shuffled) and all(fault_for_trial(none, n, 2026) is None for n in range(1, 400) if n not in (8, 19)) and other != again,
              "A scripted fault wins on its trial (trial 8 and 19 of the example); random faults happen as often as their chance (50% of 2,000 trials within 4 points, a retry that works 70% within 5), give the same answer for a trial whatever order trials are asked in, never happen at a chance of 0, and change with the seed",
              f"random rate {rate:.3f}, retry rate {retry_rate:.3f}")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 6 (executor): does the stand-in run a plan and return what truly happened, faults and skips included?")
    before = project_files()
    known_answer_checks(cl)
    recount_checks(cl)
    clean_run_checks(cl)
    skip_checks(cl)
    schema_checks(cl)
    readings_checks(cl)
    refusal_checks(cl)
    fault_selection_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
