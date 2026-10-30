"""The cross-field rules: things the schema cannot say, such as 'the lowest value must be below the highest',
'this recipe rule can never be met', 'no station in the layout can read this result'.

Each rule is a small function that looks at the whole setup and yields Problems with plain-English messages.
Every rule is written to cope with a setup of any shape (missing parts, wrong kinds of value): it skips what it
cannot judge, because the schema already reports a malformed part in its own words.
"""
from __future__ import annotations

import codecs
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
from .tablefile import EXCEL_SUFFIXES, match_key, normalise_name, read_header
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
DATE_PIECES = ("month", "yyyy", "mon", "yy", "mm", "dd")        # longer pieces first, so 'month' is not read as 'mon'


def date_pieces(text: str) -> tuple[list[str] | None, str]:
    """Split a date format such as 'dd.mm.yyyy' into its pieces. (None, the unknown part) if something in it is not a known piece."""
    rest, pieces = text.strip().lower(), []
    while rest:
        if rest[0] in "./- ":
            rest = rest[1:]
            continue
        for piece in DATE_PIECES:
            if rest.startswith(piece):
                pieces.append(piece)
                rest = rest[len(piece):]
                break
        else:
            return None, rest[:8]
    return pieces, ""


def _joins(c: Ctx, data: dict) -> list[tuple[int, dict, Path | None]]:
    """The other files the setup joins in: (position, the join, where the file is or None)."""
    found = []
    for i, join in items(data, "joins"):
        reference = join.get("file")
        found.append((i, join, resolve_reference(reference, c.base_dir, c.root) if is_text(reference) and path_is_safe(reference) else None))
    return found


def r_data(c: Ctx) -> Iterator[Problem]:
    data = sub(c.s, "data")
    if not isinstance(data, dict):
        return
    found: dict[str, Path | None] = {}
    for key, variant in (("experiments_file", "experiments"), ("meta_file", "meta")):
        reference = data.get(key)
        if is_text(reference) and reference.strip() and path_is_safe(reference):
            found[key] = resolve_reference(reference, c.base_dir, c.root)
            if found[key] is None:
                yield c.make("R36", variant, ("data", key), ref=reference)
    joins = _joins(c, data)
    for i, join, where in joins:
        if where is None and is_text(join.get("file")) and path_is_safe(join["file"]):
            yield c.make("R36", "join", ("data", "joins", i, "file"), ref=join["file"])
    table = found.get("experiments_file")
    mapping = data.get("column_map") if isinstance(data.get("column_map"), dict) else {}
    main = read_header(table, data) if table else None
    if main is not None:
        main_keys = {match_key(n) for n in main.names}
        available = set(main_keys)
        for i, join, where in joins:
            joined = read_header(where, {k: v for k, v in data.items() if k in ("encoding", "delimiter", "sheet")}) if where else None
            if joined is None:
                continue
            on = items(join, "on")
            key_names = {match_key(pair["joined"]) for _, pair in on if is_text(pair.get("joined"))}
            joined_keys = {match_key(n) for n in joined.names}
            for j, pair in on:
                if is_text(pair.get("main")) and match_key(pair["main"]) not in main_keys:
                    yield c.make("R60", "main_key", ("data", "joins", i, "on", j, "main"), column=pair["main"], file=table.name)
                if is_text(pair.get("joined")) and match_key(pair["joined"]) not in joined_keys:
                    yield c.make("R60", "joined_key", ("data", "joins", i, "on", j, "joined"), column=pair["joined"], file=where.name)
            prefix = join.get("prefix") if is_text(join.get("prefix")) else ""
            added = {match_key(prefix + n) for n in joined.names if normalise_name(n) and match_key(n) not in key_names}
            clash = sorted(added & available)
            if clash:
                yield c.make("R60", "clash", ("data", "joins", i, "file"), file=where.name, column=clash[0])
            available |= added
        wanted: list[tuple[str, tuple]] = [(k, ("data", "column_map")) for k in mapping]
        for key, value in (data.get("id_columns") if isinstance(data.get("id_columns"), dict) else {}).items():
            wanted.append((value, ("data", "id_columns", key)))
        for section, keys in (("hardness", ("value_column", "unit_column")), ("below_detection", ("note_column",)), ("failed_runs", ("status_column",))):
            block = data.get(section)
            for key in keys if isinstance(block, dict) else ():
                wanted.append((block.get(key), ("data", section, key)))
        reported: set = set()
        for column, path in wanted:
            if is_text(column) and column.strip() and match_key(column) not in available and match_key(column) not in reported:
                reported.add(match_key(column))
                have = ", ".join(normalise_name(n) for n in main.names[:6]) + (", ..." if len(main.names) > 6 else "")
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
        used = (_ids(c, "ingredients", "process_factors", "context_factors") | set(needs)
                | ({hardness["to"]} if is_text(hardness.get("to")) else set()))
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
    yield from _reading_settings(c, data, table)
    yield from _cleaning_settings(c, data)
    yield from _validation_settings(c, data)


def _validation_settings(c: Ctx, data: dict) -> Iterator[Problem]:
    """The modelling section: the names it uses must be columns this setup produces, and a result is never also an input."""
    validation = data.get("validation")
    if not isinstance(validation, dict):
        return
    column_map = data.get("column_map")
    mapped = {v for v in column_map.values() if is_text(v)} if isinstance(column_map, dict) else set()
    hardness = data.get("hardness") if isinstance(data.get("hardness"), dict) else {}
    id_columns = data.get("id_columns") if isinstance(data.get("id_columns"), dict) else {}
    # what the cleaned table holds: mapped IDs, the hardness result, the identifying columns and the setup's own quantities
    produced = {match_key(x) for x in mapped | {"experiment_id", "replicate_no", "batch_id", "date", "status", "failure_reason", "source_row"}}
    produced |= {match_key(hardness["to"])} if is_text(hardness.get("to")) else set()
    produced |= {match_key(x) for x in _ids(c, "ingredients", "process_factors", "context_factors")}
    produced |= {match_key(v) for v in id_columns.values() if is_text(v)}
    composition = data.get("composition")
    if isinstance(composition, dict) and is_text(composition.get("total_weight")):     # amounts in mg also arrive as a percentage of the total weight
        suffix = composition.get("amount_suffix") if is_text(composition.get("amount_suffix")) and composition["amount_suffix"] else "_mg"
        percent = next(u.suffix for u in UNITS if u.symbol == "%")       # the unit list stays in one place (units.py)
        produced |= {match_key(x[:-len(suffix)] + percent) for x in mapped if x.endswith(suffix) and x != composition["total_weight"]}
    for _, target in items(c.s, "targets", "constraints"):
        produced |= {match_key(target["response"])} if is_text(target.get("response")) else set()
    known = bool(mapped)

    def unknown(path: tuple, variant: str, name) -> Iterator[Problem]:
        if known and is_text(name) and name.strip() and match_key(name) not in produced:
            yield c.make("R69", variant, path, name=name)

    responses = validation.get("responses") if isinstance(validation.get("responses"), list) else []
    inputs = validation.get("inputs") if isinstance(validation.get("inputs"), list) else []
    for i, name in enumerate(responses):
        yield from unknown(("data", "validation", "responses", i), "response", name)
    for i, name in enumerate(inputs):
        yield from unknown(("data", "validation", "inputs", i), "input", name)
        if is_text(name) and name in responses:
            yield c.make("R70", "", ("data", "validation", "inputs", i), name=name)
    for i, item in items(validation, "left_out"):
        yield from unknown(("data", "validation", "left_out", i, "id"), "left_out", item.get("id"))
        if is_text(item.get("id")) and (item["id"] in responses or item["id"] in inputs):
            yield c.make("R73", "", ("data", "validation", "left_out", i, "id"), name=item["id"])
    derived = validation.get("derived_from") if isinstance(validation.get("derived_from"), dict) else {}
    for key, sources in derived.items():
        yield from unknown(("data", "validation", "derived_from", key), "derived", key)
        for source in sources if isinstance(sources, list) else []:
            yield from unknown(("data", "validation", "derived_from", key), "derived", source)
            if source == key:
                yield c.make("R72", "", ("data", "validation", "derived_from", key), name=key)
    groups = validation.get("groups") if isinstance(validation.get("groups"), dict) else {}
    for kind, group in groups.items():
        if not isinstance(group, dict):
            continue
        columns = group.get("column") if isinstance(group.get("column"), list) else [group.get("column")]
        for name in columns:
            yield from unknown(("data", "validation", "groups", kind, "column"), "group", name)
        if kind == "supplier" and not isinstance(group.get("confirmed"), bool):
            yield c.make("R71", "", ("data", "validation", "groups", "supplier", "confirmed"))


def _cleaning_settings(c: Ctx, data: dict) -> Iterator[Problem]:
    """The settings that say how values are cleaned: composition (mg to percent), assumed units, the fixed hardness unit, below-detection."""
    column_map = data.get("column_map")
    mapped = {v for v in column_map.values() if is_text(v)} if isinstance(column_map, dict) else set()
    composition = data.get("composition")
    if isinstance(composition, dict) and is_text(composition.get("total_weight")):
        total = composition["total_weight"]
        suffix = composition.get("amount_suffix") if is_text(composition.get("amount_suffix")) and composition["amount_suffix"] else "_mg"
        if mapped and total not in mapped:
            yield c.make("R64", "weight_not_mapped", ("data", "composition", "total_weight"), id=total)
        elif not total.endswith(suffix):
            yield c.make("R64", "suffix_mismatch", ("data", "composition", "total_weight"), id=total, suffix=suffix)
        if mapped and not [m for m in mapped if m.endswith(suffix) and m != total]:
            yield c.make("R64", "no_amounts", ("data", "composition"), suffix=suffix)
    assumed = data.get("assumed_units")
    if isinstance(assumed, list) and mapped:
        for i, item in items(data, "assumed_units"):
            if is_text(item.get("id")) and item["id"] not in mapped:
                yield c.make("R65", "", ("data", "assumed_units", i, "id"), id=item["id"])
    hardness = data.get("hardness")
    if isinstance(hardness, dict):
        unit, conversions = hardness.get("unit"), hardness.get("conversions")
        if is_text(unit) and unit.strip():
            if isinstance(conversions, dict) and unit not in conversions:
                yield c.make("R66", "no_conversion", ("data", "hardness", "unit"), unit=unit)
            if is_text(hardness.get("unit_column")) and hardness["unit_column"].strip():
                yield c.make("R66", "both", ("data", "hardness", "unit"))
    replicates = data.get("replicates")
    if isinstance(replicates, dict) and isinstance(replicates.get("group_by"), list):
        id_columns = data.get("id_columns") if isinstance(data.get("id_columns"), dict) else {}
        allowed = {"experiment_id", "replicate_no", "batch_id", "date", "status", "failure_reason", "source_row"} | mapped
        allowed |= {match_key(k) for k in (column_map if isinstance(column_map, dict) else {})} | {match_key(v) for v in id_columns.values() if is_text(v)}
        allowed = {match_key(a) for a in allowed}
        for i, entry in enumerate(replicates["group_by"]):
            if is_text(entry) and entry.strip() and match_key(entry) not in allowed:
                yield c.make("R68", "", ("data", "replicates", "group_by", i), name=entry)
    below = data.get("below_detection")
    if isinstance(below, dict) and is_text(below.get("note_column")) and below["note_column"].strip():
        missing = [name for name in ("marker", "quantity", "limit") if below.get(name) in (None, "")]
        if missing:
            yield c.make("R67", "", ("data", "below_detection"), missing=", ".join(missing))


def _reading_settings(c: Ctx, data: dict, table: Path | None) -> Iterator[Problem]:
    """The settings that say how to read the file: separator, decimal mark, encoding, sheet, dates, missing markers, units."""
    if data.get("delimiter") == "comma" and data.get("decimal") == "comma":
        yield c.make("R55", "", ("data", "decimal"))
    encoding = data.get("encoding")
    if is_text(encoding) and encoding.strip().lower() not in ("auto", ""):
        try:
            codecs.lookup(encoding.strip())
        except LookupError:
            yield c.make("R63", "", ("data", "encoding"), encoding=encoding)
    sheet = data.get("sheet")
    if is_text(sheet) and sheet.strip() and table is not None and table.suffix.lower() not in EXCEL_SUFFIXES:
        yield c.make("R62", "", ("data", "sheet"), sheet=sheet, file=table.name)
    date = data.get("date")
    if isinstance(date, dict):
        pieces, unknown = date_pieces(date["format"]) if is_text(date.get("format")) and date["format"].strip() else (None, "")
        if is_text(date.get("format")) and date["format"].strip():
            if pieces is None:
                yield c.make("R56", "unknown_piece", ("data", "date", "format"), shown=shown(date["format"]), piece=unknown)
            else:
                if not any(p in pieces for p in ("mm", "mon", "month")):
                    yield c.make("R56", "no_month", ("data", "date", "format"), shown=shown(date["format"]))
                if not any(p in pieces for p in ("yyyy", "yy")):
                    yield c.make("R56", "no_year", ("data", "date", "format"), shown=shown(date["format"]))
                if len(pieces) != len(set(pieces)):
                    yield c.make("R56", "repeated", ("data", "date", "format"), shown=shown(date["format"]))
        months = date.get("months")
        if isinstance(months, list) and all(is_text(m) for m in months):
            if len(months) != 12 or len({m.strip().casefold() for m in months}) != 12:
                yield c.make("R57", "", ("data", "date", "months"), n=len(months))
    markers = data.get("missing_markers")
    if isinstance(markers, list):
        for i, marker in enumerate(markers):
            if is_text(marker) and marker and not marker.strip():
                yield c.make("R58", "", ("data", "missing_markers", i))
    units = data.get("column_units")
    if isinstance(units, dict):
        mapped = {v for v in (data.get("column_map") or {}).values() if is_text(v)} if isinstance(data.get("column_map"), dict) else set()
        used = _ids(c, "ingredients", "process_factors", "context_factors") | mapped
        for ident, unit in units.items():
            if is_text(ident) and is_text(unit):
                yield from _unit_problems(c, "R59", ("data", "column_units", ident), ident, unit)
                if used and ident not in used:
                    yield c.make("R59", "unused_id", ("data", "column_units", ident), id=ident)


SEMANTIC_RULES = [r_project, r_ranges, r_balance, r_duplicate_ids, r_balance_range, r_recipe_rules, r_process_units, r_targets,
                  r_measurable, r_objectives, r_steps, r_stations, r_reach, r_calendar, r_faults, r_engine, r_noise, r_data]
