"""Reads config/settings.yaml, checks every value, and explains problems in plain English."""
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Any

import yaml

from .models import (
    Cell, Comparison, DesignSpace, Display, DissolutionSpec, HardnessSpec,
    Ingredient, Noise, People, Run, ScriptedFault, ScriptedFaults, Settings,
    Specifications, Step,
)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"

REQUIRED_INGREDIENTS = ("drug", "filler", "binder", "disintegrant", "lubricant")
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class SettingsError(Exception):
    """Raised with a list of plain-English problems found in the settings."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


class _Reader:
    """Pulls values out of the raw file and records every problem instead of stopping at the first."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def problem(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def section(self, parent: Any, key: str, where: str) -> dict:
        value = parent.get(key) if isinstance(parent, dict) else None
        if not isinstance(value, dict):
            self.problem(where or key, f"section '{key}' is missing or empty.")
            return {}
        return value

    def number(self, parent: dict, key: str, where: str, *, positive: bool = False,
               minimum: float | None = None, integer: bool = False) -> float:
        label = f"{where} > {key}"
        value = parent.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.problem(label, f"expected a number but found {value!r}.")
            return 0
        if integer and value != int(value):
            self.problem(label, f"expected a whole number but found {value}.")
        if positive and value <= 0:
            self.problem(label, f"must be greater than zero, but is {value}.")
        if minimum is not None and value < minimum:
            self.problem(label, f"must be at least {minimum}, but is {value}.")
        return int(value) if integer else value

    def text(self, parent: dict, key: str, where: str) -> str:
        value = parent.get(key)
        if not isinstance(value, str) or not value.strip():
            self.problem(f"{where} > {key}", f"expected some text but found {value!r}.")
            return ""
        return value

    def clock(self, parent: dict, key: str, where: str) -> time:
        raw = self.text(parent, key, where)
        try:
            return datetime.strptime(raw, "%H:%M").time()
        except ValueError:
            if raw:
                self.problem(f"{where} > {key}", f"'{raw}' is not a time. Write it like 08:00.")
            return time(0, 0)


def load_settings(path: Path | str | None = None) -> Settings:
    """Load and check the settings file. Raises SettingsError listing every problem found."""
    file = Path(path) if path else DEFAULT_PATH
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError([f"The settings file was not found at {file}."])
    except yaml.YAMLError as error:
        raise SettingsError([f"The settings file is not valid YAML (check indentation and colons): {error}"])
    return settings_from_dict(raw)


def settings_from_dict(raw: Any) -> Settings:
    """Check an already-parsed settings dictionary. Separate from load_settings so checks can test bad input."""
    r = _Reader()
    if not isinstance(raw, dict):
        raise SettingsError(["The settings file is empty or is not a list of named sections."])

    # display
    d = r.section(raw, "display", "")
    display = Display(r.text(d, "banner", "display"), r.text(d, "accent_colour", "display"),
                      r.text(d, "font", "display"))

    # design space
    ing_raw = r.section(r.section(raw, "design_space", ""), "ingredients", "design_space")
    ingredients = []
    for key in REQUIRED_INGREDIENTS:
        if key not in ing_raw:
            r.problem("design_space > ingredients", f"ingredient '{key}' is missing.")
            continue
        item = ing_raw[key] if isinstance(ing_raw[key], dict) else {}
        where = f"design_space > ingredients > {key}"
        low = r.number(item, "min", where, minimum=0)
        high = r.number(item, "max", where, positive=True)
        if high and low >= high:
            r.problem(where, f"min ({low}) must be smaller than max ({high}).")
        ingredients.append(Ingredient(key, r.text(item, "label", where), low, high))
    for key in ing_raw:
        if key not in REQUIRED_INGREDIENTS:
            r.problem("design_space > ingredients",
                      f"'{key}' is not a recognised ingredient. This proof of concept models exactly: "
                      + ", ".join(REQUIRED_INGREDIENTS) + ".")

    # specifications
    spec_raw = r.section(raw, "specifications", "")
    dis = r.section(spec_raw, "dissolution_30min", "specifications")
    hard = r.section(spec_raw, "hardness", "specifications")
    dw, hw = "specifications > dissolution_30min", "specifications > hardness"
    dissolution = DissolutionSpec(r.text(dis, "label", dw), r.text(dis, "unit", dw),
                                  r.number(dis, "minimum", dw, minimum=0),
                                  r.number(dis, "margin_scale", dw, positive=True))
    hardness = HardnessSpec(r.text(hard, "label", hw), r.text(hard, "unit", hw),
                            r.number(hard, "minimum", hw, minimum=0),
                            r.number(hard, "maximum", hw, positive=True))
    if hardness.maximum and hardness.minimum >= hardness.maximum:
        r.problem(hw, f"minimum ({hardness.minimum}) must be smaller than maximum ({hardness.maximum}).")
    if dissolution.minimum > 100:
        r.problem(dw, f"minimum ({dissolution.minimum}) cannot be above 100 %.")

    # cell steps
    steps = []
    steps_raw = r.section(raw, "cell", "").get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        r.problem("cell > steps", "expected a list of steps (dispense, blend, ...).")
        steps_raw = []
    for i, item in enumerate(steps_raw, start=1):
        item = item if isinstance(item, dict) else {}
        where = f"cell > steps > step {i}"
        steps.append(Step(r.text(item, "name", where), r.text(item, "label", where),
                          r.number(item, "duration_minutes", where, positive=True)))
    names = [s.name for s in steps]
    if len(set(names)) != len(names):
        r.problem("cell > steps", "two steps have the same name; each name must be unique.")

    # run
    run_raw = r.section(raw, "run", "")
    start_text = r.text(run_raw, "start", "run")
    start = datetime(2000, 1, 1)
    try:
        start = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
    except ValueError:
        if start_text:
            r.problem("run > start", f"'{start_text}' is not a date and time. Write it like 2026-10-09 18:00.")
    run = Run(start, r.number(run_raw, "duration_hours", "run", positive=True),
              r.number(run_raw, "random_seed", "run", integer=True))

    # people
    p = r.section(raw, "people", "")
    days = p.get("staffed_days")
    weekdays: list[int] = []
    if not isinstance(days, list):
        r.problem("people > staffed_days", "expected a list such as [\"Mon\", \"Tue\"].")
    else:
        for day in days:
            key = str(day).strip().lower()[:3]
            if key in WEEKDAYS:
                weekdays.append(WEEKDAYS[key])
            else:
                r.problem("people > staffed_days", f"'{day}' is not a day. Use Mon, Tue, Wed, Thu, Fri, Sat or Sun.")
    people = People(tuple(sorted(set(weekdays))), r.clock(p, "staffed_from", "people"),
                    r.clock(p, "staffed_until", "people"))
    if people.staffed_from >= people.staffed_until:
        r.problem("people", "staffed_from must be earlier than staffed_until.")

    # virtual lab noise
    n = r.section(r.section(raw, "virtual_lab", ""), "noise", "virtual_lab")
    noise = Noise(r.number(n, "dissolution_sd", "virtual_lab > noise", minimum=0),
                  r.number(n, "hardness_sd", "virtual_lab > noise", minimum=0))

    # comparison
    c = r.section(raw, "comparison", "")
    comparison = Comparison(
        r.number(c, "campaigns", "comparison", positive=True, integer=True),
        r.number(c, "trials_per_campaign", "comparison", positive=True, integer=True),
        r.number(c, "manual_baseline_trials_per_week", "comparison", positive=True))

    # scripted faults (checked against the steps and campaign length above)
    f = r.section(raw, "scripted_faults", "")
    purge = r.number(f, "purge_minutes", "scripted_faults", positive=True)
    events = []
    events_raw = f.get("events")
    if not isinstance(events_raw, list):
        r.problem("scripted_faults > events", "expected a list of events (it can be empty: events: []).")
        events_raw = []
    for i, item in enumerate(events_raw, start=1):
        item = item if isinstance(item, dict) else {}
        where = f"scripted_faults > events > event {i}"
        trial = r.number(item, "trial", where, positive=True, integer=True)
        station = r.text(item, "station", where)
        retry = item.get("retry_succeeds")
        if not isinstance(retry, bool):
            r.problem(f"{where} > retry_succeeds", f"expected true or false but found {retry!r}.")
        if station and station not in names:
            r.problem(f"{where} > station", f"'{station}' is not one of the cell steps ({', '.join(names)}).")
        if trial > comparison.trials_per_campaign:
            r.problem(f"{where} > trial",
                      f"trial {trial} is beyond the {comparison.trials_per_campaign} trials in a campaign.")
        events.append(ScriptedFault(trial, station, bool(retry), r.text(item, "alert", where)))
    trial_numbers = [e.trial for e in events]
    if len(set(trial_numbers)) != len(trial_numbers):
        r.problem("scripted_faults > events", "two events target the same trial; use one event per trial.")

    if r.problems:
        raise SettingsError(r.problems)
    return Settings(display, DesignSpace(tuple(ingredients)), Specifications(dissolution, hardness),
                    Cell(tuple(steps)), run, people, noise, ScriptedFaults(purge, tuple(events)), comparison)
