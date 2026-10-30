"""The rules a motion plan (and an executed timeline) must obey, as plain functions that return a list of plain-English problems (empty = fine).

They are the same rules `check_formats.bat` applies to the hand-authored examples, ported here so that the planner, the executor and the health checks all use one implementation that lives in the package
(a check proves the two copies agree). Every function works on plain dictionaries read from the JSON files; nothing here imports another part of the platform.
"""
from __future__ import annotations

import re

STEPS = ("dispense", "mix", "press", "test", "clean")
ACTION_TYPES = ("move", "pick", "place", "pour", "shake", "press", "stir", "scan", "read", "wait")
VAGUE_WORDS = {"wait", "waiting", "idle", "filler", "padding", "pause", "delay", "pending", "tbd", "todo"}


def flow_problems(actions: list[dict], layout: dict) -> list[str]:
    """Walk the actions in order: what the robot holds, where objects are, what each action needs."""
    locs = ({s["id"] for s in layout["stations"]} | {s["id"] for s in layout["bottle_shelf"]["slots"]}
            | {h["id"] for h in layout["tool_holders"]} | {"home"})
    reads = {s["id"]: s["instrument"]["reads"] for s in layout["stations"] if "instrument" in s}
    where = {o["id"]: o["starts_at"] for o in layout["objects"]}
    created = {o["id"]: o["created_by"] for o in layout["objects"] if o.get("created_by")}
    held, problems = None, []
    for a in actions:
        t, i = a["type"], a["id"]
        dur = a.get("duration_s", a.get("actual_duration_s", 0))
        for k in ("from", "to", "at"):
            if k in a and a[k] not in locs:
                problems.append(f"{i}: '{a[k]}' is not a location in the layout")
        if "object" in a and a["object"] not in where:
            problems.append(f"{i}: '{a['object']}' is not an object in the layout")
            continue
        if t == "pick":
            if held:
                problems.append(f"{i}: picks {a['object']} while already holding {held}")
            elif where[a["object"]] != a["from"]:
                problems.append(f"{i}: {a['object']} is at {where[a['object']]}, not at {a['from']}")
            else:
                held, where[a["object"]] = a["object"], None
        elif t == "place":
            if held != a["object"]:
                problems.append(f"{i}: places {a['object']} but the robot holds {held}")
            else:
                where[held], held = a["to"], None
        elif t in ("pour", "shake", "scan", "press", "stir"):
            if held != a["object"]:
                problems.append(f"{i} ({t}): the robot is not holding {a['object']} (it holds {held})")
            if t == "scan" and reads.get(a.get("at")) != "barcode":
                problems.append(f"{i}: there is no scanner at {a.get('at')}")
            if t == "pour":
                into = a["into"]
                if into in where and where[into] != a["at"]:
                    problems.append(f"{i}: pours into {into}, which is at {where[into]}, not at {a['at']}")
                if into not in where and into != a["at"]:
                    problems.append(f"{i}: pours into {into} but pours at {a['at']}")
            if t == "press":
                for obj, station in created.items():
                    if station == a["at"]:
                        where[obj] = station
        elif t == "read":
            if reads.get(a["at"]) != a["quantity"]:
                problems.append(f"{i}: {a['at']} does not read {a['quantity']}")
        elif t == "wait" and held and dur > 300:
            problems.append(f"{i}: the robot holds {held} through a {dur:g} s wait")
    if held:
        problems.append(f"the robot is still holding {held} at the end")
    return problems


def timing_problems(actions: list[dict], start: str, dur: str) -> list[str]:
    """Every action follows the one before it with no gap and no overlap; the first starts at 0; the steps come in order."""
    problems = []
    if actions and abs(actions[0][start]) > 1e-6:
        problems.append(f"{actions[0]['id']}: the first action does not start at 0")
    for a, b in zip(actions, actions[1:]):
        gap = b[start] - (a[start] + a[dur])
        if abs(gap) > 1e-6:
            problems.append(f"{a['id']} to {b['id']}: {'gap' if gap > 0 else 'overlap'} of {abs(gap):g} s")
    order = [STEPS.index(a["step"]) for a in actions]
    if order != sorted(order):
        problems.append("steps are not in the order dispense, mix, press, test, clean")
    return problems


def step_sum_problems(actions: list[dict], setup: dict, dur: str, planned_only: bool = False) -> list[str]:
    """A step's actions add up to the setup's step time, within 1 second."""
    want = {s["name"]: s["time_min"] * 60 for s in setup["equipment"]["steps"]}
    got = {s: sum(a[dur] for a in actions if a["step"] == s and (not planned_only or a["origin"] == "planned")) for s in want}
    return [f"step {s}: actions add up to {got[s]:g} s, the setup says {want[s]:g} s" for s in want if abs(got[s] - want[s]) > 1.0]


def phase_problems(actions: list[dict], setup: dict, start_key: str) -> list[str]:
    """Each action carries the phase the setup implies: act, sense, or (in the last step) reason and then adapt."""
    ph = setup["equipment"]["phases"]
    problems, first = [], {}
    for a in actions:
        first.setdefault(a["step"], a[start_key])
        if a["step"] in ph["act"]:
            want = "act"
        elif a["step"] in ph["sense"]:
            want = "sense"
        else:
            want = "reason" if a[start_key] - first[a["step"]] < ph["reason_min"] * 60 else "adapt"
        if a["phase"] != want:
            problems.append(f"{a['id']}: phase '{a['phase']}' but the setup implies '{want}'")
    return problems


def wait_reason_problems(actions: list[dict]) -> list[str]:
    """Every wait must name the real process it stands for (not just 'wait' or 'filler')."""
    problems = []
    for a in actions:
        if a["type"] != "wait":
            continue
        reason = a.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 20 or set(re.findall(r"[a-z]+", reason.lower())) & VAGUE_WORDS:
            problems.append(f"{a['id']}: the wait's reason {reason!r} does not name a real process")
    return problems


def needs_friability(setup: dict) -> bool:
    """The planner includes friability steps only when the setup needs them: an objective on friability, or a required constraint on it."""
    return (any(o["quantity"] == "friability_pct" for o in setup["targets"]["objectives"])
            or any(c["response"] == "friability_pct" and c.get("required", True) for c in setup["targets"]["constraints"]))


def friability_problems(setup: dict, actions: list[dict]) -> list[str]:
    measured = any(a["type"] == "read" and a.get("quantity") == "friability_pct" for a in actions)
    used_station = any("friabilator" in (a.get("from"), a.get("to"), a.get("at")) for a in actions)
    problems = []
    if needs_friability(setup) and not measured:
        problems.append("the setup needs friability but the plan never reads it")
    if measured and not needs_friability(setup):
        problems.append("the plan measures friability although nothing in the setup needs it")
    if measured != used_station:
        problems.append("the friability tester station and the friability reading do not go together")
    return problems


def unknown_action_problems(actions: list[dict]) -> list[str]:
    ids = [a["id"] for a in actions]
    problems = [f"{a['id']}: '{a['type']}' is not one of the ten action types" for a in actions if a["type"] not in ACTION_TYPES]
    problems += [f"{i}: the id is used more than once" for i in sorted({x for x in ids if ids.count(x) > 1})]
    problems += [f"{a['id']}: the step '{a['step']}' is not one of the five steps" for a in actions if a["step"] not in STEPS]
    return problems


def plan_problems(plan: dict, setup: dict, layout: dict) -> list[str]:
    """Every rule a motion plan must obey, in the order a person would ask them."""
    actions = plan["actions"]
    problems = unknown_action_problems(actions)
    if problems:
        return problems
    problems += timing_problems(actions, "start_s", "duration_s")
    problems += step_sum_problems(actions, setup, "duration_s")
    problems += phase_problems(actions, setup, "start_s")
    problems += wait_reason_problems(actions)
    problems += friability_problems(setup, actions)
    problems += flow_problems(actions, layout)
    return problems


def timeline_problems(timeline: dict, setup: dict, layout: dict) -> list[str]:
    """The rules for an executed timeline: contiguous in actual time, one flow of objects, every wait with a reason, friability only when needed."""
    actions = timeline["actions"]
    problems = unknown_action_problems(actions)
    if problems:
        return problems
    problems += timing_problems(actions, "actual_start_s", "actual_duration_s")
    problems += wait_reason_problems(actions)
    problems += flow_problems(actions, layout)
    return problems
