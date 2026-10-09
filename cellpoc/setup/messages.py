"""Every message the setup validator can show, in one place, so the wording can be reviewed without reading code.

Each entry is a rule (an ID such as R05, plus a variant when one rule has more than one wording), what it checks,
whether it is an error (blocks saving), a warning or a note, and the text. The full message shown to a person is
"<Screen> > <Field>: <text>". docs/setup_messages.md is generated from this catalogue and the tests.
"""
from __future__ import annotations

from dataclasses import dataclass

from .units import allowed_symbols


@dataclass(frozen=True)
class Rule:
    id: str
    variant: str
    level: str          # error, warning or note
    screen: str         # the screen it belongs to ("" = decided by where the problem is)
    what: str           # what is checked, in words
    template: str       # the message text, with {placeholders}


CATALOGUE: dict[tuple[str, str], Rule] = {}


def _add(rule_id: str, variant: str, level: str, screen: str, what: str, template: str) -> None:
    CATALOGUE[(rule_id, variant)] = Rule(rule_id, variant, level, screen, what, template)


SETUP_FILE = "Setup file"

# ---------------------------------------------------------------- the file itself
_add("F01", "", "error", SETUP_FILE, "the file can be read as text",
     "the file isn't plain text in the usual UTF-8 format, so it can't be read. Save it as text and try again.")
_add("F02", "", "error", SETUP_FILE, "the file is written correctly",
     "the file isn't written correctly near line {line}, column {column} (check the indentation and the colons). Compare it with the example setup.")
_add("F03", "", "error", SETUP_FILE, "the file is not too big",
     "the file is {mb} MB, which is too big for a setup (the limit is 1 MB). Check that it is the right file.")
_add("T01", "", "error", SETUP_FILE, "the file is made of named sections",
     "the file must be made of named sections such as 'project' and 'ingredients' (this one is {what}). Start from the example setup.")
_add("V01", "", "error", SETUP_FILE, "the setup has a format version",
     "this setup has no format version, so it can't be read safely. Add 'format_version: 1' at the top.")
_add("V02", "not_a_number", "error", SETUP_FILE, "the format version is a whole number",
     "the format version must be a whole number such as 1 (you wrote {shown}). Fix it at the top of the file.")
_add("V02", "too_old", "error", SETUP_FILE, "the format version is not older than the oldest readable",
     "this setup is in format version {version}, which is older than any this program can read (it reads {oldest} to {current}). Open it in an older program and save it again.")
_add("V02", "no_path", "error", SETUP_FILE, "an older format can be brought up to date",
     "this setup is in format version {version} and this program has no way to bring it up to version {current}. Open it in an older program, or start again from the example.")
_add("V03", "", "error", SETUP_FILE, "the format version is not newer than this program knows",
     "this setup was saved in a newer format (version {version}). This program understands formats up to {current}. Update the program, or open the file in the newer program and save it in an older format.")
_add("V04", "", "note", SETUP_FILE, "an older setup was brought up to date",
     "this setup was saved in an older format (version {version}) and was updated to version {current} when it was opened. Save it to keep the update.")
_add("V05", "", "warning", SETUP_FILE, "the saved fingerprint still matches the content",
     "this setup was changed after it was saved (its fingerprint no longer matches). If you edited it by hand that is fine; save it again to refresh the fingerprint.")
_add("X99", "", "warning", SETUP_FILE, "a check could not run because the layout was unexpected",
     "part of this setup could not be fully checked because it is not laid out as expected. Fix the other messages first.")

# ---------------------------------------------------------------- generic messages for anything not covered by a specific rule
_add("S01", "", "error", "", "a required field is present", "this is missing. Add it.")
_add("S02", "", "error", "", "a value is the right kind (number, text, list, yes/no)", "must be {kind} (you wrote {shown}).")
_add("S03", "", "error", "", "a value is one of the allowed choices", "must be one of: {options} (you wrote {shown}).")
_add("S04", "", "error", "", "a number is inside its allowed range", "must be {bound} {limit} (you wrote {shown}).")
_add("S05", "empty", "error", "", "a text is not empty", "must not be empty. Write something here.")
_add("S05", "long", "error", "", "a text is not too long", "is too long: {n} characters, and the limit is {limit}. Shorten it.")
_add("S06", "id", "error", "", "an ID is written in the allowed form",
     "must start with a lowercase letter and use only lowercase letters, digits and underscores (you wrote {shown}).")
_add("S06", "other", "error", "", "a value is written in the expected form", "is not written in the expected form (you wrote {shown}). Compare it with the example setup.")
_add("S07", "", "error", "", "no unknown setting names", "'{name}' is not a setting this program knows. Check the spelling, or remove it.")
_add("S08", "", "error", "", "a list has enough items", "needs at least {n} item{s} but has {have}. Add one.")
_add("S09", "", "error", "", "a list has no repeats", "has repeated entries. List each one once.")
_add("S10", "", "error", "", "any other value problem", "has a value that is not allowed. Compare it with the example setup.")
_add("S11", "", "error", "", "a value is the one fixed value required", "must be exactly {expected} (you wrote {shown}).")

# ---------------------------------------------------------------- 1 Project
_add("R01", "", "error", "Project", "the study has a name", "give the study a name (1 to 80 characters).")
_add("R01", "long", "error", "Project", "the study name is not too long", "the name is {n} characters long. Shorten it to 80 or fewer.")
_add("R02", "", "error", "Project", "the banner carries the data-status label",
     "while the data status is '{status}' the banner must say so. Add the word 'illustrative' or 'synthetic', for example 'Simulation with illustrative values'.")
_add("R03", "", "error", "Project", "the accent colour is a colour code",
     "write the colour as # followed by six letters or digits, for example #86BC25 (you wrote {shown}).")
_add("R04", "real", "warning", "Project", "choosing 'real' reminds about data handling",
     "'real' means real client data. The client's data-handling policy must be approved before real data is used. Keep real data in data/client/, which is never saved to git.")
_add("R04", "validated", "warning", "Project", "choosing 'validated' reminds about review and data handling",
     "'validated' means real client data that an expert has reviewed. Choose it only after that review, and only when the client's data-handling policy has been approved.")

# ---------------------------------------------------------------- 2 Ingredients
_add("R05", "", "error", "", "a lowest value is below its highest value",
     "the lowest value ({lo}) must be below the highest ({hi}). Swap them or change one.")
_add("R06", "", "error", "Ingredients", "an ingredient percentage is between 0% and 100%",
     "values must be between 0% and 100% (you wrote {shown}). Change it.")
_add("R07", "none", "error", "Ingredients", "exactly one ingredient is the balance",
     "choose exactly one ingredient as the balance (usually the filler): it is 100% minus all the others. You chose {n}.")
_add("R07", "many", "error", "Ingredients", "exactly one ingredient is the balance",
     "choose exactly one ingredient as the balance (usually the filler): it is 100% minus all the others. You chose {n}.")
_add("R08", "", "error", "", "no two items share an ID", "two items use the ID '{id}'. Give each a different ID.")
_add("R09", "unreachable", "error", "Ingredients", "the balance ingredient can reach 100%",
     "with these ranges the {name} would have to be between {lo}% and {hi}%, but you only allow {bmin}% to {bmax}%, so no recipe can add up to 100%. Widen the {name}'s range or narrow another ingredient.")
_add("R09", "narrower", "warning", "Ingredients", "the balance range is not tighter than what the others leave",
     "some recipes the other ingredients allow can't be made: the {name} would have to be between {lo}% and {hi}%, but you only allow {bmin}% to {bmax}%. That is allowed, but it shrinks the recipe space.")
_add("R10", "", "error", "Ingredients", "the batch size is more than 0 grams", "must be more than 0 grams (you wrote {shown}). Type the batch size in grams.")
_add("R10", "type", "error", "Ingredients", "the batch size is a number", "must be a number of grams (you wrote {shown}). Type the batch size in grams.")
_add("R11", "at_most", "error", "Ingredients", "an 'at most' recipe rule can be met",
     "'{rule}': the lowest allowed values of {names} already add up to {sum}%, so no recipe can stay within {limit}%. Raise the limit or lower their lowest values.")
_add("R11", "at_least", "error", "Ingredients", "an 'at least' recipe rule can be met",
     "'{rule}': the highest allowed values of {names} only add up to {sum}%, so no recipe can reach {limit}%. Lower the limit or raise their highest values.")
_add("R42", "", "error", "Ingredients", "recipe rules only name ingredients that exist",
     "'{rule}': '{id}' is not an ingredient in this setup. Choose one from the Ingredients table.")
_add("R43", "missing", "error", "Ingredients", "there is a rule that ingredients add up to 100%",
     "add the rule that the ingredients must add up to 100%.")
_add("R43", "many", "error", "Ingredients", "there is only one 'add up to' rule",
     "there is more than one 'add up to' rule. Keep one.")
_add("R43", "total", "error", "Ingredients", "the 'add up to' total is 100%",
     "the total must be 100% (you wrote {total}%). Change it to 100.")

# ---------------------------------------------------------------- 3 Process and context
_add("R12", "conflict", "error", "Process and context", "a process setting's unit agrees with its ID",
     "the ID '{id}' ends in '{suffix}' ({suffix_name}) but the unit says '{unit}' ({unit_name}). These conflict: make them agree.")
_add("R12", "unknown_unit", "warning", "Process and context", "a process setting's unit is one this program knows",
     "the unit '{unit}' is not one this program knows, so it can't be double-checked. Allowed units: {allowed_units}.")
_add("R12", "no_suffix", "warning", "Process and context", "a process setting's ID ends with a unit",
     "the ID '{id}' does not end with a unit such as {examples}, so its unit can't be double-checked. Consider renaming it.")
_add("R12", "case", "warning", "Process and context", "a process setting's unit has the usual capital letters",
     "write the unit as '{canonical}' (you wrote '{unit}').")
_add("R13", "empty", "error", "Process and context", "a context factor lists at least one value", "list at least one value.")
_add("R13", "repeats", "error", "Process and context", "a context factor lists each value once",
     "list each value once (you wrote {shown}).")

# ---------------------------------------------------------------- 4 Targets
_add("R14", "", "error", "Targets", "'between' has a lowest value below its highest",
     "'between' needs a lowest value ({low}) below the highest ({high}). Swap them or change one.")
_add("R15", "at_least", "error", "Targets", "'at least' has a number", "'at least' needs a number. Type the limit, for example 85.")
_add("R15", "at_most", "error", "Targets", "'at most' has a number", "'at most' needs a number. Type the limit, for example 1.0.")
_add("R15", "between", "error", "Targets", "'between' has a lowest and a highest value", "'between' needs a lowest and a highest value. Type both.")
_add("R16", "", "error", "Targets", "at least one target is required",
     "add at least one required target, otherwise nothing decides what 'good' means.")
_add("R17", "needed", "error", "Targets", "a result that matters can be read by a station in the layout",
     "'{name}' is {why} but no station in the chosen layout can read it. Choose a layout with an instrument for it, or remove it.")
_add("R17", "optional", "warning", "Targets", "an optional result can be read by a station in the layout",
     "'{name}' is an optional target and no station in the chosen layout can read it, so it will be ignored. Choose a layout with an instrument for it, or remove it.")
_add("R18", "", "error", "Targets", "no objective is both maximised and minimised",
     "you asked to both maximise and minimise '{name}'. Keep one.")
_add("R19", "conflict", "error", "Targets", "a target's unit agrees with its ID",
     "the ID '{id}' ends in '{suffix}' ({suffix_name}) but the unit says '{unit}' ({unit_name}). These conflict: make them agree.")
_add("R19", "unknown_unit", "warning", "Targets", "a target's unit is one this program knows",
     "the unit '{unit}' is not one this program knows, so it can't be double-checked. Allowed units: {allowed_units}.")
_add("R19", "no_suffix", "warning", "Targets", "a target's ID ends with a unit",
     "the ID '{id}' does not end with a unit such as {examples}, so its unit can't be double-checked. Consider renaming it.")
_add("R19", "case", "warning", "Targets", "a target's unit has the usual capital letters", "write the unit as '{canonical}' (you wrote '{unit}').")

# ---------------------------------------------------------------- 5 Equipment
_add("R20", "", "error", "Equipment", "a step takes more than 0 minutes", "a step must take more than 0 minutes (you wrote {shown}). Type the time in minutes.")
_add("R21", "", "error", "Equipment", "a step only uses stations that exist in the layout",
     "'{station}' is not a station in this layout. The layout has: {stations}. Choose from those.")
_add("R22", "", "error", "Equipment", "Reason leaves time for Adapt",
     "Reason takes {reason} minutes but the {step} step lasts {total}, which leaves no time for Adapt. Shorten Reason or lengthen {step}.")
_add("R23", "", "error", "Equipment", "Reason and Adapt happen in the last step",
     "Reason and Adapt happen in the last step, but '{step}' is not the last step ('{last}' is). Choose '{last}'.")
_add("R24", "tight", "warning", "Equipment", "the layout's spare reach is at least 0.10 m",
     "the layout's tightest spot has only {margin} m of spare reach (a warning below 0.10 m): {where}. It still works; moving it would add margin.")
_add("R24", "very_tight", "error", "Equipment", "the layout's spare reach is at least 0.03 m",
     "the layout's tightest spot has only {margin} m of spare reach (the limit is 0.03 m): {where}. Move it closer to the arm or choose another layout.")
_add("R24", "beyond", "error", "Equipment", "everything in the layout is within the arm's reach",
     "{where} is out of the arm's reach. Move it closer to the arm or choose another layout.")
_add("R25", "", "error", "", "a file name stays inside the project",
     "file names must be inside the project folder: no drive letter, no leading slash and no '..' (you wrote {shown}). Use a plain relative name.")
_add("R45", "phase", "error", "Equipment", "a phase only names steps that exist",
     "the '{step}' step is used in the phases but is not in the list of steps. Add the step or take it out of the phases.")
_add("R45", "measurement", "error", "Equipment", "the measurement step exists",
     "the measurement step '{step}' is not in the list of steps. Choose one of the steps.")
_add("R47", "", "error", "Equipment", "the five steps appear once each, in order",
     "the five steps (dispense, mix, press, test, clean) must each appear once, in that order. This setup has: {found}.")
_add("R51", "", "error", "Equipment", "the layout file exists",
     "'{ref}' was not found. Looked in the project folder and next to the setup file. Check the name, or choose a layout from the list.")
_add("R52", "", "error", "Equipment", "the layout file is a usable layout",
     "the layout file can't be used: {why}. Choose another layout or fix the file.")

# ---------------------------------------------------------------- 6 Calendar
_add("R26", "", "error", "Calendar", "opening time is before closing time",
     "opening time ({start}) must be before closing time ({end}). Swap them or change one.")
_add("R27", "", "error", "Calendar", "the run is at least one trial long",
     "the run ({run} hours) is shorter than one trial ({trial} hours), so no trial can finish. Lengthen the run.")
_add("R28", "", "error", "Calendar", "the start is a real date and time",
     "{shown} is not a date and time. Write it like 2026-10-09 18:00.")
_add("R53", "", "error", "Calendar", "opening and closing times are real times",
     "{shown} is not a time. Write it like 08:00.")

# ---------------------------------------------------------------- 7 Faults
_add("R29", "", "error", "Faults", "a scripted fault is on a trial that exists",
     "trial {trial} can't happen: a campaign has {trials} trials. Choose a trial from 1 to {trials}.")
_add("R30", "", "error", "Faults", "each trial has at most one scripted fault", "two scripted faults hit trial {trial}. Use one per trial.")
_add("R31", "pour_needs_ingredient", "error", "Faults", "a fault on a pour says which ingredient", "a fault on a pour must say which ingredient. Choose one.")
_add("R31", "unknown_ingredient", "error", "Faults", "a fault names an ingredient that exists", "'{ingredient}' is not an ingredient in this setup. Choose one from the Ingredients table.")
_add("R32", "", "error", "Faults", "a chance is a probability from 0 to 1",
     "the chance must be a probability from 0 to 1 (you wrote {shown}). {example}")
_add("R48", "", "error", "Faults", "a fault names a step that exists",
     "'{step}' is not a step in this setup. Choose one of the steps.")

# ---------------------------------------------------------------- 8 Baseline and engine
_add("R33", "", "error", "Baseline and engine", "the starting recipes fit in a campaign",
     "{n} starting recipes is more than the {trials} trials in a campaign. Lower it or raise the trials per campaign.")
_add("R34", "", "error", "Baseline and engine", "the manual baseline is more than 0",
     "must be more than 0 (the dashboard divides by it; you wrote {shown}). Type the manual trials per week.")
_add("R35", "", "error", "Baseline and engine", "noise is only given for measured results",
     "noise is given for '{quantity}', which is not a measured result in this setup. Measured results are: {results}.")

# ---------------------------------------------------------------- 9 Data
_add("R36", "experiments", "error", "Data", "the experiments file exists",
     "'{ref}' was not found. Looked in the project folder and next to the setup file. Check the name, or put the file in data/client/.")
_add("R36", "meta", "error", "Data", "the companion file exists",
     "'{ref}' was not found. Looked in the project folder and next to the setup file. Every experiments file needs its companion .meta.json file.")
_add("R37", "", "error", "Data", "every mapped column is in the file",
     "the file has no column called '{column}'. It has: {have}. Fix the name in the mapping.")
_add("R38", "", "error", "Data", "everything the setup needs is mapped to a column",
     "nothing maps to '{id}', but {why}. Add a column for it in the mapping.")
_add("R39", "", "error", "Data", "no two columns map to the same ID",
     "two columns ('{first}' and '{second}') both map to '{id}'. Each ID can come from one column.")
_add("R40", "missing_kp", "error", "Data", "hardness conversions include kP",
     "add a conversion for 'kP' (divide by 1) as well as for the other units.")
_add("R50", "newtons", "warning", "Data", "the newtons conversion is the usual one",
     "newtons are normally divided by 9.807 to give kP (you wrote {value}). Check this is intended.")
_add("R41", "", "note", "Data", "the experiment table's data status is shown",
     "the experiment table is marked '{status}', so results will be labelled '{status}'.")
_add("R54", "", "warning", "Data", "every mapped ID is used by this setup",
     "column '{column}' maps to '{id}', which this setup does not use. Remove it or add '{id}' to the setup.")


def rule_for(rule_id: str, variant: str = "") -> Rule:
    return CATALOGUE[(rule_id, variant)]


def render(rule_id: str, variant: str = "", **values) -> str:
    values.setdefault("allowed_units", allowed_symbols())      # always read from the one list of units, when the message is built
    return CATALOGUE[(rule_id, variant)].template.format(**values)


def make_problem(rule_id: str, variant: str, path: tuple, setup=None, **values):
    """Build a Problem: the catalogue's wording filled in, placed on the right screen at the right field."""
    from .problems import Problem, field_label, path_text, screen_for

    rule = CATALOGUE[(rule_id, variant)]
    screen = rule.screen or screen_for(path)
    return Problem(rule_id, variant, rule.level, screen, field_label(setup, path) if setup is not None else "",
                   path_text(path), render(rule_id, variant, **values))
