"""Format check: the example files in docs/platform_formats/ and the rules in docs/naming.md.

Prints a PASS/FAIL list in plain words. Every check is scripted; nothing is written. It covers:
  A  setup file          B  motion plan and executed timeline     C  cell layout
  D  experiment tables   E  run record                            F  all files together
  G  schemas             H  safe reading and safe paths           I  naming rules
  J  can the PoC settings be built from the setup (converter feasibility)
  K  the schemas and four example files live in the package; docs copies must be identical
  S  self-tests: deliberately broken copies must be caught (so a PASS means something)
All files are ILLUSTRATIVE or SYNTHETIC examples. Nothing here is real client data.
"""
from __future__ import annotations

import copy
import csv
import dataclasses
import io
import itertools
import json
import re
import sys
from datetime import datetime, timedelta
from importlib import metadata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.setup.layout_rules import REACH_FAIL_M, REACH_WARN_M, reach_policy, reach_report  # noqa: E402
from checks.common import Checklist  # noqa: E402

D = ROOT / "docs" / "platform_formats"
PACKAGE = ROOT / "cellpoc" / "formats"
SCHEMAS = PACKAGE / "schemas"                    # the schemas live in the package; docs keeps only a pointer
EXAMPLES = PACKAGE / "examples"                  # master copies of the four files programs read at run time
MASTER_COPIES = ["setup_example.yaml", "cell_layout_example.json", "experiments_example.csv", "experiments_example.meta.json"]
EXTRA_EXAMPLE_SETUPS = ["setup_example_2_week_random_faults.yaml", "setup_example_3_demanding_targets.yaml"]       # the two further illustrative example setups the apps offer (added 2026-10-13 at the project owner's request)
MOCK = ROOT / "data" / "mock"
FILES = {"setup": "setup_example.yaml", "plan": "motion_plan_example.json", "executed": "executed_timeline_example.json",
         "layout": "cell_layout_example.json", "record": "run_record_v2_example.json",
         "csv": "experiments_example.csv", "csv_meta": "experiments_example.meta.json",
         "messy": "experiments_messy_example.csv", "messy_meta": "experiments_messy_example.meta.json"}
SCHEMA_FILES = {"setup": "setup.schema.json", "plan": "plan.schema.json", "executed": "executed_timeline.schema.json", "layout": "layout.schema.json",
                "record": "run_record.schema.json", "row": "experiment_row.schema.json", "meta": "experiments_meta.schema.json"}
ACTION_NAMES = ["move", "pick", "place", "pour", "shake", "press", "stir", "scan", "read", "wait"]
STEPS = ["dispense", "mix", "press", "test", "clean"]
STATUS_ORDER = ["synthetic", "illustrative", "real", "validated"]      # weakest to strongest
INT_COLS = {"replicate_no"}
FLOAT_COLS = {"drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kN", "blend_time_min", "dissolution_30min_pct", "hardness", "friability_pct"}
NULLABLE_TEXT = {"friability_note", "failure_reason"}
ING_COLS = ["drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct"]

checklist = Checklist("FORMAT CHECK - example files, schemas and naming rules (all checks are scripted; nothing is written)")


def rec(check_id: str, ok: bool, text: str, evidence: str = "") -> bool:
    return checklist.record(bool(ok), f"{check_id}  {text}", evidence)


# ------------------------------------------------------------------ reading (tolerant, safe)
def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")          # a leading byte-order mark is accepted


def typed_rows(data: bytes) -> list[dict]:
    """Read an experiment table: BOM and either line ending accepted; blank cells become None; numbers become numbers."""
    rows = []
    for raw in csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")):
        row = {}
        for k, v in raw.items():
            if v == "":
                row[k] = None
            elif k in INT_COLS:
                row[k] = int(v)
            elif k in FLOAT_COLS:
                row[k] = float(v)
            else:
                row[k] = v
        rows.append(row)
    return rows


def path_is_safe(s) -> bool:
    """A file reference must be relative, inside the project, with no drive letter and no '..'."""
    if not isinstance(s, str) or not s or re.match(r"^[A-Za-z]:", s) or s.startswith(("/", "\\")) or any(c in s for c in ':*?"<>|'):
        return False
    if ".." in re.split(r"[/\\]", s):
        return False
    return (D / s).resolve().is_relative_to(ROOT)


def weakest(statuses: list[str]) -> str:
    return min(statuses, key=STATUS_ORDER.index)


def load_all() -> dict:
    out = {}
    for key, name in FILES.items():
        p = D / name
        if name.endswith(".yaml"):
            out[key] = yaml.safe_load(read_text(p))                    # the safe reader only
        elif name.endswith(".json"):
            out[key] = json.loads(read_text(p))
        else:
            out[key] = typed_rows(p.read_bytes())
    return out


# ------------------------------------------------------------------ rule functions (also used by the self-tests)
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
    want = {s["name"]: s["time_min"] * 60 for s in setup["equipment"]["steps"]}
    got = {s: sum(a[dur] for a in actions if a["step"] == s and (not planned_only or a["origin"] == "planned")) for s in want}
    return [f"step {s}: actions add up to {got[s]:g} s, the setup says {want[s]:g} s" for s in want if abs(got[s] - want[s]) > 1.0]


def phase_problems(actions: list[dict], setup: dict, start_key: str) -> list[str]:
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


# The reach calculation and the spare-reach policy (warn below 0.10 m, fail below 0.03 m) now live in
# cellpoc/setup/layout_rules.py, so the setup app and this check use the very same code.
VAGUE_WORDS = {"wait", "waiting", "idle", "filler", "padding", "pause", "delay", "pending", "tbd", "todo"}


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


def numeric_without_unit(setup: dict) -> list[str]:
    """Numbers in the setup whose unit is not named (rule 3 in docs/naming.md)."""
    suffix = re.compile(r"(_pct|_g|_kn|_kp|_min|_s|_h|_m|_week)$")
    no_unit_needed = {"trial", "campaigns", "trials_per_campaign", "initial_recipes", "candidates_per_decision", "run", "max_retries",
                      "format_version", "divide_by", "chance_per_trial", "retry_succeeds_chance"}
    bad = []

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    named = (suffix.search(k) or "per_week" in k or "unit" in o or k in no_unit_needed
                             or any(isinstance(o.get(q), str) and suffix.search(o[q]) for q in ("quantity", "response")))
                    if not named:
                        bad.append(f"{path}.{k}={v}")
                else:
                    walk(v, f"{path}.{k}" if path else k)
        elif isinstance(o, list):
            for n, v in enumerate(o):
                walk(v, f"{path}[{n}]")
    walk(setup)
    return bad


# ------------------------------------------------------------------ schemas
try:
    from jsonschema import Draft202012Validator, FormatChecker
    SCHEMA_LIB = metadata.version("jsonschema")
except Exception as error:   # noqa: BLE001
    Draft202012Validator, FormatChecker, SCHEMA_LIB = None, None, f"unavailable ({error})"


def schema_errors(schema: dict, doc) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(top)'}: {e.message[:110]}" for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))]


# ------------------------------------------------------------------ the checks
def main() -> int:
    # ---------- F1 parse
    try:
        F = load_all()
        rec("F1", True, "Every example file parses without errors (YAML, JSON and both CSV tables)", f"{len(FILES)} files")
    except Exception as error:   # noqa: BLE001
        rec("F1", False, "Every example file parses without errors", repr(error))
        return checklist.print()
    S, P, E, L, R = F["setup"], F["plan"], F["executed"], F["layout"], F["record"]
    schemas = {k: json.loads(read_text(SCHEMAS / v)) for k, v in SCHEMA_FILES.items()}
    mock_header = (MOCK / "mock_formulation_experiments.csv").read_bytes().split(b"\n")[0].decode("utf-8").split(",")

    # ---------- A setup
    ing = {i["id"]: i for i in S["ingredients"]}
    bal = [i for i in S["ingredients"] if i["role"] == "balance"]
    others = [i for i in S["ingredients"] if i["role"] != "balance"]
    lo, hi = 100 - sum(i["max"] for i in others), 100 - sum(i["min"] for i in others)
    cap = next(r for r in S["recipe_rules"] if r["rule"] == "at_most")
    lo_rule = 100 - (sum(ing[k]["max"] for k in ("drug_pct", "lubricant_pct")) + min(sum(ing[k]["max"] for k in cap["items"]), cap["limit"]))
    f = bal[0] if bal else {"min": 0, "max": 0}
    rec("A1", len(bal) == 1 and bal[0]["id"] == "filler_pct" and f["min"] <= lo and hi <= f["max"],
        "Filler is the one balance ingredient and the other four ranges leave it reachable",
        f"filler ends up {lo:g} to {hi:g}% ({lo_rule:g} to {hi:g}% with the binder-plus-disintegrant rule); declared {f['min']:g} to {f['max']:g}%")
    bare = numeric_without_unit(S)
    rec("A2", not bare, "Every numeric field in the setup names its unit (in the field name, or a unit field beside it; counts and probabilities need none)",
        f"{len(bare)} without: {bare[:4]}" if bare else "all numeric fields checked")
    goals = {t["goal"] for t in S["targets"]["constraints"]} | {t["goal"] for t in S["targets"]["objectives"]}
    all_t = S["targets"]["constraints"] + S["targets"]["objectives"]
    rec("A3", {"at_least", "at_most", "between", "maximise", "minimise"} <= goals and all(t.get("unit") for t in all_t)
        and all(t["goal"] in ("at_least", "at_most", "between") for t in S["targets"]["constraints"])
        and all(t["goal"] in ("maximise", "minimise") for t in S["targets"]["objectives"]),
        "Targets are split into constraints (at least, at most, between) and objectives (maximise, minimise), all five goals shown, each with a unit",
        "constraints: " + ", ".join(f"{t['response']} {t['goal']} [{t['unit']}]" for t in S["targets"]["constraints"])
        + " | objectives: " + ", ".join(f"{t['goal']} {t['quantity']} [{t['unit']}]" for t in S["targets"]["objectives"]))
    sc = {x["trial"]: x for x in S["faults"]["scripted"]}
    rec("A4", 8 in sc and sc[8]["retry_succeeds"] is True and 19 in sc and sc[19]["retry_succeeds"] is False
        and all({"step", "action", "ingredient"} <= set(x["where"]) for x in sc.values()),
        "Scripted faults: trial 8 recovers on retry, trial 19's retry fails (candidate skipped); each says the step, action and ingredient it hits",
        f"trial 8: {sc[8]['where']} retry_succeeds={sc[8]['retry_succeeds']}; trial 19: retry_succeeds={sc[19]['retry_succeeds']}")
    src = (ROOT / "tools/make_mock_data.py").read_text(encoding="utf-8")
    lim = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(r"(\w+)=\(([\d.]+),\s*([\d.]+)\)", src.split("LIM = dict(")[1].split("\n")[0])}
    alias = {"drug": "drug_pct", "binder": "binder_pct", "disint": "disintegrant_pct", "lube": "lubricant_pct", "force": "compression_force_kn", "blend": "blend_time_min"}
    ranges = {i["id"]: (float(i["min"]), float(i["max"])) for i in S["ingredients"]}
    ranges.update({p["id"]: (float(p["min"]), float(p["max"])) for p in S["process_factors"]})
    mism = {alias[k]: (v, ranges.get(alias[k])) for k, v in lim.items() if ranges.get(alias[k]) != v}
    mock_rows = typed_rows((MOCK / "mock_formulation_experiments.csv").read_bytes())
    ctx_bad = [c["id"] for c in S["context_factors"] if sorted(c["values"]) != sorted({r[c["id"]] for r in mock_rows})]
    rec("A5", not mism and not ctx_bad, "Ingredient and process ranges and the context values match data/mock/ and tools/make_mock_data.py",
        "drug 10-30, binder 2-6, disintegrant 1-8, lubricant 0.25-2, force 5-20, blend 5-30 all equal" if not mism else f"differences: {mism} {ctx_bad}")

    # ---------- B plan and executed timeline
    pa, ea = P["actions"], E["actions"]
    rec("B1", all("start_s" in a and "duration_s" in a for a in pa) and all("actual_start_s" in a and "actual_duration_s" in a for a in ea),
        "Every action has a start time and a duration (plan and executed timeline)", f"{len(pa)} planned actions, {len(ea)} executed actions")
    used = {a["type"] for a in pa + ea}
    rec("B2", used <= set(ACTION_NAMES) and set(ACTION_NAMES) <= {a["type"] for a in pa},
        "Every action name is from the fixed list of ten, and all ten appear in the full plan",
        f"outside the list: {sorted(used - set(ACTION_NAMES)) or 'none'}; never used in the plan: {sorted(set(ACTION_NAMES) - {a['type'] for a in pa}) or 'none'}")
    pt, et = timing_problems(pa, "start_s", "duration_s"), timing_problems(ea, "actual_start_s", "actual_duration_s")
    rec("B3", not pt and not et, "Times never go backwards: actions follow each other with no gap and no overlap (plan and executed timeline)", "; ".join(pt + et) or "contiguous from 0 s")
    fault = next((a for a in ea if a.get("outcome") == "failed"), None)
    rec_acts = [a for a in ea if a["origin"] == "recovery"]
    order_ok = bool(fault) and rec_acts and [a["type"] for a in rec_acts] == ["shake", "place", "wait", "pick", "pour"] \
        and ea.index(fault) < ea.index(rec_acts[0]) and all(a["recovers"] == fault["id"] for a in rec_acts)
    purge = next((a for a in rec_acts if a["type"] == "wait"), None)
    rec("B4", order_ok and purge and purge["actual_duration_s"] == S["faults"]["purge_min"] * 60
        and rec_acts[0]["actual_duration_s"] == S["faults"]["recovery"]["tap_shake_s"],
        "Trial 8: the jam, then recovery (tap-shake, bottle back, purge, bottle again, retry pour) in the right order, purge and tap-shake lasting what the setup says",
        f"fault {fault['id']} at {fault['actual_start_s']} s; recovery {[a['id'] for a in rec_acts]}; purge {purge['actual_duration_s'] if purge else '?'} s = setup {S['faults']['purge_min'] * 60} s")
    fp, fe = flow_problems(pa, L), flow_problems(ea, L)
    rec("B5", not fp and not fe, "Every pick has a matching place, no object is held by two actions, scans/shakes/pours happen holding the right object, and no long wait is spent holding something",
        "; ".join((fp + fe)[:4]) or "plan and executed timeline both walked action by action")
    layout_ids = ({s["id"] for s in L["stations"]} | {s["id"] for s in L["bottle_shelf"]["slots"]} | {h["id"] for h in L["tool_holders"]} | {"home"})
    obj_ids = {o["id"] for o in L["objects"]}
    refs = [(a["id"], k, a[k]) for a in pa + ea for k in ("from", "to", "at") if k in a] + [(a["id"], "object", a["object"]) for a in pa + ea if "object" in a]
    missing = [(i, k, v) for i, k, v in refs if (v not in obj_ids if k == "object" else v not in layout_ids)]
    rec("B6", not missing, "Every station, slot, holder and object ID used in the plan and executed timeline exists in the layout", f"{len(refs)} references checked; missing: {missing or 'none'}")
    sp = step_sum_problems(pa, S, "duration_s")
    se = step_sum_problems(ea, S, "planned_duration_s", planned_only=True)
    want = {s["name"]: s["time_min"] * 60 for s in S["equipment"]["steps"]}
    rec("B7", not sp and not se and E["step_totals_s"]["planned"] == want and P["step_totals_s"] == want,
        "Within each step the action durations (waits included) add up to the setup's step time within 1 second: in the plan, and in the planned part of the executed timeline",
        f"plan totals {P['step_totals_s']} = setup {want}; largest difference 0 s" if not (sp or se) else "; ".join(sp + se))
    actual = {s: sum(a["actual_duration_s"] for a in ea if a["step"] == s) for s in STEPS}
    extra = sum(actual.values()) - sum(want.values())
    delta = sum(a["actual_duration_s"] - a["planned_duration_s"] for a in ea if a["origin"] == "planned") + sum(a["actual_duration_s"] for a in rec_acts)
    rec("B8", E["step_totals_s"]["actual"] == actual and abs(extra - delta) < 1e-6 and sum(1 for s in STEPS if actual[s] != want[s]) == 1,
        "The executed totals are explained: only the faulted step (dispense) is longer, by exactly the recovery actions plus the shortened failed pour",
        f"actual {actual}; extra {extra:g} s = recovery {sum(a['actual_duration_s'] for a in rec_acts):g} s + change to the failed pour {delta - sum(a['actual_duration_s'] for a in rec_acts):g} s")
    keep = ("id", "step", "phase", "type", "object", "from", "to", "into", "at", "amount_g", "style", "force_kn", "quantity", "reason", "caption")
    same = [a["id"] for a in pa if a["id"] not in {x["id"] for x in ea if x["origin"] == "planned"}] == [] and \
        all({k: v for k, v in pa_.items() if k in keep and k != "caption"} == {k: v for k, v in ea_.items() if k in keep and k != "caption"}
            for pa_, ea_ in zip(pa, [x for x in ea if x["origin"] == "planned"])) and \
        all(ea_["planned_start_s"] == pa_["start_s"] and ea_["planned_duration_s"] == pa_["duration_s"] for pa_, ea_ in zip(pa, [x for x in ea if x["origin"] == "planned"]))
    rec("B9", same and len([x for x in ea if x["origin"] == "planned"]) == len(pa) and E["plan_id"] == P["plan_id"] and E["trial"] == P["trial"] and E["trial_start_minute"] == P["trial_start_minute"],
        "The executed timeline contains every planned action unchanged (same step, type, objects, places and planned times), plus the recovery actions tagged 'recovery'",
        f"{len(pa)} planned actions + {len(rec_acts)} recovery actions = {len(ea)}")
    batch, rec_amt = P["batch_size_g"], P["recipe"]
    pours = {a["object"]: a["amount_g"] for a in pa if a["type"] == "pour" and a["into"] == "vial"}
    want_amt = {"bottle_" + k.replace("_pct", ""): round(batch * rec_amt[k] / 100, 2) for k in ING_COLS}
    delivered = {}
    for a in ea:
        if a["type"] == "pour" and a["into"] == "vial" and "reading" in a:
            delivered[a["object"]] = round(delivered.get(a["object"], 0) + a["reading"]["value"], 4)
    rec("B10", pours == want_amt and abs(sum(pours.values()) - batch) < 0.01 and all(abs(delivered[k] - v) < 0.005 for k, v in want_amt.items())
        and abs(sum(rec_amt[k] for k in ING_COLS) - 100) < 0.01,
        "Pour amounts equal batch size times the recipe percentage and add up to the batch; what was actually delivered (including the retry) adds up to the same",
        f"batch {batch:g} g; binder planned {pours.get('bottle_binder')} g, delivered {delivered.get('bottle_binder')} g (0.31 + 0.55)")
    shake = next(a for a in pa if a["type"] == "shake" and a["style"] == "mix")
    press = next(a for a in pa if a["type"] == "press")
    rec("B11", shake["duration_s"] == rec_amt["blend_time_min"] * 60 and press["force_kn"] == rec_amt["compression_force_kn"],
        "The mixing shake lasts the recipe's blend time and the press uses the recipe's compression force",
        f"shake {shake['duration_s']} s = {rec_amt['blend_time_min']} min; press {press['force_kn']} kN")
    ph = phase_problems(pa, S, "start_s") + phase_problems(ea, S, "actual_start_s")
    rec("B12", not ph and all(a["phase"] == a["phase"].lower() for a in pa + ea),
        "Phases are lowercase and match the setup: act for dispense, mix and press; sense for test; reason for the first 30 minutes of clean, adapt for the rest", "; ".join(ph[:3]) or "all actions checked")
    x = next((a for a in sc.values() if a["trial"] == E["trial"]), None)
    rec("B13", bool(x) and fault and E["faults"][0]["where"] == x["where"] == fault["fault"]["where"] and fault["fault"]["cause"] == x["cause"] == E["faults"][0]["cause"]
        and E["faults"][0]["recovered"] is x["retry_succeeds"] and E["outcome"] == "completed_after_recovery",
        "The fault in the executed timeline is the one the setup scripts for that trial (same step, action, ingredient and cause; recovered)",
        f"{fault['fault']['where']}, cause '{fault['fault']['cause']}'")
    ok_rec = all(r_["recovers"] == fault["id"] and "planned_start_s" not in r_ for r_ in rec_acts) and E["faults"][0]["recovery_action_ids"] == [r_["id"] for r_ in rec_acts]
    rec("B14", ok_rec, "Recovery actions are tagged origin 'recovery', say which action they recover, and carry no planned time", f"{[r_['id'] for r_ in rec_acts]} recover {fault['id']}")
    wr = wait_reason_problems(pa) + wait_reason_problems(ea)
    n_waits = sum(1 for a in pa + ea if a["type"] == "wait")
    rec("B15", not wr, "Every wait action (plan and executed timeline) has a reason that names the real process it stands for",
        "; ".join(wr[:3]) or f"{n_waits} waits, e.g. '{next(a['reason'] for a in pa if a['type'] == 'wait')}'")
    fr = friability_problems(S, pa)
    friab_actions = [a["id"] for a in pa if "friabilator" in (a.get("from"), a.get("to"), a.get("at"))]
    rec("B16", not fr, "The plan uses the friability tester exactly when the setup needs friability (an objective on it, or a required constraint on it)",
        "; ".join(fr) or f"the plan uses the friability tester in {len(friab_actions)} actions ({', '.join(friab_actions)}); the setup needs it because friability_pct is an objective")

    # ---------- C layout
    rec("C1", "metres" in L["units"] and "degrees" in L["units"], "The layout states its units: metres and degrees", L["units"][:80])
    sids = {s["id"] for s in L["stations"]}
    slots = {s["id"]: s["ingredient_id"] for s in L["bottle_shelf"]["slots"]}
    rec("C2", {"rack", "balance", "press", "gauge", "vessel", "discard"} <= sids and len(slots) == 5 and {t["id"] for t in L["tool_holders"]} == {"punch_holder", "rod_holder"}
        and {"vial", "tablet", "punch", "rod"} <= obj_ids,
        "The layout lists the stations (rack and scanner, balance, press, hardness gauge, dissolution vessel, discard bin, plus the friability tester), five bottle slots, tools and an object list (vial, tablet, bottles, punch, rod)",
        f"stations {sorted(sids)}; slots {len(slots)}; objects {len(obj_ids)}")
    rec("C3", set(slots.values()) == set(ing) and all(any(o.get("ingredient_id") == v and o["starts_at"] == k for o in L["objects"]) for k, v in slots.items()),
        "The five bottle slots map to the same ingredient IDs as the setup, and each bottle object starts in its slot", f"slots {slots}")
    margin, where_, reach_problems = reach_report(L)
    r_ = L["robot"]
    rec("C4", not reach_problems and abs(r_["reach_m"] - (r_["links_m"]["upper_arm"] + r_["links_m"]["forearm"])) < 1e-9 and all("position" in h for h in L["tool_holders"]),
        "Every station, slot and tool holder is within the arm's reach in 3D (shoulder height and link lengths used), at its working height and at the safe height; tool positions are given",
        f"arm reach {r_['links_m']['upper_arm'] + r_['links_m']['forearm']:.2f} m; tightest margin {margin:.3f} m at {where_}" if not reach_problems else "; ".join(reach_problems))
    verdict = reach_policy(margin)
    policy_text = f"C5  Spare reach policy: fail below {REACH_FAIL_M:.2f} m, warn below {REACH_WARN_M:.2f} m, otherwise fine"
    evidence = f"spare reach {margin:.3f} m at {where_}"
    if verdict == "warn":
        checklist.warn(policy_text + " - WARNING: the tightest spot has less than 0.10 m to spare. It still works; moving a slot or raising the shoulder would add margin.", evidence)
    else:
        rec("C5", verdict == "pass", policy_text.split("  ", 1)[1], evidence)

    # ---------- D experiment tables
    ex_bytes, ms_bytes = (D / FILES["csv"]).read_bytes(), (D / FILES["messy"]).read_bytes()
    header = lambda b: b.decode("utf-8-sig").split("\n")[0].strip().split(",")   # noqa: E731
    rec("D1", header(ex_bytes) == mock_header and header(ms_bytes) == mock_header, "Column names and order are identical to data/mock/mock_formulation_experiments.csv (both example tables)", f"{len(mock_header)} columns")
    rows, messy = F["csv"], F["messy"]
    sums = [sum(r[c] for c in ING_COLS) for r in rows + messy]
    rec("D2", all(abs(s - 100) <= 0.05 for s in sums) and all(r["hardness_unit"] in ("kP", "N") and r["status"] in ("ok", "failed") for r in rows + messy),
        "Rows are valid: ingredients add up to 100 (within 0.05), hardness units are named (kP or N) and statuses are known (ok or failed)",
        f"{len(rows) + len(messy)} rows; sums {min(sums):.3f} to {max(sums):.3f}")
    mock_lines = set((MOCK / "mock_formulation_small.csv").read_bytes().split(b"\n")) | set((MOCK / "mock_formulation_hard.csv").read_bytes().split(b"\n"))
    lines_ok = all(l in mock_lines for l in ex_bytes.split(b"\n")[1:] + ms_bytes.split(b"\n")[1:] if l)
    rec("D3", lines_ok and not ex_bytes.startswith(b"\xef\xbb\xbf") and not ms_bytes.startswith(b"\xef\xbb\xbf") and b"\r\n" not in ex_bytes + ms_bytes,
        "The example tables use no byte-order mark and Unix line endings, like the mock files, and every data line is copied from the synthetic mock files (so no real client data)",
        f"BOM: none; CRLF line ends: {(ex_bytes + ms_bytes).count(b'\r\n')}; lines found in the mock files: yes")
    mutated = b"\xef\xbb\xbf" + ex_bytes.replace(b"\n", b"\r\n")
    rec("D4", typed_rows(mutated) == rows and typed_rows(ex_bytes) == rows,
        "Reading tolerates a byte-order mark and Windows line endings: a copy with both gives exactly the same rows", f"{len(rows)} rows identical")
    n = {"failed": sum(r["status"] == "failed" for r in messy), "newtons": sum(r["hardness_unit"] == "N" for r in messy),
         "missing": sum(r["status"] == "ok" and (r["dissolution_30min_pct"] is None or r["friability_pct"] is None) for r in messy),
         "below_detection": sum(r["friability_note"] == "<0.05" for r in messy), "replicates": sum(r["replicate_no"] > 1 for r in messy), "batches": len({r["batch_id"] for r in messy})}
    rec("D5", n["failed"] >= 1 and n["newtons"] >= 1 and n["missing"] >= 1 and n["below_detection"] >= 1 and n["replicates"] >= 1 and n["batches"] >= 3,
        "The messy example really is messy: failed runs, values in newtons, missing values, below-detection values, replicates and several batches", str(n))
    row_errors = [e for r in rows + messy for e in schema_errors(schemas["row"], r)]
    rec("D6", not row_errors, "Every row of both tables passes the experiment-row schema (types, ranges, allowed values, failed rows have no results)", f"{len(rows) + len(messy)} rows; {row_errors[:2] or 'no errors'}")

    # ---------- E run record
    poc_keys = [f_.name for f_ in dataclasses.fields(__import__("cellpoc.contracts", fromlist=["RunRecord"]).RunRecord)]
    unmarked = [k for k in poc_keys if k not in R]
    rec("E1", R["data_status"] in STATUS_ORDER and "SYNTHETIC" in R["label"].upper(), "The record has a field marking the data status, and says so in its label", f"data_status = {R['data_status']}")
    rec("E2", not unmarked, "Every section of today's run record is either shown or marked 'unchanged_from_poc'",
        f"today's {len(poc_keys)} sections all present; marked unchanged: {sorted(k for k, v in R.items() if isinstance(v, dict) and v.get('unchanged_from_poc'))}" if not unmarked else f"missing: {unmarked}")
    t0 = R["trials"][0]
    files_ok = all(path_is_safe(p) and (D / p).exists() for p in [R["meta"]["setup_file"], R["meta"]["layout_file"], R["data"]["experiments_file"], R["data"]["meta_file"], t0["plan_file"], t0["executed_file"]] + [i["file"] for i in R["meta"]["inputs"]])
    rec("E3", files_ok and t0["plan_id"] == P["plan_id"] == E["plan_id"] and t0["trial"] == P["trial"] and t0["recipe"] == P["recipe"] and t0["why"] == P["why"]
        and t0["result"] == E["result"] and R["data"]["rows_read"] == len(rows) and R["meta"]["start"] == S["calendar"]["start"] and R["meta"]["seed"] == S["seeds"]["run"]
        and datetime.strptime(R["meta"]["end"], "%Y-%m-%d %H:%M") == datetime.strptime(S["calendar"]["start"], "%Y-%m-%d %H:%M") + timedelta(hours=S["calendar"]["duration_h"]),
        "The record's references resolve and agree: files exist, plan and executed timeline IDs, trial, recipe, result, row count, start, end and seed match the other files", f"plan {t0['plan_id']}, trial {t0['trial']}")
    m = R["model"]
    nums = [v for c in m["candidates"] for k, v in c.items() if k != "name"]
    rec("E4", m["selected"] is None and m["how_chosen"] is None and all(v is None for v in nums) and "No model" in m["note"],
        "Model numbers are null with an explanatory note, not realistic-looking values", f"{len(nums)} numbers, all null; note: {m['note'][:50]}...")
    statuses = {i["file"]: i["data_status"] for i in R["meta"]["inputs"]}
    own = {FILES["setup"]: S["project"]["data_status"], FILES["layout"]: L["data_status"], FILES["csv"]: F["csv_meta"]["data_status"],
           FILES["plan"]: P["data_status"], FILES["executed"]: E["data_status"]}
    rec("E5", statuses == own and R["data_status"] == weakest(list(own.values())) == "synthetic",
        "The record takes the weakest data status of its inputs (illustrative setup + synthetic table + illustrative layout = synthetic), and each input's status matches the file's own",
        f"inputs {own} -> {R['data_status']}")

    # ---------- F all files
    metas = {k: F[k] for k in ("csv_meta", "messy_meta")}
    vl = {"setup": S["format_version"], "layout": L["format_version"], "plan": P["format_version"], "executed": E["format_version"], "record": R["format_version"],
          **{k: v["format_version"] for k, v in metas.items()}}
    labels = {"setup": S["project"]["data_status"], "layout": L["data_status"] and L["label"], "plan": P["label"], "executed": E["label"], "record": R["label"], "csv_meta": F["csv_meta"]["label"], "messy_meta": F["messy_meta"]["label"]}
    status_vals = [S["project"]["data_status"], L["data_status"], P["data_status"], E["data_status"], R["data_status"], F["csv_meta"]["data_status"], F["messy_meta"]["data_status"]]
    rec("F2", all(vl.values()) and all(labels.values()) and all(s in STATUS_ORDER for s in status_vals) and (D / FILES["csv_meta"]).exists(),
        "Every file carries a version and an illustrative or synthetic label (the CSV tables through their companion .meta.json)", f"versions {vl}; data statuses {sorted(set(status_vals))}")
    qty = set(ing) | {p["id"] for p in S["process_factors"]} | {t["response"] for t in S["targets"]["constraints"]} | {t["quantity"] for t in S["targets"]["objectives"]}
    used_q = ({s["instrument"]["reads"] for s in L["stations"] if "instrument" in s} | {a["quantity"] for a in pa + ea if "quantity" in a} | set(P["recipe"]) | set(R["ingredient_labels"])
              | set(t0["recipe"]) | {k for k in E["result"] if k != "verdict"} | {k for k in t0["result"] if k != "verdict"} | set(S["data"]["column_map"].values()) | {S["data"]["hardness"]["to"]})
    known = qty | {"mass_g", "barcode", "binder_supplier", "filler_grade", "dissolution_instrument"}
    unknown = sorted(used_q - known)
    forbidden = {"dissolution_pct", "hardness", "drug", "filler", "binder", "disintegrant", "lubricant", "compression_force_kN", "blend"}
    def strings(o, skip=()):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in skip:
                    continue
                yield from strings(v, skip)
        elif isinstance(o, list):
            for v in o:
                yield from strings(v, skip)
        elif isinstance(o, str):
            yield o
    # 'role' values (binder, disintegrant, ...) are a vocabulary of ingredient roles, not quantity IDs; free text is skipped too
    aliases = sorted({s for doc in (S, L, P, E, R) for s in strings(doc, skip=("data", "role", "label", "caption", "note", "why", "time_note", "reason", "detail", "plain_summary", "other_fields", "cause", "units", "description")) if s in forbidden})
    rec("F3", not unknown and not aliases, "One ID per quantity across all files: no old names (such as 'hardness' or 'dissolution_pct') outside the raw-column mapping, and every quantity ID is a known one",
        f"unknown IDs: {unknown or 'none'}; old names found: {aliases or 'none'}; hardness is '{S['data']['hardness']['to']}' everywhere")
    steps = [s["name"] for s in S["equipment"]["steps"]]
    holder_station = {h["id"]: h["station"] for h in L["tool_holders"]}
    slot_ids = set(slots)
    def station_of(loc):
        return "bottle_shelf" if loc in slot_ids else holder_station.get(loc, loc)
    stray = []
    for a in pa:
        used_st = {station_of(a[k]) for k in ("from", "to", "at") if k in a and a[k] != "home"}
        allowed = set(next(s for s in S["equipment"]["steps"] if s["name"] == a["step"])["stations"])
        stray += [(a["id"], u) for u in used_st if u not in allowed]
    kfirst = sum(s["time_min"] for s in S["equipment"]["steps"]) * 60
    start_ok = P["trial_start_minute"] == (P["trial"] - 1) * kfirst / 60
    rec("F4", steps == STEPS == [s["name"] for s in R["steps"]] and not stray and start_ok and sc[8]["trial"] == P["trial"] == E["trial"] == t0["trial"]
        and sorted(S["equipment"]["phases"]["act"] + S["equipment"]["phases"]["sense"] + [S["equipment"]["phases"]["reason_adapt_step"]]) == sorted(steps),
        "Steps, stations and trial numbers agree across the files: the same five step names; every station an action uses is listed under its step in the setup; trial 8 everywhere; trial start = (trial - 1) x one trial's length",
        f"stray stations: {stray or 'none'}; trial_start_minute {P['trial_start_minute']:g} = 7 x {kfirst / 60:g} min")
    texts = {n: read_text(D / n) for n in list(FILES.values()) + ["README.md"]}
    texts.update({f"schemas/{s}": read_text(SCHEMAS / s) for s in SCHEMA_FILES.values()})
    texts["naming.md"] = read_text(ROOT / "docs" / "naming.md")
    # absolute-path patterns (drive letters, user folders, network paths) apply to every file except the schemas, whose regular expressions
    # legitimately contain backslashes; the personal-name and address patterns apply to all files
    paths_pat = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|file:///|(?<![\\])\\\\[A-Za-z]", re.I)
    names_pat = re.compile(r"pranay|deloitte|@[a-z0-9-]+\.[a-z]{2,}", re.I)
    hits = [(n, i, l.strip()[:50]) for n, t in texts.items() for i, l in enumerate(t.splitlines(), 1)
            if names_pat.search(l) or (not n.startswith("schemas/") and paths_pat.search(l))]
    rec("F5", not hits and not F["csv_meta"]["contains_real_client_data"] and not F["messy_meta"]["contains_real_client_data"],
        "No real client data, no absolute file paths, no personal names or addresses in any example, schema or doc file", f"{len(texts)} files scanned; hits: {hits[:2] or 'none'}")
    all_refs = [S["equipment"]["layout_file"], S["data"]["experiments_file"], S["data"]["meta_file"], E["plan_file"], F["csv_meta"]["table_file"], F["messy_meta"]["table_file"],
                R["meta"]["setup_file"], R["meta"]["layout_file"], R["data"]["experiments_file"], R["data"]["meta_file"], t0["plan_file"], t0["executed_file"]] + [i["file"] for i in R["meta"]["inputs"]]
    rec("F6", all(path_is_safe(r_) and (D / r_).exists() for r_ in all_refs), "Every file reference inside the files is relative, inside the project, has no '..', and points at a file that exists", f"{len(all_refs)} references")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "tools"))
    import make_trial_story
    story_path = D / "trial8_story.md"
    story_now = make_trial_story.build_story(E, L, S)
    story_disk = story_path.read_bytes().decode("utf-8") if story_path.exists() else ""
    rec("F7", story_disk == story_now and "jam" in story_disk and "FAILED" in story_disk and "purge the dispenser" in story_disk and story_disk.count("| recovery |") == len(rec_acts),
        "trial8_story.md matches the executed timeline exactly (it is regenerated from the timeline and compared) and tells the jam, the purge and the retry",
        f"{len(story_disk.splitlines())} lines; {story_disk.count('| planned |')} planned and {story_disk.count('| recovery |')} recovery rows" if story_disk == story_now else "the file differs from what the timeline produces: run tools/make_trial_story.py")

    # ---------- K package copies and docs copies
    differing = [n for n in MASTER_COPIES if (D / n).read_bytes() != (EXAMPLES / n).read_bytes()]
    rec("K1", not differing and all((EXAMPLES / n).exists() for n in MASTER_COPIES),
        "The docs copies of the four runtime example files are byte-for-byte identical to the master copies in the package",
        f"{len(MASTER_COPIES)} files compared; differing: {differing or 'none'}")
    docs_schemas = sorted(p.name for p in (D / "schemas").glob("*")) if (D / "schemas").exists() else []
    rec("K2", docs_schemas == ["MOVED.md"] and all((SCHEMAS / s).exists() for s in SCHEMA_FILES.values()),
        "The seven schemas live in the package and docs keeps only a pointer (MOVED.md)", f"package schemas: {len(SCHEMA_FILES)}; docs folder holds: {docs_schemas}")
    pkg_files = sorted(p.name for p in EXAMPLES.glob("*"))
    rec("K3", pkg_files == sorted(MASTER_COPIES + EXTRA_EXAMPLE_SETUPS), "The package examples folder holds exactly the four runtime example files and the two further example setups, nothing else", f"{pkg_files}")
    from cellpoc.setup import has_errors as _has_errors, load_setup as _load_setup, validate as _validate
    extra = {n: _load_setup(EXAMPLES / n) for n in EXTRA_EXAMPLE_SETUPS}
    extra_problems = {n: ([] if loaded.setup is None else _validate(loaded.setup, base_dir=EXAMPLES)) for n, loaded in extra.items()}
    rec("K4", all(loaded.setup is not None and not _has_errors(extra_problems[n]) and loaded.setup["project"]["data_status"] == "illustrative" and loaded.setup["project"]["name"].startswith("Illustrative study") for n, loaded in extra.items())
        and len({loaded.setup["project"]["name"] for loaded in extra.values()} | {S["project"]["name"]}) == 3,
        "The two further example setups pass the platform's own setup checker with no errors, are marked illustrative, and each has its own name", "; ".join(f"{n}: {sum(p.level == 'warning' for p in extra_problems[n])} warning(s)" for n in extra))

    # ---------- G schemas
    rec("G1", Draft202012Validator is not None, "The schema library (jsonschema) works with this Python version and is installed", f"jsonschema {SCHEMA_LIB} on Python {sys.version.split()[0]}")
    if Draft202012Validator is None:
        return checklist.print()
    meta_bad = []
    for k, s in schemas.items():
        try:
            Draft202012Validator.check_schema(s)
        except Exception as error:   # noqa: BLE001
            meta_bad.append((k, str(error)[:60]))
    rec("G2", not meta_bad, "All seven schemas are themselves valid JSON Schema (draft 2020-12)", f"{len(schemas)} schemas; problems: {meta_bad or 'none'}")
    errs = {"setup": schema_errors(schemas["setup"], S), "layout": schema_errors(schemas["layout"], L), "plan": schema_errors(schemas["plan"], P),
            "executed timeline": schema_errors(schemas["executed"], E), "run record": schema_errors(schemas["record"], R),
            "csv meta": schema_errors(schemas["meta"], F["csv_meta"]), "messy meta": schema_errors(schemas["meta"], F["messy_meta"])}
    rec("G3", not any(errs.values()), "Every structured example file passes its schema (required and optional fields, allowed values, units, relative paths)",
        "; ".join(f"{k}: {v[:2]}" for k, v in errs.items() if v) or "setup, layout, plan, executed timeline, run record and both table companions: 0 errors")

    # ---------- H safe reading, safe paths
    py_files = [p for p in list((ROOT / "cellpoc").rglob("*.py")) + list((ROOT / "checks").rglob("*.py")) if p.name != "formats_check.py"]
    unsafe_words = ["yaml." + "load(", "unsafe" + "_load", "Full" + "Loader", "Loader" + "="]
    unsafe_use = [(p.name, w) for p in py_files for w in unsafe_words if w in p.read_text(encoding="utf-8")]
    try:
        yaml.safe_load("x: !!python/object/apply:os.system ['echo hi']")
        rejected = False
    except yaml.YAMLError:
        rejected = True
    rec("H1", not unsafe_use and rejected, "YAML is read with the safe reader only: no unsafe loader anywhere in the code, and a file with a dangerous tag is refused", f"{len(py_files)} code files scanned; unsafe uses: {unsafe_use or 'none'}")
    bad_paths = ["../x.json", "a/../../x.json", "C:\\x.json", "c:/x.json", "/etc/passwd", "\\\\server\\share\\x", "a\\..\\b.json"]
    good_paths = ["setup_example.yaml", "schemas/setup.schema.json"]
    rec("H2", not any(path_is_safe(p) for p in bad_paths) and all(path_is_safe(p) for p in good_paths), "The path guard refuses absolute paths, drive letters, network paths and '..', and accepts ordinary relative ones",
        f"{len(bad_paths)} bad paths refused, {len(good_paths)} good accepted")

    # ---------- I naming rules
    naming = texts["naming.md"]
    id_re = re.compile(r"^[a-z][a-z0-9_]*$")
    ids = [i["id"] for i in S["ingredients"]] + [p["id"] for p in S["process_factors"]] + [c["id"] for c in S["context_factors"]] + [s["id"] for s in L["stations"]] + list(slots) + [o["id"] for o in L["objects"]] + [h["id"] for h in L["tool_holders"]]
    badid = [i for i in ids if not id_re.match(i)]
    suffixes_ok = all(re.search(r"_pct$", i["id"]) for i in S["ingredients"]) and all(re.search(r"_(kn|min)$", p["id"]) for p in S["process_factors"]) \
        and all(re.search(r"_(pct|kp)$", t["response"]) for t in S["targets"]["constraints"])
    rec("I1", not badid and suffixes_ok and all(i in naming for i in sorted(known - {"barcode"})) and all(w in naming for w in STEPS + ACTION_NAMES + STATUS_ORDER),
        "docs/naming.md exists, lists every platform ID, step, action name and data status, and every ID in the files is lowercase with its unit in the name",
        f"{len(ids)} IDs checked; not lowercase: {badid or 'none'}")

    # ---------- J converter feasibility: can the PoC settings be built from the setup?
    try:
        from cellpoc.settings import settings_from_dict
        raw = poc_settings_from_setup(S)
        settings_from_dict(raw)
        rec("J1", True, "The PoC settings can be built from this setup (renames per docs/naming.md) and are accepted by the PoC's own settings checker, so the setup really is a superset",
            f"PoC sections produced: {sorted(raw)}")
    except Exception as error:   # noqa: BLE001
        rec("J1", False, "The PoC settings can be built from this setup and are accepted by the PoC's own settings checker", str(error)[:200])

    # ---------- S self-tests: broken copies must be caught
    def mutate(doc, fn):
        c = copy.deepcopy(doc)
        fn(c)
        return c

    def drop_pick(d):
        d["actions"] = [a for a in d["actions"] if not (a["type"] == "pick" and a.get("object") == "vial" and a["step"] == "mix")]
    t1 = flow_problems(mutate(P, drop_pick)["actions"], L)
    rec("S1", any("shake" in p and "not holding" in p for p in t1), "Self-test: a plan that shakes the vial without picking it up is caught", t1[0] if t1 else "NOT CAUGHT")

    def long_wait(d):
        a = next(x for x in d["actions"] if x["type"] == "wait" and x["step"] == "press")
        a["type"], a["object"], a["from"] = "pick", "vial", "balance"
        d["actions"][d["actions"].index(a)] = a
    held_wait = [{"id": "A001", "type": "pick", "object": "vial", "from": "rack", "duration_s": 60}, {"id": "A002", "type": "wait", "reason": "x", "duration_s": 3600}]
    t2 = flow_problems(held_wait, L)
    rec("S2", any("through a 3600 s wait" in p for p in t2), "Self-test: holding something through a one-hour wait is caught", t2[0] if t2 else "NOT CAUGHT")

    def stretch(d):
        d["actions"][-1]["duration_s"] += 5
    t3 = step_sum_problems(mutate(P, stretch)["actions"], S, "duration_s")
    rec("S3", bool(t3) and not step_sum_problems(P["actions"], S, "duration_s"), "Self-test: a step that is 5 seconds too long is caught, while the real plan is within 1 second", t3[0] if t3 else "NOT CAUGHT")
    bad_name = mutate(P, lambda d: d["actions"][0].__setitem__("type", "tap_shake"))
    rec("S4", bool(schema_errors(schemas["plan"], bad_name)), "Self-test: the old action name 'tap_shake' (outside the ten) is rejected by the schema", (schema_errors(schemas["plan"], bad_name) or ["NOT CAUGHT"])[0])
    bad_event = mutate(P, lambda d: d["actions"].append({"id": "A999", "step": "clean", "phase": "adapt", "type": "event", "start_s": 14400, "duration_s": 1, "caption": "x"}))
    rec("S5", bool(schema_errors(schemas["plan"], bad_event)), "Self-test: an 'event' action in a plan is rejected", (schema_errors(schemas["plan"], bad_event) or ["NOT CAUGHT"])[0])
    bad_setup = mutate(S, lambda d: d["targets"]["constraints"].append({"response": "drug_pct", "label": "x", "unit": "%", "goal": "maximise"}))
    rec("S6", bool(schema_errors(schemas["setup"], bad_setup)), "Self-test: 'maximise' placed among the constraints is rejected", (schema_errors(schemas["setup"], bad_setup) or ["NOT CAUGHT"])[0])
    bad_path = mutate(S, lambda d: d["equipment"].__setitem__("layout_file", "../outside.json"))
    rec("S7", bool(schema_errors(schemas["setup"], bad_path)), "Self-test: a file reference containing '..' is rejected by the schema", (schema_errors(schemas["setup"], bad_path) or ["NOT CAUGHT"])[0])
    bad_rec = mutate(E, lambda d: d["actions"][-1].__setitem__("origin", "recovery"))
    rec("S8", bool(schema_errors(schemas["executed"], bad_rec)), "Self-test: a recovery action that does not say what it recovers is rejected", (schema_errors(schemas["executed"], bad_rec) or ["NOT CAUGHT"])[0])
    bad_row = dict(rows[0], status="failed")
    rec("S9", bool(schema_errors(schemas["row"], bad_row)), "Self-test: a 'failed' experiment row that still has results is rejected", (schema_errors(schemas["row"], bad_row) or ["NOT CAUGHT"])[0])
    rec("S10", weakest(["illustrative", "synthetic"]) == "synthetic" and weakest(["validated", "real"]) == "real" and weakest(["validated"]) == "validated",
        "Self-test: the 'weakest input' rule picks synthetic over illustrative over real over validated", "")
    far = mutate(L, lambda d: d["bottle_shelf"]["slots"][0]["position"].__setitem__("radius_m", 1.5))
    rec("S11", bool(reach_report(far)[2]), "Self-test: a bottle slot moved out to 1.5 m is caught as beyond the arm's reach", (reach_report(far)[2] or ["NOT CAUGHT"])[0])
    nounit = mutate(S, lambda d: d["ingredients"][0].pop("unit"))
    rec("S12", bool(numeric_without_unit(nounit)), "Self-test: an ingredient range with no unit is caught", (numeric_without_unit(nounit) or ["NOT CAUGHT"])[0])

    rec("S13", [reach_policy(x) for x in (0.12, 0.10, 0.08, 0.03, 0.02)] == ["pass", "pass", "warn", "warn", "fail"],
        "Self-test: the reach policy gives pass at 0.12 and 0.10 m, warning at 0.08 and 0.03 m, failure at 0.02 m", "")
    verdicts = []
    for radius in (1.30, 1.35, 1.37):
        moved = mutate(L, lambda d, r=radius: d["bottle_shelf"]["slots"][0]["position"].__setitem__("radius_m", r))
        verdicts.append(reach_policy(reach_report(moved)[0]))
    rec("S14", verdicts == ["warn", "warn", "fail"], "Self-test: a slot moved further out turns the layout from warning to failure as the spare reach shrinks",
        f"slot at 1.30 m: {verdicts[0]}, 1.35 m: {verdicts[1]}, 1.37 m: {verdicts[2]}")
    no_reason = mutate(P, lambda d: next(a for a in d["actions"] if a["type"] == "wait").__setitem__("reason", "wait"))
    vague = wait_reason_problems(no_reason["actions"])
    rec("S15", bool(vague) and not wait_reason_problems(P["actions"]), "Self-test: a wait whose reason is just 'wait' is caught", vague[0] if vague else "NOT CAUGHT")
    no_fr = mutate(S, lambda d: (d["targets"]["objectives"].__delitem__(0), d["targets"]["constraints"][2].__setitem__("required", False)))
    fp2 = friability_problems(no_fr, pa)
    rec("S16", bool(fp2) and not friability_problems(S, pa), "Self-test: a setup that no longer needs friability, with a plan that still measures it, is caught", fp2[0] if fp2 else "NOT CAUGHT")
    copy_bytes = (D / MASTER_COPIES[0]).read_bytes() + b"# edited"
    rec("S18", copy_bytes != (EXAMPLES / MASTER_COPIES[0]).read_bytes(), "Self-test: a docs copy that was edited by hand no longer equals the package copy, so it would be caught", "")
    tampered = mutate(E, lambda d: d["result"].__setitem__("hardness_kp", 6.5))
    rec("S17", make_trial_story.build_story(tampered, L, S) != story_now, "Self-test: changing a number in the timeline changes the story, so a stale story file would be caught", "")

    checklist.headline("These are example files and rules for review. Nothing here is used by the running program yet.")
    return checklist.print()


def poc_settings_from_setup(S: dict) -> dict:
    """A test-only mini converter: build the PoC's settings dictionary from the platform setup (renames per docs/naming.md)."""
    to_poc = {"drug_pct": "drug", "filler_pct": "filler", "binder_pct": "binder", "disintegrant_pct": "disintegrant", "lubricant_pct": "lubricant"}
    cons = {c["response"]: c for c in S["targets"]["constraints"]}
    steps = [{"name": "blend" if s["name"] == "mix" else s["name"], "label": s["label"], "duration_minutes": s["time_min"]} for s in S["equipment"]["steps"]]
    ph = S["equipment"]["phases"]
    noise = {n["quantity"]: n["sd"] for n in S["virtual_lab"]["noise"]}
    ren = lambda names: ["blend" if n == "mix" else n for n in names]   # noqa: E731
    return {
        "display": S["display"],
        "design_space": {"ingredients": {to_poc[i["id"]]: {"label": i["label"], "min": i["min"], "max": i["max"]} for i in S["ingredients"]}},
        "specifications": {
            "dissolution_30min": {"label": cons["dissolution_30min_pct"]["label"], "unit": cons["dissolution_30min_pct"]["unit"], "minimum": cons["dissolution_30min_pct"]["value"], "margin_scale": cons["dissolution_30min_pct"]["margin_scale"]},
            "hardness": {"label": cons["hardness_kp"]["label"], "unit": cons["hardness_kp"]["unit"], "minimum": cons["hardness_kp"]["low"], "maximum": cons["hardness_kp"]["high"]}},
        "cell": {"measurement_step": S["equipment"]["measurement_step"], "steps": steps,
                 "phases": {"act": ren(ph["act"]), "sense": ren(ph["sense"]), "reason_adapt_step": ph["reason_adapt_step"], "reason_minutes": ph["reason_min"]}},
        "run": {"start": S["calendar"]["start"], "duration_hours": S["calendar"]["duration_h"], "random_seed": S["seeds"]["run"]},
        "people": {"staffed_days": S["calendar"]["staffed_days"], "staffed_from": S["calendar"]["staffed_from"], "staffed_until": S["calendar"]["staffed_until"]},
        "virtual_lab": {"noise": {"dissolution_sd": noise["dissolution_30min_pct"], "hardness_sd": noise["hardness_kp"]}},
        "decision_engine": {"initial_recipes": S["engine"]["initial_recipes"], "candidates_per_decision": S["engine"]["candidates_per_decision"]},
        "scripted_faults": {"purge_minutes": S["faults"]["purge_min"], "clean_after_skip": S["faults"]["clean_after_skip"],
                            "events": [{"trial": x["trial"], "station": x["where"]["step"], "cause": x["cause"], "retry_succeeds": x["retry_succeeds"], "alert": f"{x['cause'].capitalize()} on trial {x['trial']}"} for x in S["faults"]["scripted"]]},
        "comparison": {"campaigns": S["comparison"]["campaigns"], "trials_per_campaign": S["comparison"]["trials_per_campaign"], "manual_baseline_trials_per_week": S["baseline"]["manual_trials_per_week"]},
    }


if __name__ == "__main__":
    sys.exit(main())
