"""The nine editing screens (the tenth, Review and save, is in review.py). Each draws fields; none calculates anything."""
from __future__ import annotations

import streamlit as st

from cellpoc.setup import allowed_symbols, list_layouts, options_at, station_ids

from . import style
from .widgets import Form, get_at

STEPS = options_at(("equipment", "steps", 0, "name"))
ACTIONS = options_at(("faults", "scripted", 0, "where", "action"))
DAYS = options_at(("calendar", "staffed_days"))


def ingredient_ids(f: Form) -> list[str]:
    return [i["id"] for i in (f.setup.get("ingredients") or []) if isinstance(i, dict) and isinstance(i.get("id"), str) and i["id"]]


def intro(text: str) -> None:
    st.caption(text)


# ------------------------------------------------------------------ 1 Project
def project(f: Form) -> None:
    intro("Name the study and say what kind of data it uses. Everything here is labelled 'illustrative' or 'synthetic' until real client data and expert review exist.")
    f.text(("project", "name"), "Study name", help="1 to 80 characters.")
    f.select(("project", "data_status"), "Data status", options_at(("project", "data_status")),
             help="From weakest to strongest: synthetic, illustrative, real, validated. A result is only as strong as its weakest input.")
    st.markdown("#### How the study's own outputs look")
    f.text(("display", "banner"), "Banner text", help="Must contain the word 'illustrative' or 'synthetic' while the data status is one of those.")
    f.text(("display", "accent_colour"), "Accent colour", help="A colour code such as #86BC25.")
    colour = get_at(f.setup, ("display", "accent_colour"))
    if isinstance(colour, str) and len(colour) == 7 and colour.startswith("#"):
        st.markdown(f"Colour shown here: {style.swatch(colour)} {colour}", unsafe_allow_html=True)
    f.text(("display", "font"), "Font", help="The font name. Open Sans is bundled; if a font is not installed, Arial is used.")


# ------------------------------------------------------------------ 2 Ingredients
def _ingredient(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("id",), "ID", help="Lowercase, ending in _pct, for example binder_pct.")
        f.select(p + ("role",), "Role", options_at(("ingredients", 0, "role")),
                 help="Exactly one ingredient must be the 'balance': 100% minus all the others, usually the filler.")
    with right:
        f.text(p + ("label",), "Name shown")
        st.caption("Unit: % of the tablet")
    low, high = st.columns(2)
    with low:
        f.number(p + ("min",), "Lowest value (%)", step=0.25)
    with high:
        f.number(p + ("max",), "Highest value (%)", step=0.25)


def _recipe_rule(f: Form, p: tuple) -> None:
    f.rule_select(p + ("rule",), "Kind of rule", options_at(("recipe_rules", 0, "rule")))
    f.text(p + ("label",), "Rule in words")
    kind = get_at(f.setup, p + ("rule",))
    if kind == "sum_to":
        left, right = st.columns(2)
        with left:
            f.number(p + ("total",), "Total (%)", step=1.0)
        with right:
            f.number(p + ("tolerance",), "Tolerance (%)", step=0.01)
    elif kind in ("at_most", "at_least"):
        f.multiselect(p + ("items",), "Ingredients in the rule", ingredient_ids(f))
        f.number(p + ("limit",), "Limit (%)", step=0.5)


def ingredients(f: Form) -> None:
    intro("The ingredients of the tablet and how far each may vary. Values are percentages of the tablet.")
    f.number(("batch_size_g",), "Batch size (grams)", step=1.0, help="Grams of powder blend made in each trial.")
    f.items(("ingredients",), "Ingredients", _ingredient,
            {"id": "", "label": "", "role": "other", "unit": "%", "min": None, "max": None}, "Add an ingredient",
            hint="At least two. One must be the balance.")
    f.items(("recipe_rules",), "Recipe rules", _recipe_rule,
            {"rule": "at_most", "items": [], "limit": None, "unit": "%", "label": ""}, "Add a recipe rule",
            hint="One rule must say the ingredients add up to 100%. Others can cap or floor a group of ingredients.")


# ------------------------------------------------------------------ 3 Process and context
def _process(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("id",), "ID", help="Ends in its unit, for example compression_force_kn.")
        f.text(p + ("unit",), "Unit", help="Allowed units: " + allowed_symbols() + ".")
    with right:
        f.text(p + ("label",), "Name shown")
    low, high = st.columns(2)
    with low:
        f.number(p + ("min",), "Lowest value", step=0.5)
    with high:
        f.number(p + ("max",), "Highest value", step=0.5)


def _context(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("id",), "ID")
    with right:
        f.text(p + ("label",), "Name shown")
    f.csv(p + ("values",), "Values (separated by commas)", help="For example A, B, C. List each value once.")


def process_and_context(f: Form) -> None:
    intro("Settings the engine may choose besides the recipe, and things that vary but are not chosen (they are recorded and allowed for).")
    f.items(("process_factors",), "Process settings", _process,
            {"id": "", "label": "", "unit": "", "min": None, "max": None}, "Add a process setting")
    f.items(("context_factors",), "Context factors", _context, {"id": "", "label": "", "values": []}, "Add a context factor")


# ------------------------------------------------------------------ 4 Targets
def _constraint(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("response",), "Result measured (ID)", help="Ends in its unit, for example hardness_kp.")
        f.text(p + ("unit",), "Unit", help="Allowed units: " + allowed_symbols() + ".")
    with right:
        f.text(p + ("label",), "Name shown")
        f.checkbox(p + ("required",), "Required (untick for an optional target)", missing=True)
    f.goal_select(p + ("goal",), "Goal", options_at(("targets", "constraints", 0, "goal")))
    goal = get_at(f.setup, p + ("goal",))
    if goal == "between":
        low, high = st.columns(2)
        with low:
            f.number(p + ("low",), "Lowest acceptable", step=0.5)
        with high:
            f.number(p + ("high",), "Highest acceptable", step=0.5)
    elif goal in ("at_least", "at_most"):
        f.number(p + ("value",), "Limit", step=0.5)
    f.number(p + ("margin_scale",), "Margin scale (optional)", step=0.5, optional=True,
             help="How much headroom counts as 'comfortably good'. Leave empty if not needed.")


def _objective(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("quantity",), "Quantity (ID)")
        f.text(p + ("unit",), "Unit", help="Allowed units: " + allowed_symbols() + ".")
    with right:
        f.text(p + ("label",), "Name shown")
        f.select(p + ("goal",), "Goal", options_at(("targets", "objectives", 0, "goal")))


def targets(f: Form) -> None:
    intro("What 'good' means. Constraints are limits a result must respect; objectives are things to push as far as possible after that.")
    f.items(("targets", "constraints"), "Constraints", _constraint,
            {"response": "", "label": "", "unit": "", "goal": "at_least", "value": None, "required": True},
            "Add a constraint", hint="At least one required constraint is needed.")
    f.items(("targets", "objectives"), "Objectives", _objective, {"quantity": "", "label": "", "unit": "", "goal": "maximise"}, "Add an objective")


# ------------------------------------------------------------------ 5 Equipment
def _step(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.select(p + ("name",), "Step", STEPS)
        f.number(p + ("time_min",), "Time (minutes)", step=5.0)
    with right:
        f.text(p + ("label",), "Name shown")
        f.multiselect(p + ("stations",), "Stations used", station_ids(f.layout) if f.layout else [])


def equipment(f: Form) -> None:
    intro("The cell: which layout it uses and how long each step takes. The five steps appear once each, in order.")
    names = [path.name for path in list_layouts()]
    current = get_at(f.setup, ("equipment", "layout_file"))
    f.select(("equipment", "layout_file"), "Layout file", names + ([current] if isinstance(current, str) and current and current not in names else []),
             help="The bundled example layout, or any file you put in the layouts folder.")
    f.items(("equipment", "steps"), "Steps", _step, {"name": None, "label": "", "time_min": None, "stations": []}, "Add a step")
    st.markdown("#### Phases")
    st.caption("Each trial is described as Sense, Reason, Act and Adapt. Say which steps belong to which phase.")
    f.select(("equipment", "measurement_step"), "Measurement step", STEPS, help="The result becomes known when this step finishes.")
    f.multiselect(("equipment", "phases", "act"), "Act steps (making the tablets)", STEPS)
    f.multiselect(("equipment", "phases", "sense"), "Sense steps (measuring them)", STEPS)
    f.select(("equipment", "phases", "reason_adapt_step"), "Reason and Adapt happen during", STEPS, help="Must be the last step.")
    f.number(("equipment", "phases", "reason_min"), "Minutes of Reason (the rest of that step is Adapt)", step=5.0)


# ------------------------------------------------------------------ 6 Calendar
def calendar(f: Form) -> None:
    intro("When the run starts, how long it lasts, and when people are in the building.")
    left, right = st.columns(2)
    with left:
        f.text(("calendar", "start"), "Start (date and time)", placeholder="2026-10-09 18:00", help="Write it like 2026-10-09 18:00.")
    with right:
        f.number(("calendar", "duration_h"), "Duration (hours)", step=1.0)
    f.multiselect(("calendar", "staffed_days"), "Days when people are in the lab", DAYS)
    left, right = st.columns(2)
    with left:
        f.text(("calendar", "staffed_from"), "Staffed from", placeholder="08:00", help="Write it like 08:00.")
    with right:
        f.text(("calendar", "staffed_until"), "Staffed until", placeholder="18:00", help="Write it like 18:00.")


# ------------------------------------------------------------------ 7 Faults
def _where(f: Form, p: tuple) -> None:
    left, right, third = st.columns(3)
    with left:
        f.select(p + ("where", "step"), "Step", STEPS)
    with right:
        f.select(p + ("where", "action"), "Action", ACTIONS)
    with third:
        choices = ingredient_ids(f)
        held = get_at(f.setup, p + ("where", "ingredient"))
        f.select(p + ("where", "ingredient"), "Ingredient (for a pour)", choices + ([held] if isinstance(held, str) and held not in choices else []), optional=True)


def _scripted(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.number(p + ("trial",), "On trial number", integer=True)
        f.text(p + ("cause",), "Cause", help="For example: binder bottle jam.")
    with right:
        f.checkbox(p + ("retry_succeeds",), "The retry succeeds", help="Tick: the retry works. Untick: the retry fails and the candidate is skipped.")
    _where(f, p)


def _random(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("cause",), "Cause")
    with right:
        f.number(p + ("chance_per_trial",), "Chance per trial (0 to 1)", step=0.01, help="A probability, for example 0.05 for 5%.")
        f.number(p + ("retry_succeeds_chance",), "Chance the retry works (0 to 1)", step=0.05)
    _where(f, p)


def faults(f: Form) -> None:
    intro("Things that go wrong on purpose (scripted) or by chance (random), and how the cell recovers.")
    left, right = st.columns(2)
    with left:
        f.number(("faults", "purge_min"), "Purge time after a failure (minutes)", step=5.0)
        f.number(("faults", "recovery", "tap_shake_s"), "Tap-and-shake time (seconds)", step=10.0)
    with right:
        f.number(("faults", "recovery", "max_retries"), "Maximum retries", integer=True)
        f.checkbox(("faults", "clean_after_skip"), "Do a full cleaning step after a skipped candidate")
    f.items(("faults", "scripted"), "Scripted faults", _scripted,
            {"trial": None, "where": {"step": None, "action": None}, "cause": "", "retry_succeeds": True}, "Add a scripted fault")
    f.items(("faults", "random"), "Random faults", _random,
            {"where": {"step": None, "action": None}, "cause": "", "chance_per_trial": None, "retry_succeeds_chance": None}, "Add a random fault")


# ------------------------------------------------------------------ 8 Baseline and engine
def _noise(f: Form, p: tuple) -> None:
    left, right = st.columns(2)
    with left:
        f.text(p + ("quantity",), "Measured quantity (ID)")
    with right:
        f.number(p + ("sd",), "Scatter (standard deviation, in the quantity's own unit)", step=0.05)


def baseline_and_engine(f: Form) -> None:
    intro("The manual baseline the autonomous cell is compared against, how many campaigns to compare, and the engine and simulated-lab settings. These are settings only: this app calculates no results.")
    f.number(("baseline", "manual_trials_per_week"), "Manual trials per week", step=1.0, help="The dashboard divides by this.")
    left, right = st.columns(2)
    with left:
        f.number(("comparison", "campaigns"), "Campaigns to compare", integer=True)
    with right:
        f.number(("comparison", "trials_per_campaign"), "Trials per campaign", integer=True)
    left, right, third = st.columns(3)
    with left:
        f.number(("engine", "initial_recipes"), "Spread-out starting recipes", integer=True)
    with right:
        f.number(("engine", "candidates_per_decision"), "Candidates weighed per decision", integer=True)
    with third:
        f.text(("engine", "model"), "Model", help="'auto' means the best-validated model.")
    f.number(("seeds", "run"), "Random seed", integer=True, help="The same seed gives identical results every time.")
    f.items(("virtual_lab", "noise"), "Instrument scatter in the simulated lab", _noise, {"quantity": "", "sd": None}, "Add a scatter value")


# ------------------------------------------------------------------ 9 Data
def data(f: Form) -> None:
    intro("How to read the client's experiment table. File names are relative to the project folder or the setups folder: no drive letters and no '..'. Put real client files in data/client/ (never saved to git).")
    left, right = st.columns(2)
    with left:
        f.text(("data", "experiments_file"), "Experiments file", help="For example data/client/experiments.csv")
    with right:
        f.text(("data", "meta_file"), "Companion file", help="The .meta.json file that goes with the table.")
    left, right = st.columns(2)
    with left:
        f.text(("data", "encoding"), "Encoding")
    with right:
        f.select(("data", "line_endings"), "Line endings", options_at(("data", "line_endings")))
    st.markdown("#### Identifying columns")
    cols = st.columns(3)
    for n, name in enumerate(("experiment", "replicate", "batch", "date", "status", "failure_reason")):
        with cols[n % 3]:
            f.text(("data", "id_columns", name), name.replace("_", " ").capitalize() + " column")
    f.rows(("data", "column_map"), "Column mapping", "Column in the file", "Becomes (ID)",
           hint="Each column of the table that the platform should use, and the ID it becomes.")
    st.markdown("#### Hardness")
    left, right, third = st.columns(3)
    with left:
        f.text(("data", "hardness", "value_column"), "Value column")
    with right:
        f.text(("data", "hardness", "unit_column"), "Unit column")
    with third:
        f.text(("data", "hardness", "to"), "Becomes (ID)")
    f.rows(("data", "hardness", "conversions"), "Unit conversions", "Unit in the file", "Divide by", wrap=True,
           hint="Newtons divided by 9.807 give kP. Include a row for kP (divide by 1).")
    st.markdown("#### Results reported as 'below the limit'")
    left, right, third = st.columns(3)
    with left:
        f.text(("data", "below_detection", "note_column"), "Note column")
        f.text(("data", "below_detection", "marker"), "Marker", placeholder="<0.05")
    with right:
        f.text(("data", "below_detection", "quantity"), "Quantity (ID)")
        f.number(("data", "below_detection", "limit"), "Limit", step=0.01)
    with third:
        f.select(("data", "below_detection", "rule"), "What to do", options_at(("data", "below_detection", "rule")))
    st.markdown("#### Replicates, missing values and failed runs")
    left, right = st.columns(2)
    with left:
        f.csv(("data", "replicates", "group_by"), "Group replicates by (columns, separated by commas)")
        f.select(("data", "replicates", "rule"), "Combine replicates by", options_at(("data", "replicates", "rule")))
        f.checkbox(("data", "replicates", "keep_individual_rows_for_noise_estimate"), "Keep individual rows to estimate noise")
    with right:
        f.select(("data", "missing_values", "policy"), "Missing values", options_at(("data", "missing_values", "policy")))
        f.text(("data", "failed_runs", "status_column"), "Status column")
        f.text(("data", "failed_runs", "failed_value"), "Value that means failed")
        f.select(("data", "failed_runs", "policy"), "Failed runs", options_at(("data", "failed_runs", "policy")))


SCREEN_FUNCTIONS = [project, ingredients, process_and_context, targets, equipment, calendar, faults, baseline_and_engine, data]
