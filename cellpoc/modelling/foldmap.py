"""The fold map: a plain document that shows, for one table, exactly how it is divided into training and test rows, so the splits can be read without reading code.

It opens with the data-status label, says that no random rows are ever used, and then lists every hold-out type: how it works, and every fold with
what is held out and how many rows are trained on and tested. Whatever was skipped is listed with its reason. A stand-in for the supplier is named
with the proxy wording (PROXY_PHRASE, written once in findings.py) on every line that names it. It contains no clock time, so the same table always gives the same map.
"""
from __future__ import annotations

from .findings import MIN_ROWS, MIN_TEST
from .splits import FoldPlan, make_fold_plans
from .table import ModellingTable

LEVEL_WORD = {"error": "ERROR", "warning": "WARNING", "note": "note"}
SHOWN = 5


def _held(names: tuple[str, ...]) -> str:
    return ", ".join(names[:SHOWN]) + (f" and {len(names) - SHOWN} more" if len(names) > SHOWN else "")


def _signature(plan: FoldPlan) -> list:
    return [(f.held_out, len(f.train), len(f.test)) for f in plan.folds]


def build_fold_map(table: ModellingTable) -> str:
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    tag = f" [{table.tag}]" if table.tag else ""
    lines = [f"# Fold map [{label}]{tag}: {table.name}", "",
             f"**This map is {label}.** It says how the table is divided into training and test rows. It says nothing about how well any model does.", "",
             *([f"**{table.tag}.**", ""] if table.tag else []),
             "**No random rows are ever used.** A model is tested only on whole groups it has never seen: whole batches (or APIs) held out together, whole suppliers "
             "held out, and later dates held out. A hold-out that cannot be run is skipped, with the reason, and is never replaced by random rows.", "",
             f"Every fold must have at least {MIN_TEST} test rows and {MIN_ROWS} training rows. Rows with a missing result or input are left out for that result "
             "(see the modelling table's messages); they are not filled in.", ""]
    if not table.ok:
        return "\n".join(lines + ["No fold map: the table could not be prepared for modelling.", ""])
    usable = [r for r, t in table.responses.items() if t.usable]
    plans = {r: make_fold_plans(table, r) for r in usable}
    for r in table.responses:
        if r not in usable:
            lines += [f"- `{table.column_label(r)}` is not modelled (too few rows or no variation): no folds.", ""]
    if not usable:
        return "\n".join(lines) + "\n"
    kinds = list(plans[usable[0]])
    for kind in kinds:
        first = plans[usable[0]][kind]
        lines += [f"## Hold-out: {first.heading}{tag}", ""]
        spec = table.groups.get(kind)
        if spec and spec.note:
            lines += [f"{first.heading}: {spec.note}.", ""]
        if first.method:
            lines += [f"**How it works:** {first.method}.", ""]
        same = all(_signature(plans[r][kind]) == _signature(first) for r in usable)
        if same:
            shown = [(", ".join(table.column_label(r) for r in usable), first)]
        else:
            shown = [(table.column_label(r), plans[r][kind]) for r in usable]
        for names, plan in shown:
            if not plan.available:
                lines += [f"**Not run for {names}**: " + "; ".join(f.text for f in plan.findings if f.level == "warning"), ""]
                continue
            lines += [f"Results: {names}" + (" (the same folds for all of them)" if same and len(usable) > 1 else ""), "",
                      "| Fold | Held out | Training rows | Test rows |", "|---|---|---|---|"]
            lines += [f"| {f.number} | {_held(f.held_out)} | {len(f.train):,} | {len(f.test):,} |" for f in plan.folds]
            lines.append("")
        # the "how it works" note is already shown above; everything else the splitter said is listed once
        extra = sorted({(f.rule, f.variant, f.text) for r in usable for f in plans[r][kind].findings if f.rule not in ("M33", "M34")})
        if extra:
            lines += ["What was skipped or left out, and why:", ""] + [f"- {text}" for _, _, text in extra] + [""]
    lines += [f"## Left out of the modelling on purpose{tag}", ""]
    lines += [f"- `{c}`: {why}. A limitation for a formulation expert to review." for c, why in table.left_out] or ["- nothing"]
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
