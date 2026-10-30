"""The applicability-domain reports: one plain document per table and one summary.

They keep the three statuses of 3b-1 apart (carried, carried but exploratory, not assessed), carry every table's label in every heading, and put the safeguard message first:
no model's stated range tracks its own error (see the calibration report), so these warnings are the only thing that can say "do not trust this prediction".
There is deliberately NO combined "warned" flag. Four separate warning statuses are reported for every carried result and hold-out type, each with its own evidence:
 per recipe: far from the training recipes (distance); per recipe: a numeric input outside the range seen; per recipe: an unseen supplier or product (a category value never seen);
 whole group: an unfamiliar batch, supplier or time period.
The reports also say whether the distance threshold is steady across folds, next to how much the recalibration factor swung for the same folds. No clock time.
"""
from __future__ import annotations

from .carry import BORDERLINE, CARRIED, SKIPPED, STATUS_WORDS, CarryDecision, decide
from .domain import K_NEIGHBOURS, QUANTILE, RANGE_TOLERANCE, STABLE_RATIO, VARYING_RATIO, stability, threshold_swing
from .group_domain import MIN_GROUP_ROWS, MIN_NULL_GROUPS, NOUN, REFERENCE_SIZE, evaluate_groups
from .validate import Validation

SAFEGUARD = ("**These warnings are the platform's main safeguard right now.** The calibration report found that no model's stated range tracks its own error: the Gaussian processes and the "
             "neural-network ensemble state ranges that vary from recipe to recipe but do not follow the real errors, and the regressions and boosted trees state the same range for every recipe. "
             "So a model cannot tell you when it is unsure. These warnings look only at the inputs and say when a recipe, or a whole group of recipes, is far from the data the model learned from.")
STATUSES = ("Four separate warning statuses are reported and none is folded into another: **(1) per recipe, distance:** far from the training recipes; **(2) per recipe, numeric range:** a numeric input "
            "outside the range seen in training; **(3) per recipe, unseen supplier or product:** a category value (a supplier, a product code) the model never saw; **(4) whole group:** this whole batch "
            "of recipes, supplier or time period looks unfamiliar.")
EXPLAIN = [
    STATUSES,
    f"**(1) Distance.** A recipe is warned when its mean distance to the {K_NEIGHBOURS} nearest training rows is above the {QUANTILE:.0%} point of the same distance measured for the training rows "
    "themselves, each only against rows from OTHER groups (so it mimics how far a whole new group normally sits). **(2) Range:** a numeric input is beyond the training range by more than "
    f"{RANGE_TOLERANCE:.0%} of that range (this tolerance is fixed and has not been changed). **(3) Unseen supplier or product:** the value of a category input was never seen in training; the values are named.",
    "**Error ratio** is the average error of warned rows (or groups) divided by that of unwarned ones: above 1 means the warning really picks out the bad predictions. **Lift** is the share of the 10% "
    "largest errors that were warned, divided by the share warned overall: above 1 beats chance. Both use the chosen model's saved held-out answers; '-' means too few warned or unwarned rows.",
    "**Far-away recipes warned** is the share of deliberately far-away copies of the held-out rows (every numeric input pushed 8 standard deviations away) that the distance check warned: it should be close to 1.",
    f"**(4) Whole group.** For a group of recipes that arrive together (a batch, a supplier, a block of dates), the average of the group is compared with the average of the training rows. If the group's "
    "average is further off than the average of an ordinary group of the same size, the group is flagged, and the inputs that moved most are named. 'Other training groups' means the threshold is built from "
    f"ordinary groups in the training data (at least {MIN_NULL_GROUPS} are needed, so ordinary differences between groups are allowed for); **'chance alone' means there were too few training groups to know how much "
    "groups normally differ, so the group is compared with random recipes and is flagged more readily than it should be.** Groups of fewer than "
    f"{MIN_GROUP_ROWS} recipes are not assessed.",
    f"**Is the threshold itself steady?** Each threshold is set separately inside every fold. If it swung between folds the warning would be unreliable under a shift, as the recalibration factor was. "
    f"Largest over smallest up to {STABLE_RATIO} is called stable, up to {VARYING_RATIO} varying, above swinging. The recalibration factors of the same folds are shown for comparison, and so is the "
    "distance threshold when the reference groups are always batches (a diagnostic).",
    "An unseen-supplier-or-product warning that fires for every row means the held-out group's identity (a supplier, a product code) is itself an input value the model never saw.",
]


def _pct(x) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def _num(x, digits: int = 2) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def _swing(s) -> str:
    return "n/a" if s is None else f"{s[0]:.2f} ({s[1]})"


def _basis(groups) -> str:
    if not groups.groups:
        return "-"
    based = sum(g.warning.null_kind == "group-based" for g in groups.groups)
    chance = len(groups.groups) - based
    return "other training groups" if not chance else "chance alone" if not based else f"other training groups for {based}, chance alone for {chance}"


def _tables(validation: Validation, result: str, chosen: str, references: dict) -> list[str]:
    info = stability(validation, result, chosen, references)
    groups = {kind: evaluate_groups(validation, result, kind, chosen) for kind in info}
    lines = [f"The chosen model's saved held-out answers ({chosen}) are used only to measure whether warned rows or groups have bigger errors.", "",
             "**Per recipe: three separate statuses**", "",
             "| Hold-out | Held-out rows | (1) Distance: warned | error ratio | lift | (2) Numeric range: warned | error ratio | lift | (3) Unseen supplier or product: warned | the unseen values | Far-away recipes warned | Distance vs error (rank correlation) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kind, (own, alt, st) in info.items():
        p = own.parts
        seen = "; ".join(f"{c} = {v} ({n:,} row{'' if n == 1 else 's'})" for c, v, n in own.unseen) or "none"
        lines.append(f"| {own.heading} | {own.n:,} | {_pct(p['distance'].share)} | {_num(p['distance'].error_ratio)} | {_num(p['distance'].lift)} | {_pct(p['range'].share)} | {_num(p['range'].error_ratio)} | "
                     f"{_num(p['range'].lift)} | {_pct(p['category'].share)} | {seen} | {_pct(own.far)} | {_num(own.rank_correlation)} |")
    lines += ["", f"**Whole group: is this batch, supplier or time period unfamiliar?** (a group needs at least {MIN_GROUP_ROWS} recipes)", "",
              f"| Hold-out | (4) Groups flagged as unfamiliar | Groups assessed (too small to assess) | Threshold made from | Error ratio, flagged over unflagged groups | Rank correlation across groups | Threshold for {REFERENCE_SIZE} recipes on each fold | Largest ÷ smallest | Inputs that moved most in flagged groups |",
              "|---|---|---|---|---|---|---|---|---|"]
    for kind, g in groups.items():
        if g is None:
            continue
        values = [t for t, _ in g.reference_thresholds]
        moved = ", ".join(f"{n} ({c})" for n, c in g.top_shifted()) or "-"
        lines.append(f"| {g.heading} | {_pct(g.flagged_share)} of {NOUN[kind]} | {len(g.groups)} ({g.n_small}) | {_basis(g)} | {_num(g.error_ratio)} | {_num(g.rank_correlation)} | "
                     f"{', '.join(f'{t:.2f}' for t in values)} | {_swing(threshold_swing(values))} | {moved} |")
    lines += ["", "**Is the distance threshold steady across folds?**", "",
              "| Hold-out | Distance threshold on each fold | Largest ÷ smallest | Same, reference groups always batches | Recalibration factors (same folds) | Distance warned per fold |", "|---|---|---|---|---|---|"]
    for kind, (own, alt, st) in info.items():
        rates = st.rates["distance"]
        shares = f"{_pct(min(rates))} to {_pct(max(rates))}" if rates else "-"
        lines.append(f"| {own.heading} | {', '.join('n/a' if t is None else f'{t:.2f}' for t in st.thresholds)} | {_swing(st.swing)} | {_swing(st.batch_swing) if st.batch_swing else 'n/a'} | {_swing(st.factor_swing)} | {shares} |")
    notes = [f"- {f.place}: {f.text}" for kind, (own, alt, st) in info.items() for f in st.findings] + [f"- {f.place}: {f.text}" for g in groups.values() if g for f in g.findings]
    tops = [f"- {own.heading}: numeric inputs most often out of range: " + ", ".join(f"{n} ({c:,} rows)" for n, c in own.top_inputs) for kind, (own, alt, st) in info.items() if own.top_inputs]
    return lines + [""] + notes + tops + ([""] if notes or tops else [])


def _section(validation: Validation, decisions: list[CarryDecision], level: str, tag: str, references: dict) -> list[str]:
    table = validation.table
    lines = []
    for d in decisions:
        suffix = f" [{d.tag}]" if d.tag else ""
        lines += [f"{level} {table.column_label(d.result)}: {STATUS_WORDS[d.status]}{suffix}{tag}", ""]
        if d.status == BORDERLINE:
            lines += [f"**{d.tag}.**", ""]
        if d.result in table.derived_from:
            lines += [f"`{table.column_label(d.result)}` is calculated from other columns, so it is not an independent finding.", ""]
        lines += _tables(validation, d.result, d.chosen, references)
    return lines


def _skipped_line(text: str) -> str:
    return text.replace("Calibration not assessed", "Warning evaluation not assessed").replace("A calibration number", "A warning evaluation")


def build_report(validation: Validation, decisions: list[CarryDecision] | None = None) -> str:
    table = validation.table
    decisions = decisions or [decide(validation, r) for r, t in table.responses.items() if t.usable]
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    tag = f" [{table.tag}]" if table.tag else ""
    references: dict = {}
    lines = [f"# Applicability-domain warnings [{label}]{tag}: {table.name}", "",
             f"**This report is {label}.** It tests whether the warnings flag recipes and groups far from the data, on this table only. It is not a prediction about real tablets or a client.", ""]
    if table.tag:
        lines += [f"**{table.tag}.**", ""]
    lines += [SAFEGUARD, "", f"## How to read this{tag}", ""] + [f"- {e}" for e in EXPLAIN] + [""]
    for status, title in ((CARRIED, "Carried results"), (BORDERLINE, "Carried but exploratory results (borderline)")):
        group = [d for d in decisions if d.status == status]
        if group:
            lines += [f"## {title}{tag}", ""] + _section(validation, group, "###", tag, references)
    skipped = [d for d in decisions if d.status == SKIPPED]
    if skipped:
        lines += [f"## Not assessed (skipped){tag}", "", "No warning evaluation is given for these results.", ""]
        lines += [f"- **{table.column_label(d.result)}**: " + _skipped_line(" ".join(f.text[:1].upper() + f.text[1:] for f in d.findings)) for d in skipped] + [""]
    return "\n".join(lines).rstrip() + "\n"


def build_summary(validations: list[Validation]) -> str:
    items = [(v, decide(v, r)) for v in validations for r, t in v.table.responses.items() if t.usable]
    lines = ["# Stage 3b applicability-domain warnings summary", "", SAFEGUARD, "",
             "Every table is labelled with its data status: the mock tables are SYNTHETIC (they say nothing about real tablets) and the public table is REAL PUBLIC DATA, NOT CLIENT DATA. "
             "Three statuses are kept apart below: carried, carried but exploratory (borderline), and not assessed.", ""] + [f"- {e}" for e in EXPLAIN] + [""]
    references: dict = {}
    for status, title in ((CARRIED, "Part A: carried results"), (BORDERLINE, "Part B: carried but exploratory (borderline) results")):
        lines += [f"## {title}", ""]
        group = [(v, d) for v, d in items if d.status == status]
        if not group:
            lines += ["- none", ""]
        for v, d in group:
            label = v.table.label.short if v.table.label else "DATA STATUS NOT STATED"
            suffix = f" [{d.tag}]" if d.tag else ""
            lines += [f"### {v.table.name} [{label}]: {v.table.column_label(d.result)}{suffix}", ""]
            if d.status == BORDERLINE:
                lines += [f"**{d.tag}.**", ""]
            lines += _tables(v, d.result, d.chosen, references)
    lines += ["## Part C: not assessed (skipped): no warning evaluation is given", ""]
    lines += [f"- **{v.table.name}, {v.table.column_label(d.result)}** [{v.table.label.short if v.table.label else 'DATA STATUS NOT STATED'}]"
              f"{' [' + v.table.tag + ']' if v.table.tag else ''}: " + _skipped_line(" ".join(f.text[:1].upper() + f.text[1:] for f in d.findings)) for v, d in items if d.status == SKIPPED] + [""]
    return "\n".join(lines).rstrip() + "\n"
