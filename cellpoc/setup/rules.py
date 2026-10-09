"""The cross-field rules: things the schema cannot say, such as 'the lowest value must be below the highest',
'this recipe rule can never be met', 'no station in the layout can read this result'.

Each rule is a small function that looks at the whole setup and yields Problems with plain-English messages.
Every rule is written to cope with a setup of any shape (missing parts, wrong kinds of value): it skips what it
cannot judge, because the schema already reports a malformed part in its own words.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .files import path_is_safe, resolve_reference
from .layout_rules import measurable, reach_policy, reach_report, station_ids
from .messages import make_problem
from .problems import Problem
from .schema import fmt, shown
from .units import UNITS, compare

EXPECTED_STEPS = ["dispense", "mix", "press", "test", "clean"]


class Ctx:
    """What a rule can see: the setup, where it was loaded from, the project folder and the chosen layout."""

    def __init__(self, setup: dict, base_dir: Path | None, root: Path, layout: dict | None):
        self.s = setup
        self.base_dir = base_dir
        self.root = root
        self.layout = layout

    def make(self, rule_id: str, variant: str, path: tuple, /, **values) -> Problem:
        return make_problem(rule_id, variant, path, self.s, **values)


# ---------------------------------------------------------------- small helpers (all safe on any kind of value)
def sub(node, *keys):
    for key in keys:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None
    return node


def items(node, *keys) -> list[tuple[int, dict]]:
    found = sub(node, *keys)
    return [(i, x) for i, x in enumerate(found) if isinstance(x, dict)] if isinstance(found, list) else []


def num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def is_text(x) -> bool:
    return isinstance(x, str)


def with_unit(value, unit) -> str:
    if not is_text(unit) or not unit.strip():
        return fmt(value)
    return f"{fmt(value)}%" if unit.strip() == "%" else f"{fmt(value)} {unit.strip()}"


def name_of(item: dict, *keys: str, fallback: str = "") -> str:
    for key in keys:
        if is_text(item.get(key)) and item[key].strip():
            return item[key].strip()
    return fallback


def _ids(c: Ctx, *sections: str) -> set[str]:
    return {it["id"] for section in sections for _, it in items(c.s, section) if is_text(it.get("id"))}


# ---------------------------------------------------------------- 1 Project
def r_project(c: Ctx) -> Iterator[Problem]:
    status, banner = sub(c.s, "project", "data_status"), sub(c.s, "display", "banner")
    if status in ("synthetic", "illustrative") and is_text(banner):
        low = banner.lower()
        if "illustrative" not in low and "synthetic" not in low:
            yield c.make("R02", "", ("display", "banner"), status=status)
    if status in ("real", "validated"):
        yield c.make("R04", status, ("project", "data_status"))


# ---------------------------------------------------------------- 2 Ingredients, 3 Process and context
def r_ranges(c: Ctx) -> Iterator[Problem]:
    for section in ("ingredients", "process_factors"):
        for i, item in items(c.s, section):
            lo, hi = item.get("min"), item.get("max")
            if num(lo) and num(hi) and lo >= hi:
                unit = item.get("unit")
                yield c.make("R05", "", (section, i, "min"), lo=with_unit(lo, unit), hi=with_unit(hi, unit))


def r_balance(c: Ctx) -> Iterator[Problem]:
    ings = items(c.s, "ingredients")
    if ings:
        n = sum(1 for _, it in ings if it.get("role") == "balance")
        if n != 1:
            yield c.make("R07", "none" if n == 0 else "many", ("ingredients",), n=n)


def r_duplicate_ids(c: Ctx) -> Iterator[Problem]:
    seen: set[str] = set()
    for section in ("ingredients", "process_factors", "context_factors"):
        for i, item in items(c.s, section):
            ident = item.get("id")
            if is_text(ident):
                if ident in seen:
                    yield c.make("R08", "", (section, i, "id"), id=ident)
                seen.add(ident)


def r_balance_range(c: Ctx) -> Iterator[Problem]:
    ings = items(c.s, "ingredients")
    balances = [(i, it) for i, it in ings if it.get("role") == "balance"]
    if len(balances) != 1:
        return
    index, balance = balances[0]
    others = [it for _, it in ings if it.get("role") != "balance"]
    if not (num(balance.get("min")) and num(balance.get("max")) and all(num(o.get("min")) and num(o.get("max")) for o in others)):
        return
    lo = max(0.0, 100 - sum(o["max"] for o in others))
    hi = 100 - sum(o["min"] for o in others)
    values = dict(name=name_of(balance, "label", "id", fallback="balance ingredient").split(" (")[0].lower(),
                  lo=fmt(round(lo, 2)), hi=fmt(round(hi, 2)), bmin=fmt(balance["min"]), bmax=fmt(balance["max"]))
    if balance["max"] < lo or balance["min"] > hi or hi < 0:
        yield c.make("R09", "unreachable", ("ingredients", index, "min"), **values)
    elif balance["min"] > lo or balance["max"] < hi:
        yield c.make("R09", "narrower", ("ingredients", index, "min"), **values)


def r_recipe_rules(c: Ctx) -> Iterator[Problem]:
    listed = sub(c.s, "recipe_rules")
    rules = items(c.s, "recipe_rules")
    ingredients = {it["id"]: it for _, it in items(c.s, "ingredients") if is_text(it.get("id"))}
    if isinstance(listed, list):
        sums = [(i, r) for i, r in rules if r.get("rule") == "sum_to"]
        if not sums:
            yield c.make("R43", "missing", ("recipe_rules",))
        elif len(sums) > 1:
            yield c.make("R43", "many", ("recipe_rules", sums[1][0]))
        for i, rule in sums:
            if num(rule.get("total")) and rule["total"] != 100:
                yield c.make("R43", "total", ("recipe_rules", i, "total"), total=fmt(rule["total"]))
    for i, rule in rules:
        kind, listed_items = rule.get("rule"), rule.get("items")
        if kind not in ("at_most", "at_least") or not isinstance(listed_items, list):
            continue
        rule_name = name_of(rule, "label", fallback=f"Rule {i + 1}")
        known = []
        for ident in listed_items:
            if is_text(ident) and ident in ingredients:
                known.append(ingredients[ident])
            elif is_text(ident):
                yield c.make("R42", "", ("recipe_rules", i, "items"), rule=rule_name, id=ident)
        limit = rule.get("limit")
        if not num(limit) or not known:
            continue
        names = ", ".join(name_of(k, "label", "id", fallback="an ingredient") for k in known)
        if kind == "at_most" and all(num(k.get("min")) for k in known):
            total = sum(k["min"] for k in known)
            if total > limit:
                yield c.make("R11", "at_most", ("recipe_rules", i, "limit"), rule=rule_name, names=names, sum=fmt(round(total, 4)), limit=fmt(limit))
        if kind == "at_least" and all(num(k.get("max")) for k in known):
            total = sum(k["max"] for k in known)
            if total < limit:
                yield c.make("R11", "at_least", ("recipe_rules", i, "limit"), rule=rule_name, names=names, sum=fmt(round(total, 4)), limit=fmt(limit))


def _unit_problems(c: Ctx, rule: str, path: tuple, identifier, unit) -> Iterator[Problem]:
    if not is_text(identifier) or not is_text(unit):
        return
    verdict = compare(identifier, unit)
    if verdict.level == "ok":
        return
    if verdict.reason == "conflict":
        yield c.make(rule, "conflict", path, id=identifier, suffix=verdict.suffix_unit.suffix, suffix_name=verdict.suffix_unit.name,
                     unit=unit, unit_name=verdict.written_unit.name)
    elif verdict.reason == "unknown_unit":
        yield c.make(rule, "unknown_unit", path, unit=unit)
    elif verdict.reason == "no_suffix":
        yield c.make(rule, "no_suffix", path, id=identifier, examples=", ".join(u.suffix for u in UNITS[:5]))
    else:
        yield c.make(rule, "case", path, unit=unit, canonical=verdict.written_unit.symbol)


def r_process_units(c: Ctx) -> Iterator[Problem]:                       # R12
    for i, item in items(c.s, "process_factors"):
        yield from _unit_problems(c, "R12", ("process_factors", i, "unit"), item.get("id"), item.get("unit"))


# ---------------------------------------------------------------- 4 Targets
def r_targets(c: Ctx) -> Iterator[Problem]:
    constraints = items(c.s, "targets", "constraints")
    for i, target in constraints:
        if target.get("goal") == "between" and num(target.get("low")) and num(target.get("high")) and target["low"] >= target["high"]:
            yield c.make("R14", "", ("targets", "constraints", i, "low"),
                         low=with_unit(target["low"], target.get("unit")), high=with_unit(target["high"], target.get("unit")))
        yield from _unit_problems(c, "R19", ("targets", "constraints", i, "unit"), target.get("response"), target.get("unit"))
    for i, target in items(c.s, "targets", "objectives"):
        yield from _unit_problems(c, "R19", ("targets", "objectives", i, "unit"), target.get("quantity"), target.get("unit"))
    if constraints and not any(t.get("required", True) is not False for _, t in constraints):
        yield c.make("R16", "", ("targets", "constraints"))


def r_measurable(c: Ctx) -> Iterator[Problem]:
    if c.layout is None:
        return
    readable = measurable(c.layout)
    inputs = _ids(c, "ingredients", "process_factors")
    for i, target in items(c.s, "targets", "constraints"):
        quantity = target.get("response")
        if is_text(quantity) and quantity not in inputs and quantity not in readable:
            name = name_of(target, "label", fallback=quantity)
            if target.get("required", True) is False:
                yield c.make("R17", "optional", ("targets", "constraints", i, "response"), name=name)
            else:
                yield c.make("R17", "needed", ("targets", "constraints", i, "response"), name=name, why="a required target")
    for i, target in items(c.s, "targets", "objectives"):
        quantity = target.get("quantity")
        if is_text(quantity) and quantity not in inputs and quantity not in readable:
            yield c.make("R17", "needed", ("targets", "objectives", i, "quantity"), name=name_of(target, "label", fallback=quantity), why="an objective")


def r_objectives(c: Ctx) -> Iterator[Problem]:
    seen: dict[str, list[tuple[int, str, dict]]] = {}
    for i, target in items(c.s, "targets", "objectives"):
        if is_text(target.get("quantity")) and target.get("goal") in ("maximise", "minimise"):
            seen.setdefault(target["quantity"], []).append((i, target["goal"], target))
    for quantity, entries in seen.items():
        if len({goal for _, goal, _ in entries}) == 2:
            yield c.make("R18", "", ("targets", "objectives", entries[1][0], "goal"), name=name_of(entries[0][2], "label", fallback=quantity))


# ---------------------------------------------------------------- 5 Equipment
def r_steps(c: Ctx) -> Iterator[Problem]:
    listed = sub(c.s, "equipment", "steps")
    steps = items(c.s, "equipment", "steps")
    names = [it.get("name") for _, it in steps]
    present = {n for n in names if is_text(n)}
    if isinstance(listed, list) and steps and all(is_text(n) and n in EXPECTED_STEPS for n in names) and names != EXPECTED_STEPS:
        yield c.make("R47", "", ("equipment", "steps"), found=", ".join(names))
    phases = sub(c.s, "equipment", "phases")
    if isinstance(phases, dict) and steps:
        for key in ("act", "sense"):
            for step in phases.get(key) if isinstance(phases.get(key), list) else []:
                if is_text(step) and step in EXPECTED_STEPS and step not in present:
                    yield c.make("R45", "phase", ("equipment", "phases", key), step=step)
        last = phases.get("reason_adapt_step")
        if is_text(last) and last in EXPECTED_STEPS:
            if last not in present:
                yield c.make("R45", "phase", ("equipment", "phases", "reason_adapt_step"), step=last)
            elif names and names[-1] != last:
                yield c.make("R23", "", ("equipment", "phases", "reason_adapt_step"), step=last, last=names[-1])
            reason = phases.get("reason_min")
            total = next((it.get("time_min") for _, it in steps if it.get("name") == last), None)
            if num(reason) and num(total) and reason >= total:
                label = next((name_of(it, "label", "name") for _, it in steps if it.get("name") == last), last)
                yield c.make("R22", "", ("equipment", "phases", "reason_min"), reason=fmt(reason), step=label, total=f"{fmt(total)} minutes")
    measurement = sub(c.s, "equipment", "measurement_step")
    if steps and is_text(measurement) and measurement in EXPECTED_STEPS and measurement not in present:
        yield c.make("R45", "measurement", ("equipment", "measurement_step"), step=measurement)


def r_stations(c: Ctx) -> Iterator[Problem]:
    if c.layout is None:
        return
    available = station_ids(c.layout)
    for i, step in items(c.s, "equipment", "steps"):
        for station in step.get("stations") if isinstance(step.get("stations"), list) else []:
            if is_text(station) and station not in available:
                yield c.make("R21", "", ("equipment", "steps", i, "stations"), station=station, stations=", ".join(available))


def r_reach(c: Ctx) -> Iterator[Problem]:
    if c.layout is None:
        return
    spare, where, out_of_reach = reach_report(c.layout)
    path = ("equipment", "layout_file")
    if out_of_reach:
        yield c.make("R24", "beyond", path, where=out_of_reach[0])
        return
    verdict = reach_policy(spare)
    if verdict == "fail":
        yield c.make("R24", "very_tight", path, margin=f"{spare:.3f}", where=where)
    elif verdict == "warn":
        yield c.make("R24", "tight", path, margin=f"{spare:.3f}", where=where)


# ---------------------------------------------------------------- 6 Calendar
def _clock(text):
    try:
        return datetime.strptime(text, "%H:%M").time()
    except (ValueError, TypeError):
        return None


def r_calendar(c: Ctx) -> Iterator[Problem]:
    cal = sub(c.s, "calendar")
    if not isinstance(cal, dict):
        return
    start = cal.get("start")
    if is_text(start) and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", start):
        try:
            datetime.strptime(start, "%Y-%m-%d %H:%M")
        except ValueError:
            yield c.make("R28", "", ("calendar", "start"), shown=shown(start))
    times = {}
    for key in ("staffed_from", "staffed_until"):
        value = cal.get(key)
        if is_text(value) and re.fullmatch(r"\d{2}:\d{2}", value):
            times[key] = _clock(value)
            if times[key] is None:
                yield c.make("R53", "", ("calendar", key), shown=shown(value))
    if times.get("staffed_from") and times.get("staffed_until") and times["staffed_from"] >= times["staffed_until"]:
        yield c.make("R26", "", ("calendar", "staffed_from"), start=cal["staffed_from"], end=cal["staffed_until"])
    duration = cal.get("duration_h")
    minutes = [it.get("time_min") for _, it in items(c.s, "equipment", "steps")]
    if num(duration) and minutes and all(num(m) for m in minutes) and sum(minutes) > 0 and duration * 60 < sum(minutes):
        yield c.make("R27", "", ("calendar", "duration_h"), run=fmt(duration), trial=fmt(round(sum(minutes) / 60, 2)))


# ---------------------------------------------------------------- 7 Faults
def r_faults(c: Ctx) -> Iterator[Problem]:
    trials = sub(c.s, "comparison", "trials_per_campaign")
    ingredients = _ids(c, "ingredients")
    present = {it.get("name") for _, it in items(c.s, "equipment", "steps") if is_text(it.get("name"))}
    seen: set = set()
    for section in ("scripted", "random"):
        for i, fault in items(c.s, "faults", section):
            where = fault.get("where") if isinstance(fault.get("where"), dict) else {}
            if where.get("action") == "pour" and not is_text(where.get("ingredient")):
                yield c.make("R31", "pour_needs_ingredient", ("faults", section, i, "where", "ingredient"))
            if is_text(where.get("ingredient")) and ingredients and where["ingredient"] not in ingredients:
                yield c.make("R31", "unknown_ingredient", ("faults", section, i, "where", "ingredient"), ingredient=where["ingredient"])
            if is_text(where.get("step")) and where["step"] in EXPECTED_STEPS and present and where["step"] not in present:
                yield c.make("R48", "", ("faults", section, i, "where", "step"), step=where["step"])
            if section == "scripted" and num(fault.get("trial")):
                if num(trials) and fault["trial"] > trials:
                    yield c.make("R29", "", ("faults", section, i, "trial"), trial=fmt(fault["trial"]), trials=fmt(trials))
                if fault["trial"] in seen:
                    yield c.make("R30", "", ("faults", section, i, "trial"), trial=fmt(fault["trial"]))
                seen.add(fault["trial"])


# ---------------------------------------------------------------- 8 Baseline and engine
def r_engine(c: Ctx) -> Iterator[Problem]:
    starting, trials = sub(c.s, "engine", "initial_recipes"), sub(c.s, "comparison", "trials_per_campaign")
    if num(starting) and num(trials) and starting > trials:
        yield c.make("R33", "", ("engine", "initial_recipes"), n=fmt(starting), trials=fmt(trials))


def r_noise(c: Ctx) -> Iterator[Problem]:
    results = {t.get("response") for _, t in items(c.s, "targets", "constraints") if is_text(t.get("response"))}
    if c.layout is not None:
        results |= measurable(c.layout)
    for i, noise in items(c.s, "virtual_lab", "noise"):
        quantity = noise.get("quantity")
        if is_text(quantity) and results and quantity not in results:
            yield c.make("R35", "", ("virtual_lab", "noise", i, "quantity"), quantity=quantity, results=", ".join(sorted(results)))


# ---------------------------------------------------------------- 9 Data
def _header(path: Path) -> list[str] | None:
    try:
        with open(path, "rb") as handle:
            first = handle.read(100_000).decode("utf-8-sig", errors="replace")
        return next(csv.reader(io.StringIO(first, newline="")), None)
    except (OSError, csv.Error):
        return None


def r_data(c: Ctx) -> Iterator[Problem]:
    data = sub(c.s, "data")
    if not isinstance(data, dict):
        return
    found: dict[str, Path | None] = {}
    for key, variant in (("experiments_file", "experiments"), ("meta_file", "meta")):
        reference = data.get(key)
        if is_text(reference) and path_is_safe(reference):
            found[key] = resolve_reference(reference, c.base_dir, c.root)
            if found[key] is None:
                yield c.make("R36", variant, ("data", key), ref=reference)
    table = found.get("experiments_file")
    mapping = data.get("column_map") if isinstance(data.get("column_map"), dict) else {}
    header = _header(table) if table else None
    if header is not None:
        wanted: list[tuple[str, tuple]] = [(k, ("data", "column_map")) for k in mapping]
        for key, value in (data.get("id_columns") if isinstance(data.get("id_columns"), dict) else {}).items():
            wanted.append((value, ("data", "id_columns", key)))
        for section, keys in (("hardness", ("value_column", "unit_column")), ("below_detection", ("note_column",)), ("failed_runs", ("status_column",))):
            block = data.get(section)
            for key in keys if isinstance(block, dict) else ():
                wanted.append((block.get(key), ("data", section, key)))
        reported: set = set()
        for column, path in wanted:
            if is_text(column) and column not in header and column not in reported:
                reported.add(column)
                have = ", ".join(header[:6]) + (", ..." if len(header) > 6 else "")
                yield c.make("R37", "", path, column=column, have=have)
    hardness = data.get("hardness") if isinstance(data.get("hardness"), dict) else {}
    if mapping:
        covered = {v for v in mapping.values() if is_text(v)} | ({hardness["to"]} if is_text(hardness.get("to")) else set())
        needs: dict[str, str] = {}
        for section, why in (("ingredients", "it is an ingredient"), ("process_factors", "it is a process setting")):
            for _, item in items(c.s, section):
                if is_text(item.get("id")):
                    needs.setdefault(item["id"], why)
        for _, target in items(c.s, "targets", "constraints"):
            if is_text(target.get("response")):
                needs.setdefault(target["response"], "it is a target")
        for _, target in items(c.s, "targets", "objectives"):
            if is_text(target.get("quantity")):
                needs.setdefault(target["quantity"], "it is an objective")
        for ident, why in needs.items():
            if ident not in covered:
                yield c.make("R38", "", ("data", "column_map"), id=ident, why=why)
        first_column: dict[str, str] = {}
        for column, ident in mapping.items():
            if is_text(ident):
                if ident in first_column:
                    yield c.make("R39", "", ("data", "column_map", column), first=first_column[ident], second=column, id=ident)
                first_column.setdefault(ident, column)
        used = (_ids(c, "ingredients", "process_factors", "context_factors") | set(needs) | covered & {hardness.get("to")})
        for column, ident in mapping.items():
            if is_text(ident) and ident not in used:
                yield c.make("R54", "", ("data", "column_map", column), column=column, id=ident)
    conversions = hardness.get("conversions")
    if isinstance(conversions, dict):
        if "kP" not in conversions:
            yield c.make("R40", "missing_kp", ("data", "hardness", "conversions"))
        newtons = conversions.get("N")
        if isinstance(newtons, dict) and num(newtons.get("divide_by")) and abs(newtons["divide_by"] - 9.807) > 0.001:
            yield c.make("R50", "newtons", ("data", "hardness", "conversions", "N"), value=fmt(newtons["divide_by"]))
    meta = found.get("meta_file")
    if meta:
        try:
            status = json.loads(meta.read_bytes().decode("utf-8-sig")).get("data_status")
        except (OSError, ValueError, AttributeError):
            status = None
        if is_text(status):
            yield c.make("R41", "", ("data", "meta_file"), status=status)


SEMANTIC_RULES = [r_project, r_ranges, r_balance, r_duplicate_ids, r_balance_range, r_recipe_rules, r_process_units, r_targets,
                  r_measurable, r_objectives, r_steps, r_stations, r_reach, r_calendar, r_faults, r_engine, r_noise, r_data]
