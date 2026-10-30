"""The Python stand-in executor: runs a motion plan in simulated time and returns the executed timeline (docs/platform_formats/executed_timeline_example.json is the hand-authored known answer for it).

What it does, and every rule it follows, so nothing is a surprise:
- Every planned action runs at the planned duration, one after another, with no gaps; instrument readings come from the injected reading provider (it never sees how they are produced). The scan reads the vial's barcode,
  a pour at the balance reads the mass it delivered, and the balance read after dosing reads the total.
- A FAULT (from the setup: scripted or random) hits one named action. The action fails part-way (a pour after 28% of its time, any other action after half of it, in steps of 5 s); a failed pour has delivered 36% of its amount.
- RECOVERY actions are added, tagged origin 'recovery' and linked to the action they recover: tap and shake the jammed bottle (a pour only; the setup's tap-and-shake seconds), put back whatever the robot holds, wait out the purge
  (the setup's purge minutes, with a reason that names the process), pick the object up again, and retry (a pour retries the rest of its amount; any other action retries in full). The fault costs exactly what these actions cost.
- If the single retry works, every later planned action runs, pushed later by the delay. If it fails, the candidate is SKIPPED: the robot puts down what it holds, no further planned action of the trial runs, and, when the setup says
  so (clean_after_skip), the cleaning step still runs; the trial has no result.
- The verdict is the setup's targets applied to the readings (a required target with no reading gives 'No result').
It refuses a plan that breaks the plan rules, that uses an action it does not support, or a fault that names an action the plan does not have.
"""
from __future__ import annotations

import re

from ..instruments import Instruments, SimulatedBalance, SimulatedBarcodeScanner, classify, format_from_layout
from ..planner.planner import action_seconds
from ..planner.rules import ACTION_TYPES, STEPS, plan_problems, timeline_problems
from .interface import ExecutorRefusal, Fault, ReadingProvider

FAIL_FRACTION_POUR, FAIL_FRACTION_OTHER, DELIVERED_BEFORE_JAM = 0.28, 0.5, 0.36
WRONG_VIAL_WORDS = re.compile(r"wrong|mismatch|other vial|different vial", re.IGNORECASE)          # a scripted fault at the scan whose cause says this is a WRONG vial; any other cause is an unreadable label
COPY_KEYS = ("object", "from", "to", "into", "at", "amount_g", "style", "force_kn", "quantity", "reason")
TIME_NOTE = ("actual_start_s and actual_duration_s are seconds since the start of the trial, as it happened. origin 'planned' = an action from the plan; origin 'recovery' = added by the executor to deal with the fault.")
DECIMALS = {"hardness_kp": 1, "dissolution_30min_pct": 1, "friability_pct": 2}


def _to(x: float, base: int) -> int:
    return int(round(x / base) * base)


def _verdict(setup: dict, values: dict) -> str:
    """The setup's targets applied to the readings; a required target with no reading gives 'No result'."""
    for c in setup["targets"]["constraints"]:
        if not c.get("required", True):
            continue
        v = values.get(c["response"])
        if v is None:
            return "No result"
        if (c["goal"] == "at_least" and v < c["value"]) or (c["goal"] == "at_most" and v > c["value"]) or (c["goal"] == "between" and not c["low"] <= v <= c["high"]):
            return "Not good"
    return "Good"


class _Run:
    def __init__(self, plan: dict, setup: dict, layout: dict, fault: Fault | None, readings: ReadingProvider, clean_after_skip: bool, plan_file: str | None, name: str, instruments: Instruments | None = None):
        self.plan, self.setup, self.layout, self.fault, self.readings, self.clean_after_skip, self.plan_file, self.name = plan, setup, layout, fault, readings, clean_after_skip, plan_file, name
        self.label_format = format_from_layout(layout)
        self.expected_label = self.label_format.label(plan["trial"])
        barcode_settings = (layout.get("instruments") or {}).get("barcode") or {}
        self.pick_s, self.place_s, _ = action_seconds(layout)                    # the arm's pick and place times: the layout's, or the default 60 s
        self.scan_retries, self.rotate_s = int(barcode_settings.get("retries", 1)), int(barcode_settings.get("rotate_s", 5))          # from the layout's optional instruments block
        if instruments is not None:
            if fault is not None and fault.action == "scan":
                raise ExecutorRefusal("A fault at the scan can only be played with the simulated scanner; real instruments make their own mistakes.")
            self.scanner, self.balance = instruments.scanner, instruments.balance
        else:
            self.scanner, self.balance = self._simulated_scanner(), SimulatedBalance()
        self.t = 0
        self.out: list[dict] = []
        self.rids: list[str] = []
        self.held: tuple[str, str] | None = None                      # (object, where it was picked up)
        self.values: dict = {}                                        # readings as shown (rounded)
        self.raw: dict = {}                                           # readings as the instrument gave them: the verdict is judged on these
        self.fault_record: dict | None = None
        self.skipped = False
        self.ingredient_of = {o["id"]: o["ingredient_id"] for o in layout["objects"] if o.get("ingredient_id")}
        self.label_of = {i["id"]: i["label"].lower() for i in setup["ingredients"]}
        self.purge_s = int(round(setup["faults"]["purge_min"] * 60))
        self.tap_s = int(setup["faults"]["recovery"]["tap_shake_s"])

    # ------------------------------------------------------------------ building blocks
    def _track(self, e: dict) -> None:
        if e["type"] == "pick" and e["outcome"] == "ok":
            self.held = (e["object"], e["from"])
        elif e["type"] == "place" and e["outcome"] == "ok":
            self.held = None

    def _reading(self, a: dict) -> dict | None:
        t = a["type"]
        if t == "pour":
            if a.get("at") == "balance":                                           # weighing out an ingredient: the balance sees it arrive
                self.balance.add(a["amount_g"])
            return {"quantity": "mass_g", "expected": a["amount_g"], "value": a["amount_g"]}
        if t == "read":
            q = a["quantity"]
            if q == "mass_g":
                return {"quantity": q, "value": self.balance.read().grams}
            v = self.readings.reading(q)
            self.raw[q] = v
            self.values[q] = None if v is None else round(v, DECIMALS.get(q, 2))
            return {"quantity": q, "value": "not available" if v is None else self.values[q]}
        return None

    def _planned(self, a: dict, duration: int, outcome: str = "ok", reading: dict | None = None, caption: str | None = None, fault: dict | None = None) -> None:
        e = {"id": a["id"], "origin": "planned", "step": a["step"], "phase": a["phase"], "type": a["type"]}
        e.update({k: a[k] for k in COPY_KEYS if k in a})
        e.update(planned_start_s=a["start_s"], planned_duration_s=a["duration_s"], actual_start_s=self.t, actual_duration_s=duration, outcome=outcome)
        if reading is not None:
            e["reading"] = reading
        e["caption"] = caption or a["caption"]
        if fault is not None:
            e["fault"] = fault
        self.out.append(e)
        self._track(e)
        self.t += duration

    def _recovery(self, a: dict, kind: str, duration: int, caption: str, outcome: str = "ok", reading: dict | None = None, fault: dict | None = None, **fields) -> None:
        rid = f"R{len(self.rids) + 1:03d}"
        self.rids.append(rid)
        e = {"id": rid, "origin": "recovery", "step": a["step"], "phase": a["phase"], "type": kind, **fields, "recovers": a["id"], "actual_start_s": self.t, "actual_duration_s": duration, "outcome": outcome}
        if reading is not None:
            e["reading"] = reading
        e["caption"] = caption
        if fault is not None:
            e["fault"] = fault
        self.out.append(e)
        self._track(e)
        self.t += duration

    # ------------------------------------------------------------------ the fault and its recovery
    def _matches(self, a: dict) -> bool:
        f = self.fault
        if f is None or a["step"] != f.step or a["type"] != f.action:
            return False
        return f.ingredient is None or self.ingredient_of.get(a.get("object", "")) == f.ingredient

    def _faulted(self, a: dict) -> bool:
        """Run the failed action and its recovery. Returns True if the retry worked."""
        f, d = self.fault, a["duration_s"]
        kind = a["type"]
        fail_s = max(5, _to((FAIL_FRACTION_POUR if kind == "pour" else FAIL_FRACTION_OTHER) * d, 5)) if d >= 10 else max(1, d // 2)
        fail_s = min(fail_s, max(1, d - 5)) if d > 5 else fail_s
        delivered = round(DELIVERED_BEFORE_JAM * a["amount_g"], 2) if kind == "pour" else None
        detail = (f"Powder stopped flowing. The balance reads {delivered:g} g, expected {a['amount_g']:g} g." if kind == "pour" else f"The {kind} stopped before it finished.")
        reading = ({"quantity": "mass_g", "expected": a["amount_g"], "value": delivered} if kind == "pour" else None)
        if kind == "pour":
            self.balance.add(delivered)
        self._planned(a, fail_s, "failed", reading, f"{a['caption']} FAULT: {f.cause} after {fail_s} s.", {"cause": f.cause, "where": f.where, "detail": detail})
        holding = self.held
        if kind == "pour" and holding:
            self._recovery(a, "shake", self.tap_s, "Tap and shake the jammed bottle to clear it.", object=holding[0], style="tap")
        if holding:
            self._recovery(a, "place", self.place_s, f"Put the {'bottle' if kind == 'pour' else holding[0]} back in its slot before the purge." if kind == "pour" else f"Put the {holding[0]} back before the purge.", object=holding[0], to=holding[1])
        noun = "dispenser" if kind == "pour" else "press" if kind == "press" else "station"
        self._recovery(a, "wait", self.purge_s, f"Purge and reset the {noun} ({self.setup['faults']['purge_min']:g} minutes).",
                       reason=f"{noun} purge and reset after the {f.cause} ({self.setup['faults']['purge_min']:g} minutes, from the setup)")
        if holding:
            self._recovery(a, "pick", self.pick_s, f"Pick the {self.label_of.get(self.ingredient_of.get(holding[0], ''), holding[0])} bottle up again." if kind == "pour" else f"Pick the {holding[0]} up again.", object=holding[0], **{"from": holding[1]})
        ok = f.retry_succeeds
        if kind == "pour":
            rest = round(a["amount_g"] - delivered, 2)
            dur = max(60, _to(d * rest / a["amount_g"], 10))
            name = self.label_of.get(self.ingredient_of.get(a["object"], ""), "powder")
            fields = {"object": a["object"], "into": a["into"], "at": a["at"], "amount_g": rest}
            if ok:
                self.balance.add(rest)
                self._recovery(a, "pour", dur, f"Retry: pour the rest of the {name}.", reading={"quantity": "mass_g", "expected": rest, "value": rest}, **fields)
            else:
                self._recovery(a, "pour", dur, f"Retry: pour the rest of the {name}. FAULT: the retry also failed.", "failed", {"quantity": "mass_g", "expected": rest, "value": 0.0},
                               {"cause": f.cause, "where": f.where, "detail": "The retry also failed."}, **fields)
        else:
            fields = {k: a[k] for k in COPY_KEYS if k in a and k != "reason"}
            if kind == "wait":
                fields["reason"] = a["reason"]
            if ok:
                self._recovery(a, kind, d, f"Retry: {a['caption']}", reading=self._reading(a) if kind in ("scan", "read") else None, **fields)
            else:
                self._recovery(a, kind, d, f"Retry: {a['caption']} FAULT: the retry also failed.", "failed", None, {"cause": f.cause, "where": f.where, "detail": "The retry also failed."}, **fields)
        self.fault_record = {"action_id": a["id"], "cause": f.cause, "where": f.where, "recovered": ok, "recovery_action_ids": list(self.rids)}
        if not ok and self.held:
            self._recovery(a, "place", self.place_s, f"Put the {self.held[0]} back before stopping this trial.", object=self.held[0], to=self.held[1])
            self.fault_record["recovery_action_ids"] = list(self.rids)                 # the fault block lists every recovery action, the final put-down included
        return ok

    def _faulted_step(self) -> str | None:
        """The step the fault was in: the scripted fault's, or (a fault found by the instruments themselves, such as a different vial) the step recorded when it happened."""
        return self.fault.step if self.fault is not None else (self.fault_record or {}).get("where", {}).get("step")

    # ------------------------------------------------------------------ the barcode scan and its recovery
    def _simulated_scanner(self) -> SimulatedBarcodeScanner:
        """The scanner of a run with no real device: it reads this trial's vial, unless the scripted fault is at the scan (then it misreads the way the fault's cause says, and the retry works or not as the fault says)."""
        f, trial = self.fault, self.plan["trial"]
        other = self.label_format.label(trial - 1 if trial > 1 else trial + 1)
        if f is not None and f.action == "scan":
            return SimulatedBarcodeScanner(self.expected_label, "wrong_vial" if WRONG_VIAL_WORDS.search(f.cause) else "unreadable", f.retry_succeeds, other)
        return SimulatedBarcodeScanner(self.expected_label, None, True, other)

    def _scan(self, a: dict) -> bool:
        """The scan action: read the label and compare it with the vial this trial should have. Right: the planned action. Unreadable: turn the vial and read again (as many times as the layout allows). A DIFFERENT vial: stop, put it back, the candidate is skipped.
        The same decision is taken whether the scanner is the simulated one or a real one. Returns False when the trial must stop."""
        d, expected = a["duration_s"], self.expected_label
        result = self.scanner.read()
        verdict = classify(result, expected)
        if verdict == "ok":
            self._planned(a, d, reading={"quantity": "barcode", "value": result.text})
            return True
        scripted = self.fault if (self.fault is not None and self.fault.action == "scan") else None
        cause = scripted.cause if scripted else ("wrong vial scanned" if verdict == "wrong_vial" else "barcode unreadable")
        where = scripted.where if scripted else {"step": a["step"], "action": "scan"}
        fail_s = max(5, _to(FAIL_FRACTION_OTHER * d, 5)) if d >= 10 else max(1, d // 2)
        fail_s = min(fail_s, max(1, d - 5)) if d > 5 else fail_s
        seen = result.text or result.raw or "nothing"
        detail = (f"The scanner read {seen}, but this trial's vial is {expected}: a different vial is in the gripper." if verdict == "wrong_vial" else "The scanner could not read the label on the vial.")
        self._planned(a, fail_s, "failed", {"quantity": "barcode", "value": seen if verdict == "wrong_vial" else "not read", "expected": expected}, f"{a['caption']} FAULT: {cause} after {fail_s} s.", {"cause": cause, "where": where, "detail": detail})
        fields = {k: a[k] for k in COPY_KEYS if k in a and k != "reason"}
        recovered = False
        if verdict == "unreadable":
            for _ in range(self.scan_retries):
                self._recovery(a, "wait", self.rotate_s, "Turn the vial a quarter turn so the scanner can see the label.", reason="turn the vial a quarter turn so the scanner can refocus on the label")
                again = self.scanner.read()
                verdict = classify(again, expected)
                if verdict == "ok":
                    self._recovery(a, "scan", d, f"Retry: {a['caption']}", reading={"quantity": "barcode", "value": again.text}, **fields)
                    recovered = True
                    break
                seen = again.text or again.raw or "nothing"
                self._recovery(a, "scan", d, f"Retry: {a['caption']} FAULT: the vial still could not be read.", "failed",
                               {"quantity": "barcode", "value": seen if verdict == "wrong_vial" else "not read", "expected": expected}, {"cause": cause, "where": where, "detail": "The retry also failed."}, **fields)
                if verdict == "wrong_vial":
                    cause = "wrong vial scanned"
                    break
        if not recovered and self.held:
            self._recovery(a, "place", self.place_s, f"Put the {self.held[0]} back before stopping this trial.", object=self.held[0], to=self.held[1])
        self.fault_record = {"action_id": a["id"], "cause": cause, "where": where, "recovered": recovered, "recovery_action_ids": list(self.rids)}
        return recovered

    # ------------------------------------------------------------------ the run
    def run(self) -> dict:
        target = next((a for a in self.plan["actions"] if self._matches(a)), None)
        if self.fault is not None and target is None:
            raise ExecutorRefusal(f"The fault names a '{self.fault.action}' in the {self.fault.step} step" + (f" for {self.fault.ingredient}" if self.fault.ingredient else "")
                                  + ", but the plan has no such action, so there is nothing to fail.")
        for a in self.plan["actions"]:
            if self.skipped and not (a["step"] == "clean" and self.clean_after_skip and self._faulted_step() != "clean"):
                continue
            if a["type"] == "scan":
                if not self._scan(a):
                    self.skipped = True
                continue
            if a is target:
                if not self._faulted(a):
                    self.skipped = True
                continue
            self._planned(a, a["duration_s"], reading=self._reading(a))
        actual = {s: sum(e["actual_duration_s"] for e in self.out if e["step"] == s) for s in STEPS}
        outcome = "skipped" if self.skipped else ("completed_after_recovery" if self.fault_record else "completed")
        result = ({"dissolution_30min_pct": None, "hardness_kp": None, "friability_pct": None, "verdict": "No result"} if self.skipped else
                  {"dissolution_30min_pct": self.values.get("dissolution_30min_pct"), "hardness_kp": self.values.get("hardness_kp"), "friability_pct": self.values.get("friability_pct"), "verdict": _verdict(self.setup, self.raw)})
        pid = self.plan["plan_id"]
        status = self.plan["data_status"]
        return {"format_version": 1, "label": f"{status.upper()} executed timeline: what the executor returned for plan {pid}. The same actions as the plan, with actual times, outcomes, and any fault with its recovery actions.",
                "data_status": status, "executed_id": f"{pid}-executed", "plan_id": pid, "plan_file": self.plan_file or f"{pid}.json", "trial": self.plan["trial"], "trial_start_minute": self.plan["trial_start_minute"],
                "layout_id": self.plan["layout_id"], "executor": self.name, "outcome": outcome, "faults": [self.fault_record] if self.fault_record else [],
                "step_totals_s": {"planned": dict(self.plan["step_totals_s"]), "actual": actual}, "result": result, "time_note": TIME_NOTE, "actions": self.out}


class PythonStandInExecutor:
    name = "python_stand_in"
    supported_actions = frozenset(ACTION_TYPES)

    def check(self, plan: dict, layout: dict, setup: dict | None = None) -> list[str]:
        """Why this executor would refuse the plan (empty = it can run it)."""
        problems = []
        unsupported = sorted({a["type"] for a in plan["actions"]} - self.supported_actions)
        if unsupported:
            problems.append(f"The {self.name} executor cannot run these actions: {', '.join(unsupported)}. It supports: {', '.join(sorted(self.supported_actions))}.")
        return problems

    def execute(self, plan: dict, setup: dict, layout: dict, fault: Fault | None, readings: ReadingProvider, clean_after_skip: bool = True, plan_file: str | None = None, instruments: Instruments | None = None) -> dict:
        problems = self.check(plan, layout) + plan_problems(plan, setup, layout)
        if problems:
            raise ExecutorRefusal("This plan was refused: " + "; ".join(problems[:4]))
        timeline = _Run(plan, setup, layout, fault, readings, clean_after_skip, plan_file, self.name, instruments).run()
        broken = timeline_problems(timeline, setup, layout)
        if broken:
            raise ExecutorRefusal("The executed timeline broke its own rules, so it was not returned: " + "; ".join(broken[:4]))
        return timeline
