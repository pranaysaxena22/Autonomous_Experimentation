"""The shared validator: one call checks a whole setup and returns plain-English problems.

Used by the setup app and by the health check, so both apply exactly the same rules. It never raises because of what
is in a setup: a setup of any shape, however broken, produces messages. (Tests pass strict=True to prove that no rule
fails unexpectedly on a structurally sound setup.)
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .files import PROJECT_ROOT, fingerprint, path_is_safe, resolve_reference
from .messages import make_problem
from .problems import SCREENS, SETUP_FILE_SCREEN, Problem
from .rules import Ctx, SEMANTIC_RULES, is_text, sub
from .schema import load_schema, schema_problems, shown
from .versions import DEFAULT_SUPPORT, FormatSupport

_MISSING = object()
_LEVEL_ORDER = {"error": 0, "warning": 1, "note": 2}


def _describe(value) -> str:
    if value is None:
        return "empty"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, str):
        return "text"
    return "a single value"


def apply_format_version(setup: dict, formats: FormatSupport) -> tuple[list[Problem], dict, bool]:
    """Check the setup's format version. Returns (problems, the setup to check, whether to stop here)."""
    problems: list[Problem] = []
    version = setup.get("format_version", _MISSING)
    path = ("format_version",)
    if version is _MISSING:
        return [make_problem("V01", "", path, setup)], setup, True
    if isinstance(version, bool) or not isinstance(version, int):
        return [make_problem("V02", "not_a_number", path, setup, shown=shown(version))], setup, True
    if version > formats.current:
        return [make_problem("V03", "", path, setup, version=version, current=formats.current)], setup, True
    if version < formats.oldest:
        return [make_problem("V02", "too_old", path, setup, version=version, oldest=formats.oldest, current=formats.current)], setup, True
    saved = setup.get("saved")
    if isinstance(saved, dict) and is_text(saved.get("content_sha256")) and saved["content_sha256"] != fingerprint(setup):
        problems.append(make_problem("V05", "", ("saved", "content_sha256"), setup))
    if version < formats.current:
        if not formats.can_upgrade(version):
            return [make_problem("V02", "no_path", path, setup, version=version, current=formats.current)], setup, True
        setup = formats.upgrade(setup, version)
        problems.append(make_problem("V04", "", path, setup, version=version, current=formats.current))
    return problems, setup, False


def load_layout(setup: dict, base_dir: Path | None, root: Path) -> tuple[dict | None, list[Problem]]:
    """Find and read the layout the setup names. A missing or unusable layout is reported, never fatal."""
    reference = sub(setup, "equipment", "layout_file")
    if not is_text(reference) or not path_is_safe(reference):
        return None, []           # the schema reports a missing or unsafe name
    path = resolve_reference(reference, base_dir, root)
    where = ("equipment", "layout_file")
    if path is None:
        return None, [make_problem("R51", "", where, setup, ref=reference)]
    try:
        layout = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return None, [make_problem("R52", "", where, setup, why="it can't be read as a layout")]
    errors = sorted(Draft202012Validator(load_schema("layout.schema.json")).iter_errors(layout), key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        near = next((str(p) for p in reversed(list(errors[0].absolute_path)) if isinstance(p, str)), "the top")
        return None, [make_problem("R52", "", where, setup, why=f"it is not a valid layout (the problem is near '{near}')")]
    return layout, []


def validate(setup, *, base_dir: Path | str | None = None, root: Path | str = PROJECT_ROOT, layout: dict | None = None,
             formats: FormatSupport = DEFAULT_SUPPORT, strict: bool = False) -> list[Problem]:
    """Check a whole setup. `base_dir` is the folder the setup file lives in (relative file names are also looked up there)."""
    root = Path(root)
    base_dir = Path(base_dir) if base_dir is not None else None
    if not isinstance(setup, dict):
        return [make_problem("T01", "", ("format_version",), None, what=_describe(setup))]
    problems, setup, stop = apply_format_version(setup, formats)
    if stop:
        return problems
    try:
        structural = schema_problems(setup)
    except Exception:       # noqa: BLE001 - whatever the setup holds, the person gets a message, not a crash
        if strict:
            raise
        structural = [make_problem("X99", "", ("format_version",), setup)]
    problems += structural
    if layout is None:
        layout, layout_problems = load_layout(setup, base_dir, root)
        problems += layout_problems
    context = Ctx(setup, base_dir, root, layout)
    for rule in SEMANTIC_RULES:
        try:
            problems += list(rule(context))
        except Exception:   # noqa: BLE001
            if strict and not structural:
                raise
            problems.append(make_problem("X99", "", ("format_version",), setup))
    return _tidy(problems)


def _tidy(problems: list[Problem]) -> list[Problem]:
    """No repeats; grouped by screen in screen order, errors first."""
    seen: set = set()
    unique = []
    for p in problems:
        if (p.rule, p.variant, p.path, p.text) not in seen:
            seen.add((p.rule, p.variant, p.path, p.text))
            unique.append(p)
    order = [SETUP_FILE_SCREEN] + SCREENS
    return sorted(unique, key=lambda p: (order.index(p.screen) if p.screen in order else len(order), _LEVEL_ORDER[p.level]))


def problems_at(problems: list[Problem], path_prefix: str) -> list[Problem]:
    """The problems at or inside one place in the setup, for showing messages next to a field."""
    return [p for p in problems if p.path == path_prefix or p.path.startswith(path_prefix + ".") or p.path.startswith(path_prefix + "[")]
