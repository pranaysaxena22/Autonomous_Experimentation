"""Mutation test: break the example setup in 200 random ways and make sure the validator copes.

Each mutation deletes a field, swaps a value for one of a different type, writes junk, swaps two values, repeats a list
item or removes one. For every broken setup the validator must
  - never crash (strict mode: a rule that fails unexpectedly counts as a crash),
  - always return plain messages (the same wording test as the rule cases: no 'schema', 'null', 'traceback' and so on),
  - report at least one error when something was actually damaged beyond what the rules allow (not required: some
    mutations are harmless, for example changing a label).
The random generator is seeded, so the same 200 mutations run every time and a failure can be reproduced.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from checks.setup_cases import BASE, check, wording_problems

JUNK = ["", " ", "<<<!!>>>", "null", "None", "NaN", "'; DROP TABLE x; --", "ééé 日本語 ☃", "\u0000\u0001", "x" * 500,
        "../../etc/passwd", "C:\\Windows\\system32", "{{ {x} }}", "-1", "0", "1e999", "true"]
OTHER_VALUES = [None, True, False, 0, -1, 1, 2**63, 3.14, -2.5, float("nan"), float("inf"), "", "text", [], [1, 2, 3], ["a"],
                {}, {"a": 1}, {1: 2}, [[]], [{}], [None]]


def all_paths(node, prefix=()):
    """Every place in the setup (each key of a group, each item of a list), as a path."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(prefix + (key,))
            found += all_paths(value, prefix + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.append(prefix + (index,))
            found += all_paths(value, prefix + (index,))
    return found


def get(root, path):
    for part in path:
        root = root[part]
    return root


def set_at(root, path, value):
    get(root, path[:-1])[path[-1]] = value


def remove_at(root, path):
    get(root, path[:-1]).pop(path[-1])


def mutate_once(setup: dict, rng: random.Random) -> str:
    """Apply one random mutation in place and say what it was (in words)."""
    paths = all_paths(setup)
    path = rng.choice(paths)
    kind = rng.choice(["delete", "swap_type", "junk", "swap_values", "repeat_item", "add_unknown", "empty_section"])
    where = ".".join(str(p) for p in path)
    if kind == "delete":
        remove_at(setup, path)
        return f"deleted {where}"
    if kind == "swap_type":
        value = copy.deepcopy(rng.choice(OTHER_VALUES))
        set_at(setup, path, value)
        return f"replaced {where} with {value!r}"
    if kind == "junk":
        value = rng.choice(JUNK)
        set_at(setup, path, value)
        return f"wrote junk {value[:20]!r} into {where}"
    if kind == "swap_values":
        other = rng.choice(paths)
        try:
            first, second = copy.deepcopy(get(setup, path)), copy.deepcopy(get(setup, other))
            set_at(setup, path, second)
            set_at(setup, other, first)
        except (KeyError, IndexError, TypeError):
            return f"tried to swap {where} (no effect)"
        return f"swapped {where} with {'.'.join(str(p) for p in other)}"
    if kind == "repeat_item":
        value = get(setup, path)
        if isinstance(value, list) and value:
            value.append(copy.deepcopy(rng.choice(value)))
        return f"repeated an item of {where}"
    if kind == "add_unknown":
        value = get(setup, path)
        if isinstance(value, dict):
            value[rng.choice(["mystery", "Colour", "", "a b", 7])] = rng.choice(OTHER_VALUES)
        return f"added an unknown setting inside {where}"
    value = get(setup, path)
    set_at(setup, path, {} if isinstance(value, dict) else ([] if isinstance(value, list) else None))
    return f"emptied {where}"


@dataclass
class MutationReport:
    runs: int = 0
    crashes: list[str] = field(default_factory=list)
    unplain: list[str] = field(default_factory=list)
    unexpected_failures: list[str] = field(default_factory=list)   # a rule that could not cope (X99) although nothing crashed
    with_errors: int = 0
    messages: int = 0


def run(runs: int = 200, seed: int = 20261009) -> MutationReport:
    rng = random.Random(seed)
    report = MutationReport()
    for number in range(1, runs + 1):
        setup = copy.deepcopy(BASE)
        steps = [mutate_once(setup, rng) for _ in range(rng.choice([1, 1, 2, 3]))]
        label = f"#{number}: " + "; ".join(steps)
        report.runs += 1
        try:
            problems = check(setup, strict=True)
        except Exception as error:                      # noqa: BLE001 - this is exactly what the test looks for
            report.crashes.append(f"{label} -> {type(error).__name__}: {error}")
            try:
                problems = check(setup)                 # the normal (non-strict) call must still never crash
            except Exception as again:                  # noqa: BLE001
                report.crashes.append(f"{label} -> even the normal call crashed: {type(again).__name__}: {again}")
                continue
        if not isinstance(problems, list):
            report.crashes.append(f"{label} -> did not return a list")
            continue
        report.messages += len(problems)
        report.with_errors += any(p.level == "error" for p in problems)
        for p in problems:
            for why in wording_problems(p):
                report.unplain.append(f"{label} -> {p.rule}: {why}")
        if any(p.rule == "X99" for p in problems):
            report.unexpected_failures.append(label)
    return report
