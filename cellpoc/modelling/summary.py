"""The summary report: every table's comparison in one plain document, in three clearly separate parts.

Part A, the main comparisons (the only ones a model is chosen from). Part B, exploratory comparisons (never part of the main comparison or the scorecard).
Part C, robustness-only tables (they cannot support a claim about learning accuracy). Every heading in B and C carries that table's label. Each table shows, for every
result, every model's error divided by the result's spread for each hold-out type, its worst, its lowest 90% range hit rate, and whether it beats both baselines
everywhere; the per-table reports hold the detail. It has no clock time, so the same run always gives the same summary.
"""
from __future__ import annotations

import numpy as np

from .models import FIT_WORDS, MODELS_BY_KEY as MODELS, ORDER
from .selection import CANDIDATES, LEAKAGE_R2, select
from .validate import Validation, score, spread


def _num(x: float, digits: int = 3) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{digits}f}"


def _result_table(validation: Validation, result: str, chosen: str | None) -> list[str]:
    table = validation.table
    kinds = [k for (r, k), run in validation.runs.items() if r == result and run.plan.available]
    if not kinds:
        return [f"**{table.column_label(result)}**: no hold-out type could be run.", ""]
    sd = spread(table, result)
    by_kind = {k: score(validation.runs[(result, k)]) for k in kinds}
    heads = [validation.runs[(result, k)].plan.heading for k in kinds]
    lines = [f"**{table.column_label(result)}** (error ÷ the result's spread of {_num(sd, 4)}; lower is better; 1.0 is no better than guessing the training mean)", "",
             "| Model | Fitted | " + " | ".join(heads) + " | Worst | Lowest 90% range hit rate | Beats both baselines everywhere | |", "|---|---|" + "---|" * (len(kinds) + 4)]
    for key in ORDER:
        if not all(key in by_kind[k] for k in kinds):
            continue
        errors = [by_kind[k][key].rmse / sd for k in kinds]
        covers = [by_kind[k][key].coverage for k in kinds if np.isfinite(by_kind[k][key].coverage)]
        beats = "n/a (baseline)" if key in ("mean", "nearest") else ("yes" if all(by_kind[k][key].rmse < min(by_kind[k][b].rmse for b in ("mean", "nearest")) for k in kinds) else "no")
        flag = "CHOSEN" if key == chosen else ("CHECK FOR LEAKAGE" if any(np.isfinite(by_kind[k][key].r2) and by_kind[k][key].r2 > LEAKAGE_R2 for k in kinds) else "")
        lines.append(f"| {MODELS[key].label} | {FIT_WORDS[MODELS[key].joint]} | " + " | ".join(_num(e) for e in errors) + f" | {_num(max(errors))} | {_num(min(covers), 2) if covers else 'n/a'} | {beats} | {flag} |")
    return lines + [""]


def _table_section(validation: Validation, level: str, judged: bool) -> list[str]:
    table = validation.table
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    tag = f" [{table.tag}]" if table.tag else ""
    lines = [f"{level} {table.name} [{label}]{tag}", ""]
    if table.tag:
        lines += [f"**{table.tag}.** No model is chosen from this table.", ""]
    for result in table.responses:
        if not table.responses[result].usable:
            lines += [f"**{table.column_label(result)}**: not modelled (too few rows or no variation).", ""]
            continue
        chosen = select(validation, result) if judged else None
        lines += _result_table(validation, result, chosen.chosen if chosen else None)
        if chosen:
            lines += [f"Rule: {chosen.why[:1].upper() + chosen.why[1:]}" + (f" Chosen: {MODELS[chosen.chosen].label}." if chosen.chosen else ""), ""]
    return lines


def build_summary(validations: list[Validation], mode: str) -> str:
    main = [v for v in validations if not v.table.tag]
    exploratory = [v for v in validations if v.table.exploratory]
    robustness = [v for v in validations if v.table.tag and not v.table.exploratory]
    word = "FULL RUN" if mode == "full" else "FAST MODE"
    lines = [f"# Stage 3a model comparison summary, {word}", "",
             "Every table below is labelled with its data status: the mock tables are SYNTHETIC (made by a program: they say nothing about real tablets) and the two public tables are "
             "REAL PUBLIC DATA, NOT CLIENT DATA. Nothing here is a claim about real tablets, any client, or any table not listed. No model was tuned to any table: every setting was "
             "fixed in advance (the ridge penalty is chosen inside each training fold, never on the held-out fold).", ""]
    if mode != "full":
        lines += ["This is a fast-mode run (less work per model): the numbers are a first look, not final.", ""]
    lines += ["**How the models are fitted across results (a stated limitation):** only the joint Gaussian process is fitted jointly across results (one shared set of length scales, trained "
              "on the rows that have every result). Every other model, the ordinary Gaussian process included, is fitted independently, one model per result, so it cannot use what one "
              "result tells about another. The 'Fitted' column says which for every row.", "",
              "**How to read the tables:** every model is tested only on whole groups it never saw (never random rows). Each hold-out type is a column. A model's score is its WORST hold-out "
              "type; to be chosen it must beat both naive baselines (the training mean and the nearest-neighbour lookup) in every hold-out type, and ties within 5% go to the simpler or faster "
              "model. The 90% range hit rate should be about 0.90; Stage 3a only reports it (Stage 3b judges and recalibrates).", ""]
    lines += ["## Part A: the main comparisons (the only ones a model is chosen from)", ""]
    for v in main:
        lines += _table_section(v, "###", True)
    if exploratory:
        lines += ["## Part B: exploratory comparisons (never part of the main comparison or the scorecard)", ""]
        for v in exploratory:
            lines += [f"The headings in this part carry the label: {v.table.tag}.", ""] + _table_section(v, "###", False)
    if robustness:
        lines += ["## Part C: robustness-only tables (they cannot support a claim about learning accuracy)", ""]
        for v in robustness:
            lines += _table_section(v, "###", False)
    lines += ["## Results that are not independent findings", ""]
    notes = []
    for v in validations:
        t = v.table
        notes += [f"- {t.name}: `{t.column_label(k)}` is calculated from `{'`, `'.join(t.column_label(x) for x in s)}`, so their results move together and must not be presented as separate findings."
                  for k, s in ((k, [x for x in src if x in t.responses]) for k, src in t.derived_from.items() if k in t.responses) if s]
        notes += [f"- {t.name}: `{c}`: {why}." for c, why in t.left_out if "independent" in why]
    lines += sorted(set(notes)) or ["- none"]
    lines += ["", "## What was left out of the modelling, and what was assumed", ""]
    for v in validations:
        t = v.table
        lines += [f"- {t.name}: left out `{c}`: {why}." for c, why in t.left_out] + [f"- {t.name}: the unit of `{c}` is assumed, not confirmed ({why})." for c, why in t.unit_assumed.items()]
        if t.flag_columns:
            lines.append(f"- {t.name}: rows flagged by `{', '.join(t.flag_columns)}` (listed amounts do not add up to the tablet weight) are kept in the scores; the per-table report shows scores with and without them.")
    lines += ["", "## What this does not show", "",
              "- How any model does on real tablets, on client data, or on a table not listed here. The mock tables are synthetic; the public tables are real but not the client's.",
              "- Whether a score is good enough to act on: that is for Stage 3b (calibration, the applicability-domain warning and the scorecard) and, later, a formulation expert.",
              "- Anything about suppliers where the supplier hold-out is a stand-in: for the batch data the split is on a column the file does not explain, and it is marked "
              "as a proxy wherever it appears."]
    return "\n".join(lines).rstrip() + "\n"
