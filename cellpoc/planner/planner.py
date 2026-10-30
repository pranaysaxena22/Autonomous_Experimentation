"""The motion planner: turns a recipe, the setup and the cell layout into a motion plan for one trial (docs/platform_plan.md, section 6).

The plan is INTENT ONLY: what the robot is asked to do, as a timed list of actions from ten names. It never contains faults, outcomes or readings; those belong in the executed timeline an executor returns.
The planner follows the plan's rules, and checks its own output against them before returning it:
- every action follows the one before it with no gap; every action has a step; every wait has a reason naming the real process it stands for;
- the actions of a step add up to the setup's time for that step (within 1 second): a step's fixed actions are placed first and a named wait takes up the rest;
- friability steps are included only when the setup needs them (an objective on friability, or a required constraint on it);
- every pick has a matching place, nothing is picked twice, and the robot never holds something through a long wait.
It does not know how the plan will be run, or by whom. A recipe or a setup it cannot plan is refused with a plain message (PlanError); it never returns a plan that breaks a rule.
"""
from __future__ import annotations

import math

from .rules import STEPS, needs_friability, plan_problems

STATUS_ORDER = ("synthetic", "illustrative", "real", "validated")             # weakest to strongest: a plan takes the weakest status of its inputs
PICK_S = PLACE_S = SCAN_S = 60                                                # the defaults: how long the arm takes to pick, to place and to hold a vial to the scanner (the layout may set its own: robot.action_seconds)
READ_INSTRUMENT_S, READ_MASS_S = 60, 30
TARE_WAIT_S, POUR_INTO_DIE_S, PRESS_S, MOVE_HOME_S, TUMBLE_S, STIR_S = 120, 90, 60, 60, 300, 1800   # the dissolution test is a 30-minute stir
MIN_WAIT_S = 60                                                                # a named wait that fills the rest of a step is never shorter than this
TIME_NOTE = "start_s and duration_s are seconds since the start of the trial. Every action follows the one before it with no gap; waiting is an explicit wait action."


class PlanError(Exception):
    """A recipe, setup or layout the planner cannot make a plan from. The message says what to change."""


def weakest(*statuses: str) -> str:
    return min(statuses, key=STATUS_ORDER.index)


def action_seconds(layout: dict) -> tuple[int, int, int]:
    """(pick, place, scan) seconds: what the layout says the arm needs (robot.action_seconds), or 60 s each when it says nothing."""
    given = (layout.get("robot") or {}).get("action_seconds") or {}
    return int(given.get("pick", PICK_S)), int(given.get("place", PLACE_S)), int(given.get("scan", SCAN_S))


def pour_seconds(amount_g: float) -> int:
    """How long weighing out an amount takes: a minute plus a little per gram, in steps of 10 s, between 1 and 5 minutes."""
    return int(min(300, max(60, round((60 + 12 * amount_g) / 10) * 10)))


def _one(layout: dict, station_type: str, what: str) -> dict:
    found = [s for s in layout["stations"] if s["type"] == station_type]
    if not found:
        raise PlanError(f"The layout has no {what}. Add a station of type '{station_type}' to the layout.")
    return found[0]


def _recipe(setup: dict, layout: dict, recipe: dict, rescale: bool = False) -> tuple[dict, dict, list[dict], float]:
    """Check the recipe against the setup, fill in process settings it leaves out (the middle of their range), and return (full recipe, grams by ingredient, ingredients in shelf order, scale factor).
    With `rescale` the ingredient levels are first scaled to add up to 100% and the per-ingredient range check is skipped: for recipes from an engine whose ingredient levels are independent and do not add up
    to 100% (the proof of concept's), which the platform has to turn into a batch somehow. The factor is returned so the plan can say so."""
    ingredients = {i["id"]: i for i in setup["ingredients"]}
    missing = [i for i in ingredients if i not in recipe]
    if missing:
        raise PlanError("The recipe has no value for: " + ", ".join(ingredients[m]["label"] for m in missing) + ".")
    for i, spec in ingredients.items():
        v = recipe[i]
        if not rescale and not spec["min"] - 1e-9 <= v <= spec["max"] + 1e-9:
            raise PlanError(f"{spec['label']}: {v:g}% is outside the allowed {spec['min']:g} to {spec['max']:g}%.")
    factor = 1.0
    if rescale:
        raw = sum(recipe[i] for i in ingredients)
        sums_to = [r for r in setup["recipe_rules"] if r.get("rule") == "sum_to"]
        factor = (sums_to[0]["total"] if sums_to else 100.0) / raw
        recipe = {**recipe, **{i: recipe[i] * factor for i in ingredients}}
    total = sum(recipe[i] for i in ingredients)
    sums = [r for r in setup["recipe_rules"] if r.get("rule") == "sum_to"]
    if sums and abs(total - sums[0]["total"]) > sums[0]["tolerance"] + 1e-9:
        raise PlanError(f"The ingredients add up to {total:g}%, not {sums[0]['total']:g}% (allowed difference {sums[0]['tolerance']:g}).")
    full = {}
    slots = layout["bottle_shelf"]["slots"]
    shelf = [ingredients[s["ingredient_id"]] for s in slots if s["ingredient_id"] in ingredients]
    if len(shelf) != len(ingredients):
        raise PlanError("The layout has no bottle slot for: " + ", ".join(ingredients[i]["label"] for i in ingredients if i not in {s["id"] for s in shelf}) + ".")
    for spec in shelf:
        full[spec["id"]] = recipe[spec["id"]]
    for p in setup["process_factors"]:
        v = recipe.get(p["id"], (p["min"] + p["max"]) / 2)
        if not p["min"] - 1e-9 <= v <= p["max"] + 1e-9:
            raise PlanError(f"{p['label']}: {v:g} {p['unit']} is outside the allowed {p['min']:g} to {p['max']:g} {p['unit']}.")
        full[p["id"]] = v
    batch = setup["batch_size_g"]
    grams = {s["id"]: round(recipe[s["id"]] / 100.0 * batch, 2) for s in shelf}
    balance = next((s["id"] for s in shelf if s["role"] == "balance"), shelf[0]["id"])
    grams[balance] = round(grams[balance] + (round(batch, 2) - round(sum(grams.values()), 2)), 2)      # the rounded amounts must add up to the batch exactly
    return full, grams, shelf, factor


class _Builder:
    def __init__(self, setup: dict, layout: dict):
        self.setup, self.layout = setup, layout
        self.total = {s["name"]: s["time_min"] * 60 for s in setup["equipment"]["steps"]}
        if set(self.total) != set(STEPS):
            raise PlanError("The planner needs exactly these five steps in the setup: " + ", ".join(STEPS) + ". This setup has: " + ", ".join(self.total) + ".")
        ph = setup["equipment"]["phases"]
        self.act, self.sense, self.reason_s = set(ph["act"]), set(ph["sense"]), ph["reason_min"] * 60
        self.labels = {s["name"]: s["label"] for s in setup["equipment"]["steps"]}
        self.actions: list[dict] = []
        self.clock = 0
        self.step = ""
        self.step_start = 0

    def begin(self, step: str) -> None:
        self.step, self.step_start = step, self.clock

    def used(self) -> int:
        return self.clock - self.step_start

    def phase(self) -> str:
        if self.step in self.act:
            return "act"
        if self.step in self.sense:
            return "sense"
        return "reason" if self.used() < self.reason_s else "adapt"

    def add(self, kind: str, duration: int, caption: str, **fields) -> None:
        a = {"id": f"A{len(self.actions) + 1:03d}", "step": self.step, "phase": self.phase(), "type": kind, "start_s": self.clock, "duration_s": int(duration), **fields, "caption": caption}
        self.actions.append(a)
        self.clock += int(duration)

    def fill(self, reason: str, caption: str, what: str = "") -> None:
        """A named wait takes up whatever is left of the step."""
        left = self.total[self.step] - self.used()
        if left < MIN_WAIT_S:
            raise PlanError(f"The {self.labels[self.step]} step is too short: its actions need {self.used() + MIN_WAIT_S:g} s or more but the setup gives it {self.total[self.step]:g} s. "
                            f"Raise its time to at least {math.ceil((self.used() + MIN_WAIT_S) / 60):g} minutes{what}.")
        self.add("wait", left, caption, reason=reason)


def plan_trial(setup: dict, layout: dict, recipe: dict, trial: int, trial_start_minute: float, why: str, rescale: bool = False) -> dict:
    """The motion plan for one trial, as a dictionary in the platform's plan format (cellpoc/formats/schemas/plan.schema.json). See `_recipe` for `rescale`."""
    full, grams, shelf, factor = _recipe(setup, layout, recipe, rescale)
    if rescale and abs(factor - 1.0) > 1e-9:
        why = f"{why or ''} (The engine's ingredient levels did not add up to 100%, so they were scaled by {factor:.4f} to make a batch.)".strip()
    rack = _one(layout, "vial_rack_with_scanner", "rack with a barcode scanner")["id"]
    balance = _one(layout, "balance", "balance")["id"]
    press = _one(layout, "hand_press", "press")["id"]
    gauge = _one(layout, "hardness_gauge", "hardness gauge")["id"]
    vessel = _one(layout, "dissolution_vessel", "dissolution vessel")["id"]
    discard = _one(layout, "discard_bin", "discard bin")["id"]
    friable = needs_friability(setup)
    friabilator = _one(layout, "friability_tester", "friability tester")["id"] if friable else None
    holders = {h["tool"]: h["id"] for h in layout["tool_holders"]}
    for tool in ("punch", "rod"):
        if tool not in holders:
            raise PlanError(f"The layout has no holder for the {tool}.")
    objects = {o["type"]: o["id"] for o in layout["objects"] if o["type"] in ("vial", "tablet")}
    vial, tablet = objects["vial"], objects["tablet"]
    tool_object = {o["starts_at"]: o["id"] for o in layout["objects"] if o["type"] == "tool"}               # the object that sits in each tool holder
    punch, rod = tool_object.get(holders["punch"]), tool_object.get(holders["rod"])
    if not punch or not rod:
        raise PlanError("The layout has no punch or no stirring rod object in its tool holders.")
    bottle = {o["ingredient_id"]: o["id"] for o in layout["objects"] if o["type"] == "bottle"}
    slot = {s["ingredient_id"]: s["id"] for s in layout["bottle_shelf"]["slots"]}
    b = _Builder(setup, layout)
    pick_s, place_s, scan_s = action_seconds(layout)

    b.begin("dispense")
    b.add("pick", pick_s, "Pick the vial from the rack.", object=vial, **{"from": rack})
    b.add("scan", scan_s, "Hold the vial to the barcode scanner (read only).", object=vial, at=rack)
    b.add("place", place_s, "Place the vial on the balance.", object=vial, to=balance)
    b.add("wait", TARE_WAIT_S, "The balance tares and settles.", reason="balance tare and stabilisation before dosing")
    for spec in shelf:
        amount = grams[spec["id"]]
        if amount <= 0:
            continue
        name = spec["label"].lower()
        b.add("pick", pick_s, f"Pick the {name} bottle from its slot.", object=bottle[spec["id"]], **{"from": slot[spec["id"]]})
        b.add("pour", pour_seconds(amount), f"Pour the {name}, weighed on the balance.", object=bottle[spec["id"]], into=vial, at=balance, amount_g=amount)
        b.add("place", place_s, f"Return the {name} bottle to its slot.", object=bottle[spec["id"]], to=slot[spec["id"]])
    b.add("read", READ_MASS_S, "Check the total mass on the balance.", at=balance, quantity="mass_g")
    b.fill("powder settling and balance stabilisation after dosing", "Wait for the weighed powder to settle.")

    b.begin("mix")
    blend_s = int(round(full["blend_time_min"] * 60))
    b.add("pick", pick_s, "Pick up the vial to mix.", object=vial, **{"from": balance})
    b.add("shake", blend_s, "Shake the vial to mix (the blend time).", object=vial, style="mix")
    b.add("place", place_s, "Put the vial back on the balance.", object=vial, to=balance)
    b.fill("blend rest: de-aeration and static discharge before pressing", "Let the blend rest.", f" (the blend time alone is {blend_s / 60:g} minutes)")

    b.begin("press")
    b.add("pick", pick_s, "Pick up the vial.", object=vial, **{"from": balance})
    b.add("pour", POUR_INTO_DIE_S, "Pour the blend into the die.", object=vial, into=press, at=press, amount_g=float(setup["batch_size_g"]))
    b.add("place", place_s, "Drop the empty vial into the discard bin.", object=vial, to=discard)
    b.add("pick", pick_s, "Pick up the press punch.", object=punch, **{"from": holders["punch"]})
    b.add("press", PRESS_S, "Push the punch down to form the tablet.", object=punch, at=press, force_kn=float(full["compression_force_kn"]))
    b.add("place", place_s, "Return the punch to its holder.", object=punch, to=holders["punch"])
    b.fill("tablet elastic recovery and die cooling before handling", "Let the tablet relax and the die cool.")

    b.begin("test")
    b.add("pick", pick_s, "Pick the tablet out of the die.", object=tablet, **{"from": press})
    b.add("place", place_s, "Place the tablet on the hardness gauge.", object=tablet, to=gauge)
    b.add("read", READ_INSTRUMENT_S, "The gauge shows hardness. The robot only reads the number.", at=gauge, quantity="hardness_kp")
    b.add("pick", pick_s, "Pick the tablet up again.", object=tablet, **{"from": gauge})
    if friable:
        b.add("place", place_s, "Place the tablet in the friability tester.", object=tablet, to=friabilator)
        b.add("wait", TUMBLE_S, "The friability drum tumbles the tablet.", reason="friability drum tumbling the tablet for a fixed number of rotations")
        b.add("read", READ_INSTRUMENT_S, "The tester shows friability.", at=friabilator, quantity="friability_pct")
        b.add("pick", pick_s, "Pick the tablet out of the friability tester.", object=tablet, **{"from": friabilator})
    b.add("place", place_s, "Drop the tablet into the dissolution vessel.", object=tablet, to=vessel)
    b.add("pick", pick_s, "Pick up the stirring rod.", object=rod, **{"from": holders["rod"]})
    b.add("stir", STIR_S, "Stir the vessel for the 30-minute dissolution test.", object=rod, at=vessel)
    b.add("read", READ_INSTRUMENT_S, "The probe shows dissolution at 30 minutes.", at=vessel, quantity="dissolution_30min_pct")
    b.add("place", place_s, "Return the stirring rod to its holder.", object=rod, to=holders["rod"])
    b.fill("dissolution vessel drain and instrument stabilisation before cleaning", "Wait for the vessel to drain and the instruments to settle.")

    b.begin("clean")
    reason_s, adapt_s = b.reason_s, b.total["clean"] - b.reason_s
    if reason_s < MOVE_HOME_S + MIN_WAIT_S or adapt_s < MIN_WAIT_S:
        raise PlanError(f"The cleaning step cannot be planned: it is {b.total['clean']:g} s, of which {reason_s:g} s are for choosing the next recipe. "
                        f"It needs at least {MOVE_HOME_S + MIN_WAIT_S:g} s for that part and {MIN_WAIT_S:g} s after it.")
    b.add("move", MOVE_HOME_S, "Return to the home pose.", to="home")
    b.add("wait", reason_s - MOVE_HOME_S, "The decision engine reviews every result and chooses the next recipe.", reason="decision engine (software) reviews all results and chooses the next recipe")
    b.add("wait", adapt_s, "The cell is wiped down and the next recipe is loaded.", reason="wipe-down of the stations and loading of the next recipe")

    status = weakest(setup["project"]["data_status"], layout.get("data_status", "illustrative"))
    plan = {"format_version": 1,
            "label": f"{status.upper()} motion plan: INTENT ONLY (what the robot is asked to do). A full trial with no faults in it. What actually happened is in the executed timeline.",
            "data_status": status, "plan_id": f"T{trial:03d}", "trial": trial, "trial_start_minute": trial_start_minute, "layout_id": layout["layout_id"], "batch_size_g": float(setup["batch_size_g"]),
            "recipe": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in full.items()}, "why": why or "No reason was given.",
            "step_totals_s": {s: b.total[s] for s in STEPS}, "time_note": TIME_NOTE, "actions": b.actions}
    problems = plan_problems(plan, setup, layout)
    if problems:
        raise PlanError("The plan broke its own rules, so it was not returned: " + "; ".join(problems[:4]))
    return plan
