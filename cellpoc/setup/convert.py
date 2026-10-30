"""Converts a setup into the settings the proof of concept (PoC) understands, as a PREVIEW only.

Nothing here writes a file. The result is a dictionary (and its text form) that the setup app shows on the Review screen
and that the health check feeds to the PoC's own settings checker. config/settings.yaml is never touched.

The PoC is smaller than a setup: it models exactly five named ingredients, one dissolution target and one hardness target,
and has no process settings, context factors or random faults. The converter says plainly what it could not carry over
(notes), and refuses (a blocking note) when the setup asks for something the PoC cannot represent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from .problems import Problem, has_errors

POC_INGREDIENTS = {"drug_pct": "drug", "filler_pct": "filler", "binder_pct": "binder",
                   "disintegrant_pct": "disintegrant", "lubricant_pct": "lubricant"}
POC_STEP_NAMES = {"mix": "blend"}          # the setup says 'mix', the PoC says 'blend' (docs/naming.md)
DISSOLUTION, HARDNESS = "dissolution_30min_pct", "hardness_kp"
PREVIEW_HEADER = ("# PREVIEW ONLY - illustrative values. Built from the setup for the proof of concept.\n"
                  "# It is not saved anywhere and never replaces config/settings.yaml.\n")


@dataclass(frozen=True)
class Note:
    level: str       # "blocking" = the PoC cannot use this setup; "info" = something left out
    text: str

    @property
    def label(self) -> str:
        return "Cannot convert" if self.level == "blocking" else "Left out"


@dataclass
class Conversion:
    settings: dict | None
    notes: list[Note] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.settings is not None

    def yaml_text(self) -> str:
        if self.settings is None:
            return ""
        return PREVIEW_HEADER + yaml.safe_dump(self.settings, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)


def _rename(names: list[str]) -> list[str]:
    return [POC_STEP_NAMES.get(n, n) for n in names]


def _alert(cause: str, trial: int, retry_succeeds: bool) -> str:
    outcome = "purged and retried successfully" if retry_succeeds else "retry failed, candidate skipped"
    return f"{cause[:1].upper() + cause[1:]} on trial {trial} - {outcome}"


def _blocking(setup: dict) -> list[Note]:
    """What the PoC cannot represent."""
    notes: list[Note] = []
    ids = [i["id"] for i in setup["ingredients"]]
    if set(ids) != set(POC_INGREDIENTS) or len(ids) != len(POC_INGREDIENTS):
        notes.append(Note("blocking", "The proof of concept models exactly these five ingredients: " + ", ".join(POC_INGREDIENTS)
                          + ". This setup has: " + ", ".join(ids) + "."))
    constraints = {c["response"]: c for c in setup["targets"]["constraints"]}
    dissolution, hardness = constraints.get(DISSOLUTION), constraints.get(HARDNESS)
    if not dissolution or dissolution["goal"] != "at_least" or not isinstance(dissolution.get("margin_scale"), (int, float)):
        notes.append(Note("blocking", f"The proof of concept needs an 'at least' target for {DISSOLUTION} with a margin scale."))
    elif dissolution["value"] > 100:
        notes.append(Note("blocking", f"Dissolution of at least {dissolution['value']:g}% cannot be reached (the proof of concept caps it at 100%)."))
    if not hardness or hardness["goal"] != "between":
        notes.append(Note("blocking", f"The proof of concept needs a 'between' target for {HARDNESS}."))
    for c in setup["targets"]["constraints"]:          # (2026-10-16) a required target the simulated lab cannot produce would show 'No result' on every trial: say so instead of running a useless simulation
        if c.get("required", True) and c["response"] not in (DISSOLUTION, HARDNESS):
            notes.append(Note("blocking", f"'{c['label']}' is a required target, but the simulated lab produces dissolution and hardness only, so every trial would show 'No result'. "
                                          "Mark it optional, or remove it, to simulate this setup."))
    noise = {n["quantity"] for n in setup["virtual_lab"]["noise"]}
    for need in (DISSOLUTION, HARDNESS):
        if need not in noise:
            notes.append(Note("blocking", f"The proof of concept needs a scatter (noise) value for {need}."))
    last = setup["equipment"]["phases"]["reason_adapt_step"]
    for fault in setup["faults"]["scripted"]:
        if fault["where"]["step"] == last:
            notes.append(Note("blocking", f"A scripted fault on trial {fault['trial']} is in the '{last}' step, where the cell decides what to do next. "
                                          "The proof of concept does not support faults there."))
    return notes


def _left_out(setup: dict) -> list[Note]:
    """What the PoC ignores. Each note is one plain sentence."""
    notes = ["The batch size (" + f"{setup['batch_size_g']:g} g" + ") is not used."]
    extra_rules = [r for r in setup["recipe_rules"] if r.get("rule") != "sum_to"]
    if extra_rules:
        notes.append(f"{len(extra_rules)} recipe rule(s) other than 'add up to 100%' are not applied: " + "; ".join(r["label"] for r in extra_rules) + ".")
    if setup["process_factors"]:
        notes.append("Process settings are not used: " + ", ".join(p["label"] for p in setup["process_factors"]) + ".")
    if setup["context_factors"]:
        notes.append("Context factors are not used: " + ", ".join(c["label"] for c in setup["context_factors"]) + ".")
    others = [c["label"] for c in setup["targets"]["constraints"] if c["response"] not in (DISSOLUTION, HARDNESS)]
    if others:
        notes.append("Other targets are not used: " + ", ".join(others) + ".")
    if setup["targets"]["objectives"]:
        notes.append("Objectives (maximise or minimise) are not used: " + ", ".join(o["label"] for o in setup["targets"]["objectives"]) + ".")
    if setup["faults"]["random"]:
        notes.append(f"{len(setup['faults']['random'])} random fault(s) are not used.")
    notes.append("Fault recovery settings, the layout and the stations, the data section and the engine model name are not used.")
    return [Note("info", text) for text in notes]


def _build(setup: dict) -> dict:
    cons = {c["response"]: c for c in setup["targets"]["constraints"]}
    noise = {n["quantity"]: n["sd"] for n in setup["virtual_lab"]["noise"]}
    phases = setup["equipment"]["phases"]
    steps = [{"name": POC_STEP_NAMES.get(s["name"], s["name"]), "label": s["label"], "duration_minutes": s["time_min"]}
             for s in setup["equipment"]["steps"]]
    dis, hard = cons[DISSOLUTION], cons[HARDNESS]
    return {
        "display": dict(setup["display"]),
        "design_space": {"ingredients": {POC_INGREDIENTS[i["id"]]: {"label": i["label"], "min": i["min"], "max": i["max"]} for i in setup["ingredients"]}},
        "specifications": {
            "dissolution_30min": {"label": dis["label"], "unit": dis["unit"], "minimum": dis["value"], "margin_scale": dis["margin_scale"]},
            "hardness": {"label": hard["label"], "unit": hard["unit"], "minimum": hard["low"], "maximum": hard["high"]}},
        "cell": {"measurement_step": POC_STEP_NAMES.get(setup["equipment"]["measurement_step"], setup["equipment"]["measurement_step"]),
                 "steps": steps,
                 "phases": {"act": _rename(phases["act"]), "sense": _rename(phases["sense"]),
                            "reason_adapt_step": POC_STEP_NAMES.get(phases["reason_adapt_step"], phases["reason_adapt_step"]),
                            "reason_minutes": phases["reason_min"]}},
        "run": {"start": setup["calendar"]["start"], "duration_hours": setup["calendar"]["duration_h"], "random_seed": setup["seeds"]["run"]},
        "people": {"staffed_days": list(setup["calendar"]["staffed_days"]), "staffed_from": setup["calendar"]["staffed_from"],
                   "staffed_until": setup["calendar"]["staffed_until"]},
        "virtual_lab": {"noise": {"dissolution_sd": noise[DISSOLUTION], "hardness_sd": noise[HARDNESS]}},
        "decision_engine": {"initial_recipes": setup["engine"]["initial_recipes"], "candidates_per_decision": setup["engine"]["candidates_per_decision"]},
        "scripted_faults": {
            "purge_minutes": setup["faults"]["purge_min"], "clean_after_skip": setup["faults"]["clean_after_skip"],
            "events": [{"trial": f["trial"], "station": POC_STEP_NAMES.get(f["where"]["step"], f["where"]["step"]), "cause": f["cause"],
                        "retry_succeeds": f["retry_succeeds"], "alert": _alert(f["cause"], f["trial"], f["retry_succeeds"])}
                       for f in setup["faults"]["scripted"]]},
        "comparison": {"campaigns": setup["comparison"]["campaigns"], "trials_per_campaign": setup["comparison"]["trials_per_campaign"],
                       "manual_baseline_trials_per_week": setup["baseline"]["manual_trials_per_week"]},
    }


def to_poc_settings(setup, problems: list[Problem] | None = None) -> Conversion:
    """Build the PoC settings preview. Pass the validator's problems: while the setup has errors nothing is converted."""
    if problems is not None and has_errors(problems):
        return Conversion(None, [Note("blocking", "Fix the errors first. The preview is built only from a setup that has no errors.")])
    try:
        blocking = _blocking(setup)
        if blocking:
            return Conversion(None, blocking)
        return Conversion(_build(setup), _left_out(setup))
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        return Conversion(None, [Note("blocking", "This setup is not complete enough to convert yet. Fix the messages on the Review screen first.")])
