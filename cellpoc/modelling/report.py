"""The model comparison report: a plain document, one per table, that shows how every model did on whole groups it never saw.

It opens with the data-status label (and, for an exploratory or robustness-only table, that label too, in every heading). Every table lists the two naive
baselines beside every candidate, says for each model whether it was fitted jointly across results or independently per result, and gives how often the 90%
range contained the truth. It says what a fast-mode run is, what was left out, what was assumed, and what the comparison cannot show. It has no clock time:
the same run always gives the same report.
"""
from __future__ import annotations

import numpy as np

from .findings import MIN_ROWS, MIN_TEST
from .models import FIT_WORDS, MODELS_BY_KEY as MODELS, ORDER
from .selection import LEAKAGE_R2, select
from .validate import Validation, build_with_flags_removed, score, spread
RANGE_GAP = 0.05          # a 90% range that contains the truth less than 85% or more than 95% of the time is marked in the report (judging it is Stage 3b)
LIMITS = {"fast": "In fast mode the Gaussian process searches its settings on {gp} rows, the forests have {rf} trees, the boosted trees {gbt} steps and the network ensembles "
                  "{mlp} members; the full run uses more. Fast-mode numbers are a first look: the full run replaces them."}


def _num(x: float, digits: int = 3) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{digits}f}"


def _table_for(validation: Validation, result: str, kind: str, sd: float) -> list[str]:
    table = validation.table
    scores = score(validation.runs[(result, kind)])
    base = scores.get("mean")
    lines = [f"**Result: {table.column_label(result)}** (spread, as a standard deviation: {_num(sd, 4)}; {scores['mean'].n:,} held-out rows scored)" if "mean" in scores else f"**Result: {table.column_label(result)}**", "",
             "| Model | Fitted | Error | Error ÷ spread | Error ÷ the mean baseline's | R² | Worst fold (error ÷ spread) | 90% range hit rate | Range width ÷ spread | Folds | Seconds | Notes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in ORDER:
        if key not in scores:
            continue
        s, m = scores[key], MODELS[key]
        notes = []
        if np.isfinite(s.r2) and s.r2 > LEAKAGE_R2:
            notes.append("CHECK FOR LEAKAGE")
        if not np.isfinite(s.coverage):
            notes.append("no 90% range")
        elif abs(s.coverage - 0.9) > RANGE_GAP:
            notes.append("range hit rate far from 90%")
        if s.folds < s.of_folds:
            notes.append(f"result on {s.folds} of {s.of_folds} folds only")
        lines.append(f"| {m.label} | {FIT_WORDS[m.joint]} | {_num(s.rmse, 4)} | {_num(s.rmse / sd)} | {_num(s.rmse / base.rmse) if base else 'n/a'} | {_num(s.r2)} | "
                     f"{_num(s.worst_fold_rmse / sd)} | {_num(s.coverage, 2)} | {_num(s.width / sd) if np.isfinite(s.width) else 'n/a'} | {s.folds} of {s.of_folds} | {s.seconds:.1f} | {'; '.join(notes)} |")
    return lines + [""]


def _flag_section(validation: Validation, alt: Validation) -> list[str]:
    table = validation.table
    flags = ", ".join(table.flag_columns)
    tag = f" [{table.tag}]" if table.tag else ""
    lines = [f"## Scores with and without the flagged rows{tag}", "",
             f"Some rows are flagged ({flags}): their listed amounts do not add up to the tablet weight within the tolerance. They are kept in the main scores above. Here every model "
             "is fitted and scored again with those rows left out of both training and testing, so you can see whether they matter. Error ÷ spread; lower is better.", ""]
    for (result, kind), run in validation.runs.items():
        if (result, kind) not in alt.runs or not run.plan.available:
            continue
        a, b = score(run), score(alt.runs[(result, kind)])
        sd, sd_alt = spread(table, result), spread(alt.table, result)
        lines += [f"**{table.column_label(result)}, {run.plan.heading}{(' [' + table.tag + ']') if table.tag else ''}**", "", "| Model | With the flagged rows | Without them |", "|---|---|---|"]
        lines += [f"| {MODELS[k].label} | {_num(a[k].rmse / sd)} | {_num(b[k].rmse / sd_alt) if k in b else 'n/a'} |" for k in ORDER if k in a]
        lines.append("")
    return lines


def build_report(validation: Validation, alt: Validation | None = None) -> str:
    table, settings = validation.table, validation.settings
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    tag = f" [{table.tag}]" if table.tag else ""
    mode = "FAST MODE" if settings.mode == "fast" else "FULL RUN"
    lines = [f"# Model comparison, {mode} [{label}]{tag}: {table.name}", "",
             f"**This report is {label}.** It says how well each model predicts results for whole groups it never saw, on this table only. It is not a prediction about real tablets or a client.", ""]
    if table.tag:
        lines += [f"**{table.tag}.**", ""]
    if settings.mode == "fast":
        lines += [LIMITS["fast"].format(gp=settings.gp_search_rows, rf=settings.rf_trees, gbt=settings.gbt_iterations, mlp=settings.mlp_members), ""]
    lines += [f"## How the models are fitted across results (a stated limitation){tag}", "",
              "Each result is predicted by its own model, **except one**: the joint Gaussian process is fitted **jointly across results** (one shared set of length scales for all results, "
              "trained only on rows that have every result). **Every other model, including the ordinary Gaussian process, is fitted independently, one model per result,** so it cannot "
              "use what one result tells about another. The 'Fitted' column of every table says which.", "",
              "| Model | Fitted | How its 90% range is made |", "|---|---|---|"]
    lines += [f"| {m.label} | {FIT_WORDS[m.joint]} | {m.interval} |" for k, m in MODELS.items()]
    lines += ["", "Every candidate is shown beside the two naive baselines in the same table (the training mean, and a lookup of the nearest training row). "
              "A model that does not beat them is not useful. All models are fitted on the training rows of each fold only: scaling and the coding of categories are learned there too.", "",
              "**The 90% range hit rate** is how often the range contained the true value on held-out groups: about 0.90 is right. It is measured for every model's range separately from the "
              "conformal method, which is just one candidate. Stage 3a reports it and marks gaps over 5 points; judging it and recalibrating belong to Stage 3b.", ""]
    for kind in sorted({k for (_, k) in validation.runs}, key=lambda k: ["batch", "supplier", "date", "api"].index(k)):
        runs = {r: run for (r, k), run in validation.runs.items() if k == kind}
        first = next(iter(runs.values())).plan
        lines += [f"## Hold-out: {first.heading}{tag}", ""]
        spec = table.groups.get(kind)
        if spec and spec.note:
            lines += [f"{first.heading}: {spec.note}.", ""]
        if first.method:
            lines += [f"How the folds are made: {first.method}.", ""]
        for result, run in runs.items():
            if not run.plan.available:
                lines += [f"**{table.column_label(result)}**: not run: " + "; ".join(f.text for f in run.plan.findings if f.level == "warning"), ""]
                continue
            lines += _table_for(validation, result, kind, spread(table, result))
    lines += [f"## Which model would be chosen{tag}", ""]
    if table.tag:
        lines += [f"No model is chosen from this comparison. It is labelled above ({table.tag}). The tables above are shown for information only and are never part of the main comparison or the scorecard.", ""]
    else:
        lines += ["By the rule fixed in advance: a model's score is its worst hold-out type (error ÷ spread); it must beat both baselines in every hold-out type that can be run; "
                  "ties within 5% go to the simpler or faster model. These are fast-mode numbers, so this is a first look, not the final choice.", ""]
        for result in table.responses:
            s = select(validation, result)
            if not table.responses[result].usable:
                continue
            chosen = MODELS[s.chosen].label if s.chosen else "none"
            lines += [f"- **{table.column_label(result)}**: {chosen}. {s.why[:1].upper() + s.why[1:]} Hold-outs judged: {', '.join(table.groups[k].heading if k in table.groups else k for k in s.kinds) or 'none'}."]
        lines.append("")
    if alt is not None:
        lines += _flag_section(validation, alt)
    linked = [(k, [s for s in sources if s in table.responses]) for k, sources in table.derived_from.items() if k in table.responses]
    linked = [(k, s) for k, s in linked if s]
    if linked:
        lines += [f"## Results that are not independent findings{tag}", ""]
        lines += [f"- `{table.column_label(k)}` is calculated from `{"`, `".join(table.column_label(x) for x in s)}`, so their results move together and must not be presented as separate findings." for k, s in linked] + [""]
    lines += [f"## Limitations and what this does not show{tag}", "",
              "- This is a test of how well each model predicts held-out groups on THIS table. It says nothing about real tablets, any client, or any other table.",
              "- Joint versus independent fitting is described above: only the joint Gaussian process shares anything across results.",
              f"- A fold needs at least {MIN_TEST} test rows and {MIN_ROWS} training rows; smaller folds are dropped and a hold-out that cannot be run is skipped, never replaced by random rows.",
              "- No model was tuned to any table; every setting was fixed in advance."]
    for column, why in table.left_out:
        lines.append(f"- Left out of the modelling on purpose: `{column}`: {why}. A limitation for a formulation expert to review.")
    for column, why in table.unit_assumed.items():
        lines.append(f"- The unit of `{column}` is assumed, not confirmed ({why}).")
    extra = sorted({f"{f.place}: {f.text}" if f.place else f.text for f in validation.findings})
    if extra:
        lines += ["", f"## What was skipped, left out, limited or flagged, and why{tag}", ""] + [f"- {text}" for text in extra[:60]] + ([f"- ... and {len(extra) - 60} more."] if len(extra) > 60 else [])
    return "\n".join(lines).rstrip() + "\n"


def flagged_pair(validation: Validation):
    """The same table without its flagged rows, ready to run again (None when nothing is flagged)."""
    return build_with_flags_removed(validation.table)
