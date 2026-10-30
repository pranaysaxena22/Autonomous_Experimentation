"""One test for every setup rule: a deliberately wrong setup that must produce exactly that rule's message.

Each case starts from the bundled example setup (which is valid), breaks one thing, and checks that
  - the expected rule (and wording variant) is reported, at the expected level (error / warning / note),
  - the message starts with the screen and field, and contains no technical wording.
docs/setup_messages.md is generated from these cases, and the health check fails if any rule has no case.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from cellpoc.setup import (CATALOGUE, FormatSupport, load_setup, save_setup, validate)
from cellpoc.setup import rules as rules_module
from cellpoc.setup.files import PACKAGE_EXAMPLES
from cellpoc.setup.problems import Problem

EXAMPLES = PACKAGE_EXAMPLES
_LOADED = load_setup(EXAMPLES / "setup_example.yaml")
BASE: dict = _LOADED.setup
LAYOUT: dict = json.loads((EXAMPLES / "cell_layout_example.json").read_bytes().decode("utf-8"))

# Words that belong to programmers, never to the person filling in a setup.
TECHNICAL = re.compile(r"\b(schema|jsonschema|null|nonetype|traceback|exception|keyerror|typeerror|valueerror|attributeerror|"
                       r"regex|validator|enum|additionalproperties|stack trace|undefined|nan|inf)\b|\$ref|<class|object at|\{|\}",
                       re.IGNORECASE)
PYTHON_LEAKS = re.compile(r"\b(None|True|False)\b")


def wording_problems(problem: Problem) -> list[str]:
    """Why a message is not plain English for a non-programmer (empty if it is fine)."""
    found = []
    if not (problem.message.startswith(problem.screen + " › ") or problem.message.startswith(problem.screen + ": ")):
        found.append("does not start with the screen (and field)")
    # What the person typed is quoted back to them ('you wrote ...'), so quoted text is theirs and is not judged.
    own_words_removed = re.sub(r"'[^']*'", "''", problem.message)
    if TECHNICAL.search(own_words_removed) or PYTHON_LEAKS.search(own_words_removed):
        found.append("contains technical wording: " + problem.message)
    if not problem.text.strip():
        found.append("is empty")
    return found


def fresh() -> dict:
    return copy.deepcopy(BASE)


def check(setup, **kwargs) -> list[Problem]:
    kwargs.setdefault("base_dir", EXAMPLES)
    return validate(setup, **kwargs)


@dataclass
class Case:
    rule: str
    variant: str
    what: str                                  # what the test does, in words
    run: Callable[[], list[Problem]]


CASES: list[Case] = []


def case(rule: str, variant: str, what: str):
    """Register a test that returns the problems found for a deliberately wrong setup."""
    def register(function: Callable[[], list[Problem]]):
        CASES.append(Case(rule, variant, what, function))
        return function
    return register


def mutation(rule: str, variant: str, what: str, **kwargs):
    """Register a test that changes a copy of the example setup with `change(setup)` and validates it."""
    def register(change: Callable[[dict], None]):
        def run() -> list[Problem]:
            setup = fresh()
            change(setup)
            return check(setup, **kwargs)
        CASES.append(Case(rule, variant, what, run))
        return change
    return register


def _in_temp_project(setup_change: Callable[[dict], None], files: dict[str, bytes] | None = None):
    """Validate a changed setup inside a throw-away project folder holding copies of the example files."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for source in EXAMPLES.iterdir():
            if source.is_file():
                shutil.copy(source, root / source.name)
        for name, content in (files or {}).items():
            (root / name).write_bytes(content)
        setup = fresh()
        setup_change(setup)
        return check(setup, base_dir=root, root=root)


# ------------------------------------------------------------------ the file itself (F, T, V, X)
@case("F01", "", "a file of random bytes that is not text")
def _():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "bad.yaml"
        path.write_bytes(b"\xff\xfe\x00\x81\x82 not text")
        return load_setup(path).problems


@case("F02", "", "a file with a broken line (an unclosed bracket)")
def _():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "bad.yaml"
        path.write_bytes(b"format_version: 1\nproject: [unclosed\n")
        return load_setup(path).problems


@case("F03", "", "a file of more than 1 MB")
def _():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "big.yaml"
        path.write_bytes(b"# padding\n" * 120_000)
        return load_setup(path).problems


@case("T01", "", "a setup file that is only a line of text, not named sections")
def _():
    return validate("just some text")


@case("V01", "", "a setup with no format version")
def _():
    setup = fresh()
    setup.pop("format_version")
    return check(setup)


@mutation("V02", "not_a_number", "a format version written as a word")
def _(s):
    s["format_version"] = "one"


@case("V02", "too_old", "a setup older than the oldest format the program can read (simulated: program reads 2 to 3)")
def _():
    return check(fresh(), formats=FormatSupport(current=3, oldest=2))


@case("V02", "no_path", "an older setup with no way to bring it up to date (simulated: no migration registered)")
def _():
    return check(fresh(), formats=FormatSupport(current=3, oldest=1, migrations={1: lambda s: s}))


@mutation("V03", "", "a setup saved in a newer format than the program knows (version 2 while the program reads 1)")
def _(s):
    s["format_version"] = 2


@case("V04", "", "an older setup is brought up to date (simulated: the program is at version 2 with a migration from 1)")
def _():
    return check(fresh(), formats=FormatSupport(current=2, oldest=1, migrations={1: lambda s: s}))


@case("V05", "", "a saved setup that was edited by hand afterwards")
def _():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = save_setup(fresh(), "edited", root=root, problems=[])
        loaded = load_setup(path, root=root)
        loaded.setup["batch_size_g"] = 25
        return check(loaded.setup, base_dir=EXAMPLES)


@case("X99", "", "a check that fails unexpectedly (simulated by adding a faulty check)")
def _():
    def faulty(context):
        raise RuntimeError("simulated fault")
        yield
    rules_module.SEMANTIC_RULES.append(faulty)
    try:
        return check(fresh())
    finally:
        rules_module.SEMANTIC_RULES.remove(faulty)


# ------------------------------------------------------------------ generic structure messages (S)
@case("S01", "", "a missing section (the baseline is removed)")
def _():
    setup = fresh()
    setup.pop("baseline")
    return check(setup)


@mutation("S02", "", "a number written as text (the seed)")
def _(s):
    s["seeds"]["run"] = "two thousand"


@mutation("S03", "", "a choice that is not on the list (the data status)")
def _(s):
    s["project"]["data_status"] = "pretend"


@mutation("S04", "", "a number below its lowest allowed value (0 campaigns)")
def _(s):
    s["comparison"]["campaigns"] = 0


@mutation("S05", "empty", "an empty banner")
def _(s):
    s["display"]["banner"] = ""


@mutation("S05", "long", "a program version recorded with 50 characters")
def _(s):
    s["saved"] = {"saved_at": "2026-10-09T10:00:00Z", "program_version": "x" * 50, "content_sha256": "0" * 64}


@mutation("S06", "id", "an ingredient ID with capital letters and a space")
def _(s):
    s["ingredients"][0]["id"] = "Drug Pct"


@mutation("S06", "other", "a save time written as a word")
def _(s):
    s["saved"] = {"saved_at": "yesterday", "program_version": "0.1.0", "content_sha256": "0" * 64}


@mutation("S07", "", "a setting name the program does not know")
def _(s):
    s["colour_of_sky"] = "blue"


@mutation("S08", "", "a list with too few items (one ingredient)")
def _(s):
    s["ingredients"] = s["ingredients"][:1]


@mutation("S09", "", "a list with a repeat (a staffed day listed twice)")
def _(s):
    s["calendar"]["staffed_days"] = ["Mon", "Mon"]


@mutation("S10", "", "an empty column mapping")
def _(s):
    s["data"]["column_map"] = {}


@mutation("S11", "", "an ingredient measured in grams instead of percent")
def _(s):
    s["ingredients"][0]["unit"] = "g"


# ------------------------------------------------------------------ 1 Project
@mutation("R01", "", "an empty study name")
def _(s):
    s["project"]["name"] = ""


@mutation("R01", "long", "a study name of 81 characters")
def _(s):
    s["project"]["name"] = "n" * 81


@mutation("R02", "", "banner without the word 'illustrative' or 'synthetic'")
def _(s):
    s["display"]["banner"] = "Simulation of the cell"


@mutation("R03", "", "an accent colour written as a word")
def _(s):
    s["display"]["accent_colour"] = "green"


@mutation("R04", "real", "data status 'real'")
def _(s):
    s["project"]["data_status"] = "real"


@mutation("R04", "validated", "data status 'validated'")
def _(s):
    s["project"]["data_status"] = "validated"


# ------------------------------------------------------------------ 2 Ingredients, 3 Process and context
@mutation("R05", "", "an ingredient whose lowest value is above its highest")
def _(s):
    s["ingredients"][0]["min"], s["ingredients"][0]["max"] = 40, 30


@mutation("R06", "", "an ingredient above 100%")
def _(s):
    s["ingredients"][1]["max"] = 120


@mutation("R07", "none", "no ingredient chosen as the balance")
def _(s):
    s["ingredients"][4]["role"] = "binder"


@mutation("R07", "many", "two ingredients chosen as the balance")
def _(s):
    s["ingredients"][0]["role"] = "balance"


@mutation("R08", "", "two ingredients with the same ID")
def _(s):
    s["ingredients"][1]["id"] = s["ingredients"][0]["id"]


@mutation("R09", "unreachable", "a balance range that cannot reach 100% (filler 0 to 20%)")
def _(s):
    s["ingredients"][4]["min"], s["ingredients"][4]["max"] = 0, 20


@mutation("R09", "narrower", "a balance range tighter than the others leave (filler 60 to 90%)")
def _(s):
    s["ingredients"][4]["min"] = 60


@mutation("R10", "", "a batch size of 0 grams")
def _(s):
    s["batch_size_g"] = 0


@mutation("R10", "type", "a batch size written as a word")
def _(s):
    s["batch_size_g"] = "twenty"


@mutation("R11", "at_most", "an 'at most' rule that the lowest values already break")
def _(s):
    s["recipe_rules"][1]["limit"] = 2


@mutation("R11", "at_least", "an 'at least' rule that the highest values cannot reach")
def _(s):
    s["recipe_rules"].append({"rule": "at_least", "items": ["binder_pct"], "limit": 50, "unit": "%", "label": "Binder at least 50%"})


@mutation("R42", "", "a recipe rule naming an ingredient that does not exist")
def _(s):
    s["recipe_rules"][1]["items"] = ["binder_pct", "ghost_pct"]


@mutation("R43", "missing", "no 'add up to 100%' rule")
def _(s):
    s["recipe_rules"] = s["recipe_rules"][1:]


@mutation("R43", "many", "two 'add up to' rules")
def _(s):
    s["recipe_rules"].append(copy.deepcopy(s["recipe_rules"][0]))


@mutation("R43", "total", "an 'add up to' total of 90%")
def _(s):
    s["recipe_rules"][0]["total"] = 90


@mutation("R12", "conflict", "force written in newtons beside an ID that ends in kilonewtons")
def _(s):
    s["process_factors"][0]["unit"] = "N"


@mutation("R12", "unknown_unit", "a process unit the program does not know")
def _(s):
    s["process_factors"][0]["unit"] = "furlong"


@mutation("R12", "no_suffix", "a process ID with no unit at the end")
def _(s):
    s["process_factors"][1]["id"] = "blend_time"


@mutation("R12", "case", "a unit with the wrong capital letters ('KN')")
def _(s):
    s["process_factors"][0]["unit"] = "KN"


@mutation("R13", "empty", "a context factor with no values")
def _(s):
    s["context_factors"][0]["values"] = []


@mutation("R13", "repeats", "a context factor listing a value twice")
def _(s):
    s["context_factors"][0]["values"] = ["A", "A"]


# ------------------------------------------------------------------ 4 Targets
@mutation("R14", "", "a 'between' target with the lowest value above the highest")
def _(s):
    s["targets"]["constraints"][1].update(low=12, high=10)


@mutation("R15", "at_least", "an 'at least' target with no number")
def _(s):
    s["targets"]["constraints"][0].pop("value")


@mutation("R15", "at_most", "an 'at most' target with no number")
def _(s):
    s["targets"]["constraints"][2].pop("value")


@mutation("R15", "between", "a 'between' target with no lowest value")
def _(s):
    s["targets"]["constraints"][1].pop("low")


@mutation("R16", "", "every target marked optional")
def _(s):
    for target in s["targets"]["constraints"]:
        target["required"] = False


@mutation("R17", "needed", "a required target that no station in the layout can read")
def _(s):
    s["targets"]["constraints"][0]["response"] = "gloss_pct"


@mutation("R17", "optional", "an optional target that no station in the layout can read")
def _(s):
    s["targets"]["constraints"][2]["response"] = "weight_variation_pct"


@mutation("R18", "", "an objective to both maximise and minimise drug load")
def _(s):
    s["targets"]["objectives"].append({"quantity": "drug_pct", "label": "Drug load", "unit": "%", "goal": "minimise"})


@mutation("R19", "conflict", "hardness in % beside an ID that ends in kP")
def _(s):
    s["targets"]["constraints"][1]["unit"] = "%"


@mutation("R19", "unknown_unit", "a target unit the program does not know")
def _(s):
    s["targets"]["constraints"][1]["unit"] = "furlong"


@mutation("R19", "no_suffix", "a target ID with no unit at the end")
def _(s):
    s["targets"]["constraints"][1]["response"] = "hardness"


@mutation("R19", "case", "a target unit with the wrong capital letters ('KP')")
def _(s):
    s["targets"]["constraints"][1]["unit"] = "KP"


# ------------------------------------------------------------------ 5 Equipment
@mutation("R20", "", "a step of 0 minutes")
def _(s):
    s["equipment"]["steps"][0]["time_min"] = 0


@mutation("R21", "", "a step using a station that is not in the layout")
def _(s):
    s["equipment"]["steps"][0]["stations"].append("teleporter")


@mutation("R22", "", "Reason as long as the whole last step")
def _(s):
    s["equipment"]["phases"]["reason_min"] = 60


@mutation("R23", "", "Reason and Adapt placed in a step that is not the last")
def _(s):
    s["equipment"]["phases"]["reason_adapt_step"] = "test"


def _tight(change_m: float) -> list[Problem]:
    layout = copy.deepcopy(LAYOUT)
    layout["robot"]["links_m"]["upper_arm"] += change_m
    return check(fresh(), layout=layout)


@case("R24", "tight", "a layout with between 0.03 m and 0.10 m of spare reach (the bundled example)")
def _():
    return _tight(0.0)


@case("R24", "very_tight", "a layout with less than 0.03 m of spare reach (arm shortened by 0.06 m)")
def _():
    return _tight(-0.06)


@case("R24", "beyond", "a layout with a spot beyond the arm's reach (arm shortened by 0.20 m)")
def _():
    return _tight(-0.20)


@mutation("R25", "", "a file name that climbs out of the project folder")
def _(s):
    s["equipment"]["layout_file"] = "../secret/layout.json"


@mutation("R45", "phase", "the Press step removed while the phases still use it")
def _(s):
    s["equipment"]["steps"] = [x for x in s["equipment"]["steps"] if x["name"] != "press"]


@mutation("R45", "measurement", "the Test step removed while it is still the measurement step")
def _(s):
    s["equipment"]["steps"] = [x for x in s["equipment"]["steps"] if x["name"] != "test"]


@mutation("R47", "", "the steps listed in the wrong order")
def _(s):
    s["equipment"]["steps"][0], s["equipment"]["steps"][1] = s["equipment"]["steps"][1], s["equipment"]["steps"][0]


@mutation("R51", "", "a layout file name that does not exist")
def _(s):
    s["equipment"]["layout_file"] = "no_such_layout.json"


@case("R52", "", "a layout file that is not a usable layout")
def _():
    def change(setup):
        setup["equipment"]["layout_file"] = "broken_layout.json"
    return _in_temp_project(change, {"broken_layout.json": b'{"name": "not a layout"}'})


# ------------------------------------------------------------------ 6 Calendar
@mutation("R26", "", "opening time after closing time")
def _(s):
    s["calendar"]["staffed_from"], s["calendar"]["staffed_until"] = "18:00", "08:00"


@mutation("R27", "", "a run of 1 hour while one trial takes 4 hours")
def _(s):
    s["calendar"]["duration_h"] = 1


@mutation("R28", "", "a start date that does not exist (30 February)")
def _(s):
    s["calendar"]["start"] = "2026-02-30 18:00"


@mutation("R53", "", "an opening time that is not a time (25:99)")
def _(s):
    s["calendar"]["staffed_from"] = "25:99"


# ------------------------------------------------------------------ 7 Faults
@mutation("R29", "", "a scripted fault on trial 99 of a 30-trial campaign")
def _(s):
    s["faults"]["scripted"][0]["trial"] = 99


@mutation("R30", "", "two scripted faults on the same trial")
def _(s):
    s["faults"]["scripted"][1]["trial"] = s["faults"]["scripted"][0]["trial"]


@mutation("R31", "pour_needs_ingredient", "a fault on a pour that names no ingredient")
def _(s):
    s["faults"]["scripted"][0]["where"].pop("ingredient")


@mutation("R31", "unknown_ingredient", "a fault naming an ingredient that does not exist")
def _(s):
    s["faults"]["scripted"][0]["where"]["ingredient"] = "ghost_pct"


@mutation("R32", "", "a random-fault chance written as 5 instead of 0.05")
def _(s):
    s["faults"]["random"][0]["chance_per_trial"] = 5


@mutation("R48", "", "a fault in the Clean step after the Clean step was removed")
def _(s):
    s["faults"]["scripted"][0]["where"]["step"] = "clean"
    s["equipment"]["steps"] = [x for x in s["equipment"]["steps"] if x["name"] != "clean"]


# ------------------------------------------------------------------ 8 Baseline and engine
@mutation("R33", "", "40 starting recipes in a 30-trial campaign")
def _(s):
    s["engine"]["initial_recipes"] = 40


@mutation("R34", "", "a manual baseline of 0 trials per week")
def _(s):
    s["baseline"]["manual_trials_per_week"] = 0


@mutation("R35", "", "scatter given for a quantity that is not measured")
def _(s):
    s["virtual_lab"]["noise"][0]["quantity"] = "ghost_pct"


# ------------------------------------------------------------------ 9 Data
@mutation("R36", "experiments", "an experiments file that does not exist")
def _(s):
    s["data"]["experiments_file"] = "no_such_table.csv"


@mutation("R36", "meta", "a companion file that does not exist")
def _(s):
    s["data"]["meta_file"] = "no_such_table.meta.json"


@mutation("R37", "", "a mapped column that is not in the file")
def _(s):
    s["data"]["column_map"]["drugpct"] = s["data"]["column_map"].pop("drug_pct")


@mutation("R38", "", "an ingredient that no column is mapped to")
def _(s):
    s["data"]["column_map"].pop("lubricant_pct")


@mutation("R39", "", "two columns mapped to the same ID")
def _(s):
    s["data"]["column_map"]["drug_pct_copy"] = "drug_pct"


@mutation("R54", "", "a column mapped to an ID the setup does not use")
def _(s):
    s["data"]["column_map"]["extra_column"] = "unused_thing"


@mutation("R40", "missing_kp", "hardness conversions with no 'kP' entry")
def _(s):
    s["data"]["hardness"]["conversions"].pop("kP")


@mutation("R50", "newtons", "newtons divided by 10 instead of 9.807")
def _(s):
    s["data"]["hardness"]["conversions"]["N"]["divide_by"] = 10


@mutation("R41", "", "the bundled example, whose experiment table is marked 'synthetic'")
def _(s):
    pass


# ---- how to read the file (Stage 2a): separator, decimal mark, encoding, sheet, dates, missing markers, units, joins
def _with_joined_file(change, content: bytes = b"experiment_id;extra_value\nE00001;1\n"):
    def run() -> list[Problem]:
        def edit(setup):
            setup["data"]["joins"] = [{"file": "joined.csv", "on": [{"main": "experiment_id", "joined": "experiment_id"}]}]
            change(setup)
        return _in_temp_project(edit, {"joined.csv": content})
    return run


@mutation("R55", "", "columns separated by commas and a comma as the decimal mark")
def _(s):
    s["data"]["delimiter"], s["data"]["decimal"] = "comma", "comma"


@mutation("R63", "", "a text encoding that does not exist")
def _(s):
    s["data"]["encoding"] = "klingon"


@mutation("R62", "", "a sheet name for a file that is not an Excel file")
def _(s):
    s["data"]["sheet"] = "Sheet1"


@mutation("R56", "unknown_piece", "a date format with hours (a piece the reader does not know)")
def _(s):
    s["data"]["date"]["format"] = "yyyy-mm-dd hh:mm"


@mutation("R56", "no_month", "a date format with no month")
def _(s):
    s["data"]["date"]["format"] = "yyyy"


@mutation("R56", "no_year", "a date format with no year")
def _(s):
    s["data"]["date"]["format"] = "dd.mm"


@mutation("R56", "repeated", "a date format that uses the month twice")
def _(s):
    s["data"]["date"]["format"] = "mm.mm.yyyy"


@mutation("R57", "", "month names given as only eleven names")
def _(s):
    s["data"]["date"]["months"] = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov"]


@mutation("R58", "", "a missing-value marker that is only a space")
def _(s):
    s["data"]["missing_markers"] = ["NA", " "]


@mutation("R59", "conflict", "hardness declared in newtons beside an ID that ends in kP")
def _(s):
    s["data"]["column_units"] = {"hardness_kp": "N"}


@mutation("R59", "unknown_unit", "a declared unit the program does not know")
def _(s):
    s["data"]["column_units"] = {"hardness_kp": "furlong"}


@mutation("R59", "no_suffix", "a unit declared for an ID that ends with no unit")
def _(s):
    s["data"]["column_units"] = {"binder_supplier": "%"}


@mutation("R59", "case", "a declared unit with the wrong capital letters ('KP')")
def _(s):
    s["data"]["column_units"] = {"hardness_kp": "KP"}


@mutation("R59", "unused_id", "a unit declared for an ID the setup does not use")
def _(s):
    s["data"]["column_units"] = {"mystery_pct": "%"}


@case("R36", "join", "a file to join in that does not exist")
def _():
    def edit(setup):
        setup["data"]["joins"] = [{"file": "no_such_file.csv", "on": [{"main": "experiment_id", "joined": "experiment_id"}]}]
    return _in_temp_project(edit)


@case("R60", "main_key", "a join column that is not in the main file")
def _():
    return _with_joined_file(lambda s: s["data"]["joins"][0]["on"][0].update(main="no_such_column"))()


@case("R60", "joined_key", "a join column that is not in the joined file")
def _():
    return _with_joined_file(lambda s: s["data"]["joins"][0]["on"][0].update(joined="no_such_column"))()


@case("R60", "clash", "a joined file with a column whose name is already in the main file")
def _():
    return _with_joined_file(lambda s: None, b"experiment_id;drug_pct\nE00001;1\n")()


# ---- how values are cleaned (Stage 2c): composition, assumed units, a fixed hardness unit, below-detection
@mutation("R64", "weight_not_mapped", "a total weight that no column is mapped to")
def _(s):
    s["data"]["composition"] = {"total_weight": "ghost_mg"}


@mutation("R64", "suffix_mismatch", "a total-weight ID that does not end like the amounts")
def _(s):
    s["data"]["column_map"]["Weight"] = "tablet_weight_g"
    s["data"]["composition"] = {"total_weight": "tablet_weight_g"}


@mutation("R64", "no_amounts", "a composition rule with no mapped amount columns")
def _(s):
    s["data"]["column_map"]["Weight"] = "tablet_weight_mg"
    s["data"]["composition"] = {"total_weight": "tablet_weight_mg"}


@mutation("R65", "", "an assumed unit for a column that is not mapped")
def _(s):
    s["data"]["assumed_units"] = [{"id": "ghost_mg", "why": "unit assumed, not confirmed"}]


@mutation("R66", "no_conversion", "a fixed hardness unit with no conversion")
def _(s):
    s["data"]["hardness"]["unit"] = "kg/cm2"


@mutation("R66", "both", "hardness with both a unit column and a fixed unit")
def _(s):
    s["data"]["hardness"]["unit"] = "N"


@mutation("R68", "", "a replicate grouping that names a column nothing produces")
def _(s):
    s["data"]["replicates"]["group_by"] = ["no_such_column"]


@mutation("R67", "", "a below-detection note column with no limit")
def _(s):
    s["data"]["below_detection"].pop("limit")


def _with_validation(s, **changes):
    """A valid validation section for the example setup, with one thing changed."""
    block = {"responses": ["dissolution_30min_pct", "hardness_kp"],
             "groups": {"batch": {"column": "batch_id"}, "supplier": {"column": "binder_supplier", "confirmed": True}, "date": {"column": "date"}}}
    block.update(changes)
    s["data"]["validation"] = block


@mutation("R69", "response", "a result to predict that no column produces")
def _(s):
    _with_validation(s, responses=["no_such_result"])


@mutation("R69", "input", "an input that no column produces")
def _(s):
    _with_validation(s, inputs=["drug_pct", "no_such_input"])


@mutation("R69", "derived", "a derived-from column that no column produces")
def _(s):
    _with_validation(s, derived_from={"hardness_kp": ["no_such_source"]})


@mutation("R69", "group", "a group column that no column produces")
def _(s):
    _with_validation(s, groups={"batch": {"column": "no_such_batch"}})


@mutation("R69", "left_out", "a left-out column that no column produces")
def _(s):
    _with_validation(s, left_out=[{"id": "no_such_column", "why": "not measured"}])


@mutation("R73", "", "a left-out column that is also a result to predict")
def _(s):
    _with_validation(s, left_out=[{"id": "hardness_kp", "why": "not trusted"}])


@mutation("R70", "", "a result to predict that is also an input")
def _(s):
    _with_validation(s, inputs=["drug_pct", "hardness_kp"])


@mutation("R71", "", "a supplier column that does not say whether it is confirmed")
def _(s):
    _with_validation(s, groups={"supplier": {"column": "binder_supplier"}})


@mutation("R72", "", "a column listed as calculated from itself")
def _(s):
    _with_validation(s, derived_from={"hardness_kp": ["hardness_kp"]})


# ------------------------------------------------------------------ running the cases
@dataclass
class CaseResult:
    case: Case
    passed: bool
    problem: Problem | None = None
    notes: list[str] = field(default_factory=list)


def run_case(one: Case) -> CaseResult:
    try:
        problems = one.run()
    except Exception as error:                      # noqa: BLE001 - a crash is a failed case, reported as such
        return CaseResult(one, False, None, [f"the validator crashed: {type(error).__name__}: {error}"])
    key = (one.rule, one.variant)
    if key not in CATALOGUE:
        return CaseResult(one, False, None, ["this rule is not in the message catalogue"])
    expected = CATALOGUE[key]
    matches = [p for p in problems if (p.rule, p.variant) == key]
    if not matches:
        found = ", ".join(sorted({p.rule + (f"/{p.variant}" if p.variant else "") for p in problems})) or "nothing"
        return CaseResult(one, False, None, [f"expected {one.rule}{'/' + one.variant if one.variant else ''} but found: {found}"])
    notes = []
    problem = matches[0]
    if problem.level != expected.level:
        notes.append(f"expected level {expected.level} but got {problem.level}")
    if one.rule != "X99" and any(p.rule == "X99" for p in problems):
        notes.append("a check failed unexpectedly (X99) - a rule cannot cope with this setup")
    for p in problems:
        notes += [f"{p.rule}: {w}" for w in wording_problems(p)]
    return CaseResult(one, not notes, problem, notes)


def run_all() -> list[CaseResult]:
    return [run_case(one) for one in CASES]


def uncovered() -> list[tuple[str, str]]:
    """Rules (and wording variants) in the catalogue that no case tests."""
    tested = {(one.rule, one.variant) for one in CASES}
    return sorted(set(CATALOGUE) - tested)
