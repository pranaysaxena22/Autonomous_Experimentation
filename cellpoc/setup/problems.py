"""What the validator returns: a list of Problems, each with a plain-English message that names the screen and the field."""
from __future__ import annotations

from dataclasses import dataclass

SCREENS = ["Project", "Ingredients", "Process and context", "Targets", "Equipment", "Calendar", "Faults",
           "Baseline and engine", "Data", "Review and save"]
SETUP_FILE_SCREEN = "Setup file"      # problems about the file itself (version, fingerprint, unreadable)
LEVELS = ("error", "warning", "note")  # an error blocks saving; a warning does not; a note is for information
ARROW = "›"

SECTION_SCREEN = {
    "project": "Project", "display": "Project", "batch_size_g": "Ingredients", "ingredients": "Ingredients",
    "recipe_rules": "Ingredients", "process_factors": "Process and context", "context_factors": "Process and context",
    "targets": "Targets", "equipment": "Equipment", "calendar": "Calendar", "faults": "Faults",
    "baseline": "Baseline and engine", "comparison": "Baseline and engine", "engine": "Baseline and engine",
    "virtual_lab": "Baseline and engine", "seeds": "Baseline and engine", "data": "Data",
    "format_version": SETUP_FILE_SCREEN, "saved": SETUP_FILE_SCREEN,
}

# sections whose own name adds nothing after the screen name
CONTAINERS = {"project", "display", "calendar", "baseline", "comparison", "engine", "seeds", "data", "equipment",
              "faults", "targets", "virtual_lab"}

# list sections: (the field that names an item, a backup field, what to call an item that has no name)
ITEM_NAMES = {
    ("ingredients",): ("label", "id", "Ingredient"),
    ("recipe_rules",): ("label", None, "Rule"),
    ("process_factors",): ("label", "id", "Process setting"),
    ("context_factors",): ("label", "id", "Context factor"),
    ("targets", "constraints"): ("label", "response", "Constraint"),
    ("targets", "objectives"): ("label", "quantity", "Objective"),
    ("equipment", "steps"): ("label", "name", "Step"),
    ("faults", "scripted"): (None, None, "Scripted fault"),
    ("faults", "random"): (None, None, "Random fault"),
    ("virtual_lab", "noise"): (None, "quantity", "Noise"),
}

FIELD_WORDS = {
    "name": "Name", "data_status": "Data status", "banner": "Banner", "accent_colour": "Accent colour", "font": "Font",
    "batch_size_g": "Batch size", "min": "Lowest value", "max": "Highest value", "low": "Lowest value",
    "high": "Highest value", "value": "Limit", "id": "ID", "label": "Label", "role": "Role", "unit": "Unit",
    "total": "Total", "tolerance": "Tolerance", "limit": "Limit", "items": "Ingredients in the rule", "rule": "Kind of rule",
    "values": "Values", "goal": "Goal", "response": "Result", "quantity": "Quantity", "required": "Required",
    "margin_scale": "Margin scale", "time_min": "Time (minutes)", "stations": "Stations", "layout_file": "Layout file",
    "measurement_step": "Measurement step", "act": "Act steps", "sense": "Sense steps",
    "reason_adapt_step": "Reason and Adapt step", "reason_min": "Reason time (minutes)", "start": "Start",
    "duration_h": "Duration (hours)", "staffed_days": "Staffed days", "staffed_from": "Staffed from",
    "staffed_until": "Staffed until", "purge_min": "Purge time (minutes)", "clean_after_skip": "Clean after a skipped candidate",
    "recovery": "Recovery", "tap_shake_s": "Tap-and-shake time (seconds)", "max_retries": "Maximum retries", "trial": "Trial",
    "where": "Where", "step": "Step", "action": "Action", "ingredient": "Ingredient", "cause": "Cause",
    "retry_succeeds": "Retry succeeds", "risk": "Risk", "chance_per_trial": "Chance per trial", "retry_succeeds_chance": "Chance the retry works",
    "manual_trials_per_week": "Manual trials per week", "campaigns": "Campaigns", "trials_per_campaign": "Trials per campaign",
    "initial_recipes": "Starting recipes", "candidates_per_decision": "Candidates per decision", "model": "Model",
    "sd": "Noise (standard deviation)", "run": "Seed", "experiments_file": "Experiments file", "meta_file": "Companion file",
    "encoding": "Encoding", "line_endings": "Line endings", "id_columns": "Identifying columns", "column_map": "Column mapping",
    "hardness": "Hardness", "conversions": "Unit conversions", "below_detection": "Below-detection rule",
    "replicates": "Replicates", "missing_values": "Missing values", "failed_runs": "Failed runs",
    "format_version": "Format version", "saved": "Saved details", "saved_at": "Saved at", "program_version": "Program version",
    "content_sha256": "Fingerprint", "policy": "Policy", "divide_by": "Divide by", "marker": "Marker",
    "note_column": "Note column", "value_column": "Value column", "unit_column": "Unit column", "to": "Becomes",
    "group_by": "Group by", "keep_individual_rows_for_noise_estimate": "Keep individual rows for the noise estimate",
    "status_column": "Status column", "failed_value": "Failed value", "noise": "Noise", "constraints": "Constraints",
    "objectives": "Objectives", "scripted": "Scripted faults", "random": "Random faults", "steps": "Steps", "phases": "Phases",
    "context_factors": "Context factors", "process_factors": "Process settings", "ingredients": "Ingredients",
    "recipe_rules": "Recipe rules", "experiment": "Experiment column", "replicate": "Replicate column", "batch": "Batch column",
    "date": "Date column", "status": "Status column", "failure_reason": "Failure reason column",
    "validation": "Validation", "responses": "Results to predict", "inputs": "Inputs", "derived_from": "Calculated from",
    "groups": "Groups held out", "left_out": "Left out of the modelling", "why": "Why", "supplier": "Supplier column", "api": "API column", "column": "Column", "confirmed": "Confirmed supplier",
}


@dataclass(frozen=True)
class Problem:
    rule: str          # for example "R05"
    variant: str       # a rule can have more than one wording, for example "unreachable" and "narrower"
    level: str         # error, warning or note
    screen: str
    field: str         # for example "Binder › Lowest value" ("" when the whole screen is meant)
    path: str          # where in the setup, for example "ingredients[2].min"
    text: str          # what is wrong and how to fix it

    @property
    def message(self) -> str:
        return f"{self.screen} {ARROW} {self.field}: {self.text}" if self.field else f"{self.screen}: {self.text}"


def has_errors(problems: list[Problem]) -> bool:
    return any(p.level == "error" for p in problems)


def path_text(path: tuple) -> str:
    """A path like ('ingredients', 2, 'min') written as ingredients[2].min."""
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def screen_for(path: tuple) -> str:
    return SECTION_SCREEN.get(path[0], SETUP_FILE_SCREEN) if path and isinstance(path[0], str) else SETUP_FILE_SCREEN


def _words(key: str) -> str:
    if key in FIELD_WORDS:
        return FIELD_WORDS[key]
    if any(c.isupper() for c in key):   # unit names such as kP or N
        return key
    text = key.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _item_name(setup, section: tuple, index: int) -> str:
    primary, backup, kind = ITEM_NAMES[section]
    node = setup
    for key in section:
        node = node.get(key) if isinstance(node, dict) else None
    item = node[index] if isinstance(node, list) and 0 <= index < len(node) else None
    if isinstance(item, dict):
        for key in (primary, backup):
            if key and isinstance(item.get(key), str) and item[key].strip():
                return item[key].strip()
    return f"{kind} {index + 1}"


def field_label(setup, path: tuple) -> str:
    """A human name for a place in the setup. Never fails, whatever the setup looks like."""
    parts: list[str] = []
    n = len(path)
    i = 1 if n and path[0] in CONTAINERS else 0
    while i < n:
        key = path[i]
        section = tuple(path[:i + 1])
        if isinstance(key, str) and section in ITEM_NAMES:
            if i + 1 < n and isinstance(path[i + 1], int):
                parts.append(_item_name(setup, section, path[i + 1]))
                i += 2
                continue
            if i == n - 1:      # the list itself: the screen name already says it
                i += 1
                continue
        parts.append(f"item {key + 1}" if isinstance(key, int) else _words(str(key)))
        i += 1
    return f" {ARROW} ".join(p for p in parts if p)
