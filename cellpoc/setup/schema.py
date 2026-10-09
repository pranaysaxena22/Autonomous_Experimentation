"""Runs the setup schema over a setup and turns every finding into a plain-English Problem.

Specific wording is used where the setup app knows what the person was doing (a name, a colour, a batch size,
an ingredient range ...); anything else gets one of the generic messages (S01 to S11). No technical wording ever
reaches a person: the library's own messages are never shown.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .messages import make_problem
from .problems import Problem

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "formats" / "schemas"

KIND_WORDS = {"number": "a number", "integer": "a whole number", "string": "text", "array": "a list",
              "object": "a group of settings", "boolean": "true or false", "null": "empty"}
BOUND_WORDS = {"minimum": "at least", "exclusiveMinimum": "more than", "maximum": "at most", "exclusiveMaximum": "less than"}


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_bytes().decode("utf-8-sig"))


def options_at(path: tuple, schema_name: str = "setup.schema.json") -> list[str]:
    """The allowed choices for a field (or for the items of a list field), read from the schema so screens never repeat them."""
    schema = load_schema(schema_name)

    def deref(node: dict) -> dict:
        while "$ref" in node:
            target = schema
            for part in node["$ref"][2:].split("/"):
                target = target[part]
            node = target
        return node

    node = schema
    for part in path:
        node = deref(node)
        node = node["items"] if isinstance(part, int) else node["properties"][part]
    node = deref(node)
    if "enum" not in node and isinstance(node.get("items"), dict):
        node = deref(node["items"])
    return list(node["enum"])


def fmt(value) -> str:
    """A number written the way a person would: 12 not 12.0, and no technical words for odd values."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}" if math.isfinite(value) else "an invalid number"
    return str(value)


def shown(value) -> str:
    """What the person wrote, in a few characters, with no technical words."""
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return fmt(value)
    if isinstance(value, str):
        return "'" + (value if len(value) <= 40 else value[:37] + "...") + "'"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a group of settings"
    return "something else"


def _kind(types) -> str:
    names = [types] if isinstance(types, str) else list(types)
    return " or ".join(KIND_WORDS.get(n, "a different kind of value") for n in names)


def _spec_key(path: tuple) -> str:
    return ".".join("*" if isinstance(p, int) else str(p) for p in path)


def translate(error, setup) -> list[Problem]:
    path = tuple(error.absolute_path)
    check = error.validator
    instance = error.instance
    key = _spec_key(path)
    out: list[Problem] = []

    def make(rule, variant, where=path, **values):
        out.append(make_problem(rule, variant, where, setup, **values))

    pattern = error.schema.get("pattern", "") if isinstance(error.schema, dict) else ""

    # ---- specific wording where we know what the person is doing
    if key == "project.name":
        make("R01", "long", n=len(instance)) if check == "maxLength" and isinstance(instance, str) else make("R01", "")
    elif key == "display.accent_colour" and check in ("pattern", "type"):
        make("R03", "", shown=shown(instance))
    elif key in ("ingredients.*.min", "ingredients.*.max") and check in ("minimum", "maximum"):
        make("R06", "", shown=fmt(instance) + "%")
    elif key == "batch_size_g" and check in ("exclusiveMinimum", "minimum"):
        make("R10", "", shown=shown(instance))
    elif key == "batch_size_g" and check == "type":
        make("R10", "type", shown=shown(instance))
    elif key == "targets.constraints.*" and check == "required":
        goal = instance.get("goal") if isinstance(instance, dict) else None
        if goal in ("at_least", "at_most", "between"):
            make("R15", goal)
        else:
            make("S01", "")
    elif key == "equipment.steps.*.time_min" and check in ("exclusiveMinimum", "minimum"):
        make("R20", "", shown=shown(instance))
    elif "\\.\\." in pattern:
        make("R25", "", shown=shown(instance))
    elif key == "calendar.start" and check == "pattern":
        make("R28", "", shown=shown(instance))
    elif key in ("calendar.staffed_from", "calendar.staffed_until") and check == "pattern":
        make("R53", "", shown=shown(instance))
    elif key in ("faults.random.*.chance_per_trial", "faults.random.*.retry_succeeds_chance") and check in ("minimum", "maximum"):
        example = (f"Write {fmt(instance / 100)} for {fmt(instance)}%." if isinstance(instance, (int, float)) and 1 < instance <= 100
                   else "Write a number from 0 to 1, for example 0.05 for 5%.")
        make("R32", "", shown=shown(instance), example=example)
    elif key == "baseline.manual_trials_per_week" and check in ("exclusiveMinimum", "minimum"):
        make("R34", "", shown=shown(instance))
    elif key == "context_factors.*.values" and check == "minItems":
        make("R13", "empty")
    elif key == "context_factors.*.values" and check == "uniqueItems":
        listed = ", ".join(str(x) for x in instance) if isinstance(instance, list) else ""
        make("R13", "repeats", shown="'" + listed + "'")
    # ---- generic wording for everything else
    elif check == "required":
        for name in error.validator_value:
            if isinstance(instance, dict) and name not in instance:
                make("S01", "", path + (name,))
    elif check == "additionalProperties":
        known = set(error.schema.get("properties", {}))
        for name in sorted(str(k) for k in instance if k not in known) if isinstance(instance, dict) else []:
            make("S07", "", name=name)
    elif check == "type":
        make("S02", "", kind=_kind(error.validator_value), shown=shown(instance))
    elif check == "enum":
        make("S03", "", options=", ".join(str(o) for o in error.validator_value), shown=shown(instance))
    elif check == "const":
        make("S11", "", expected=shown(error.validator_value), shown=shown(instance))
    elif check in BOUND_WORDS:
        make("S04", "", bound=BOUND_WORDS[check], limit=fmt(error.validator_value), shown=shown(instance))
    elif check == "minLength":
        make("S05", "empty")
    elif check == "maxLength":
        make("S05", "long", n=len(instance) if isinstance(instance, str) else 0, limit=error.validator_value)
    elif check == "pattern":
        variant = "id" if pattern.startswith("^[a-z]") else "other"
        make("S06", variant, shown=shown(instance))
    elif check == "minItems":
        n = error.validator_value
        make("S08", "", n=n, s="" if n == 1 else "s", have=len(instance) if isinstance(instance, list) else 0)
    elif check == "uniqueItems":
        make("S09", "")
    else:
        make("S10", "")
    return out


def schema_problems(setup, schema_name: str = "setup.schema.json") -> list[Problem]:
    """Every structural problem in a setup, in plain English, without repeats."""
    validator = Draft202012Validator(load_schema(schema_name))
    errors = sorted(validator.iter_errors(setup), key=lambda e: [str(p) for p in e.absolute_path])
    seen: set = set()
    problems: list[Problem] = []
    for error in errors:
        for problem in translate(error, setup):
            ident = (problem.rule, problem.variant, problem.path, problem.text)
            if ident not in seen:
                seen.add(ident)
                problems.append(problem)
    return problems
