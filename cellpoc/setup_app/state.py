"""What the app remembers while it is open: the working setup, which screen is showing, where the setup came from.

Loading a setup (blank, the bundled example, or a saved file) replaces the working copy. Nothing is written anywhere
until the person saves on the last screen.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import streamlit as st

from cellpoc.setup import (PROJECT_ROOT, SETUP_FILE_SCREEN, Problem, blank_setup, example_choices, example_setup_path, load_setup,
                           validate)
from cellpoc.setup.files import PACKAGE_EXAMPLES, SETUPS_FOLDER
from cellpoc.setup.validate import load_layout

from . import style

SAVED_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")


def init() -> None:
    for key, value in (("setup", None), ("ver", 0), ("load_id", 0), ("screen", 0), ("origin", ""), ("base_dir", None),
                       ("load_problems", []), ("saved", None), ("linked", False), ("run_result", None), ("dashboard_started", False), ("live_started", False)):
        st.session_state.setdefault(key, value)


def saved_names() -> list[str]:
    folder = PROJECT_ROOT / SETUPS_FOLDER
    return sorted(p.stem for p in folder.glob("*.yaml") if SAVED_NAME.match(p.stem)) if folder.is_dir() else []


def _replace(setup: dict, origin: str, base_dir: Path | None) -> None:
    st.session_state.update(setup=setup, origin=origin, base_dir=base_dir, screen=0, saved=None, load_problems=[], run_result=None, dashboard_started=False, live_started=False)
    st.session_state["ver"] += 1
    st.session_state["load_id"] += 1


def start_blank() -> None:
    shown = style.project_display()
    _replace(blank_setup(shown["banner"], shown["accent_colour"], shown["font"]), "a blank setup", PACKAGE_EXAMPLES)


def example_labels() -> list[str]:
    return [label for label, _ in example_choices()]


def load_example(picker: str | None = None, number: int | None = None) -> None:
    """Load an illustrative example: the one chosen in the picker whose widget key is `picker`, or example `number` (1 to 3); with neither, the standard example 1."""
    choices = example_choices()
    index = 0
    if number is not None and 1 <= number <= len(choices):
        index = number - 1
    elif picker and st.session_state.get(picker) in [label for label, _ in choices]:
        index = [label for label, _ in choices].index(st.session_state[picker])
    path = choices[index][1] if choices else example_setup_path()
    loaded = load_setup(path)
    _replace(copy.deepcopy(loaded.setup), "the bundled example" if index == 0 else f"the bundled example {index + 1}", PACKAGE_EXAMPLES)


def open_saved(name: str | None) -> None:
    """Open setups/<name>.yaml. A file that cannot be read or has a version problem is refused, with the reason shown."""
    if not name or not SAVED_NAME.match(name):
        st.session_state["load_problems"] = []
        return
    path = PROJECT_ROOT / SETUPS_FOLDER / f"{name}.yaml"
    loaded = load_setup(path)
    problems: list[Problem] = list(loaded.problems)
    if loaded.setup is not None:
        problems += validate(loaded.setup, base_dir=path.parent)
        file_level = [p for p in problems if p.screen == SETUP_FILE_SCREEN and p.level == "error"]
        if isinstance(loaded.setup, dict) and not file_level:
            _replace(loaded.setup, f"setups/{name}.yaml", path.parent)
            return
        problems = [p for p in problems if p.screen == SETUP_FILE_SCREEN]
    st.session_state["load_problems"] = problems


def go(screen: int) -> None:
    st.session_state["screen"] = screen


def check() -> tuple[list[Problem], dict | None]:
    """The checker's verdict on the working setup, and its layout (for the station lists)."""
    setup, base_dir = st.session_state["setup"], st.session_state["base_dir"]
    problems = validate(setup, base_dir=base_dir)
    layout, _ = load_layout(setup, base_dir, PROJECT_ROOT)
    return problems, layout


def counts(problems: list[Problem], screen: str) -> tuple[int, int]:
    """(errors, warnings) on a screen. The last screen also carries the file-level messages (version, fingerprint)."""
    here = {screen} | ({SETUP_FILE_SCREEN} if screen == "Review and save" else set())
    return (sum(p.level == "error" and p.screen in here for p in problems), sum(p.level == "warning" and p.screen in here for p in problems))


def count_text(errors: int, warnings: int) -> str:
    if not errors and not warnings:
        return "no errors or warnings"
    parts = []
    if errors:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
    return ", ".join(parts)


def default_name(setup: dict) -> str:
    name = ((setup.get("project") or {}).get("name") if isinstance(setup.get("project"), dict) else "") or ""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:60].strip("-")
    return slug or "my-study"


__all__ = ["init", "saved_names", "start_blank", "load_example", "example_labels", "open_saved", "go", "check", "counts", "count_text", "default_name"]
