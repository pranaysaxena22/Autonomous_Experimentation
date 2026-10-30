"""The calibration reports: one plain document per table, and one summary across tables.

Three statuses are kept apart, in separate sections with their own wording: CARRIED results (calibrated), CARRIED BUT EXPLORATORY borderline results (calibrated for
information only, with their label in every heading) and NOT ASSESSED results (listed with the reason, never given a calibration number). Every heading carries the table's
data-status label and any exploratory or robustness label; the supplier stand-in always carries the proxy wording (PROXY_PHRASE, written once in findings.py) through the hold-out headings. No clock time.
"""
from __future__ import annotations

import numpy as np

from .calibration import HONEST_BAND, ModelCalibration, calibrate
from .carry import BORDERLINE, CARRIED, CARRY_LINE, SKIP_LINE, SKIPPED, STATUS_WORDS, CarryDecision, decide
from .models import MODELS_BY_KEY as MODELS
from .validate import Validation

EXPLAIN = [
    "Every model states a 90% range. On the held-out groups of the Stage 3a comparison we count how often the range really contained the truth. **About 0.90 is honest.** "
    f"Below {HONEST_BAND[0]:.2f} the model is over-confident (its ranges are too narrow to trust); above {HONEST_BAND[1]:.2f} it is under-confident (wider than needed). The verdict is fixed "
    "in advance: a model is honest only if the hit rate is inside that band in every hold-out type.",
    "**Recalibration** is a scale factor for the range, learned only from the held-out errors of the OTHER folds and applied to the current fold (for hold-outs forward in time, only "
    "EARLIER steps), so a fold's own answers never enter its factor. The hit rate is then measured again on that fold. Nothing is refitted: this works from the saved predictions.",
    "**Error bars** come from resampling whole held-out groups (rows inside a group are not independent); with fewer than 10 groups no error bar is given.",
    "**Knows when it is unsure** is the rank correlation between a row's stated range and its actual error: near 1 means wider ranges really go with bigger errors. A model that states "
    "the same range for every recipe cannot tell you when to worry.",
]


ROLE_WORDS = {"chosen": "the rule's choice", "tie": "within 5% of the choice"}


def _cell(k, after: bool = True) -> str:
    ci = f" [{k.ci[0]:.2f} to {k.ci[1]:.2f}]" if k.ci else f" [no error bar: {k.n_groups} groups]"
    recal = f" then {k.recal_hit:.2f} after recalibration" if after and k.recal_hit is not None else (" (could not be recalibrated)" if after else "")
    return f"{k.hit:.2f}{ci}{recal}"


def _unsure(m: ModelCalibration) -> str:
    values = [k.spearman for k in m.kinds.values() if k.spearman is not None]
    return "no: the same range for every recipe" if not values else f"{min(values):.2f} to {max(values):.2f}"


def _model_table(table, cals: list[ModelCalibration], validation: Validation) -> list[str]:
    kinds = list(cals[0].kinds)
    heads = [cals[0].kinds[k].heading for k in kinds]
    lines = ["| Model | Role | " + " | ".join(f"90% hit rate: {h}" for h in heads) + " | Verdict | After recalibration | Range width ÷ spread | Knows when it is unsure |",
             "|---|---|" + "---|" * (len(kinds) + 4)]
    for m in cals:
        after = m.verdict_after
        lines.append(f"| {MODELS[m.model].label} | {ROLE_WORDS[m.role]} | "
                     + " | ".join(_cell(m.kinds[k]) if k in m.kinds else "n/a" for k in kinds)
                     + f" | **{m.verdict}** | {after if after else 'n/a'} | "
                     + f"{np.mean([k.width for k in m.kinds.values()]):.2f} | {_unsure(m)} |")
    return lines + [""]


def build_report(validation: Validation, decisions: list[CarryDecision] | None = None) -> str:
    table = validation.table
    decisions = decisions or [decide(validation, r) for r, t in table.responses.items() if t.usable]
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    tag = f" [{table.tag}]" if table.tag else ""
    lines = [f"# Calibration [{label}]{tag}: {table.name}", "",
             f"**This report is {label}.** It tests whether the stated 90% ranges are honest on this table only. It is not a prediction about real tablets or a client.", ""]
    if table.tag:
        lines += [f"**{table.tag}.**", ""]
    lines += [f"## How to read this{tag}", ""] + [f"- {e}" for e in EXPLAIN] + [""]
    for status, title in ((CARRIED, "Carried results"), (BORDERLINE, "Carried but exploratory results (borderline)")):
        group = [d for d in decisions if d.status == status]
        if not group:
            continue
        note = (f"These results beat both baselines and their worst hold-out error is at most {CARRY_LINE:.2f} of the result's spread." if status == CARRIED else
                f"These results beat both baselines but their worst hold-out error is between {CARRY_LINE:.2f} and {SKIP_LINE:.2f} of the result's spread. They are shown for information and are never part of the main findings.")
        lines += [f"## {title}{tag}", "", note, ""]
        for d in group:
            suffix = f" [{d.tag}]" if d.tag else ""
            lines += [f"### {table.column_label(d.result)}: {STATUS_WORDS[d.status]}{suffix}{tag}", ""]
            if d.status == BORDERLINE:
                lines += [f"**{d.tag}.**", ""]
            if d.result in table.derived_from:
                lines += [f"`{table.column_label(d.result)}` is calculated from other columns, so its results move together with theirs and are not an independent finding.", ""]
            cals = [calibrate(validation, d.result, m, "chosen" if m == d.chosen else "tie") for m in d.models]
            lines += _model_table(table, cals, validation)
            lines += [f"- {f.place}: {f.text}" for m in cals for f in m.findings] + ([""] if any(m.findings for m in cals) else [])
    skipped = [d for d in decisions if d.status == SKIPPED]
    if skipped:
        lines += [f"## Not assessed (skipped){tag}", "", "No calibration number is given for these results.", ""]
        lines += [f"- **{table.column_label(d.result)}**: " + " ".join(f.text[:1].upper() + f.text[1:] for f in d.findings) for d in skipped] + [""]
    lines += [f"## What this does not show{tag}", "",
              "- Whether a model is good enough to act on: only whether the uncertainty it states is honest. That is for the scorecard and, later, a formulation expert.",
              "- Anything about real tablets or a client; this table is labelled above.",
              "- Calibration for results that do not predict well enough: they are listed as not assessed."]
    return "\n".join(lines).rstrip() + "\n"


def build_summary(validations: list[Validation]) -> str:
    items = [(v, decide(v, r)) for v in validations for r, t in v.table.responses.items() if t.usable]
    lines = ["# Stage 3b calibration summary", "",
             "Every table is labelled with its data status: the mock tables are SYNTHETIC (they say nothing about real tablets) and the public table is REAL PUBLIC DATA, NOT CLIENT DATA. "
             "Three statuses are kept apart below: carried, carried but exploratory (borderline), and not assessed.", ""] + [f"- {e}" for e in EXPLAIN] + [""]
    for status, title in ((CARRIED, "Part A: carried results"), (BORDERLINE, "Part B: carried but exploratory (borderline) results")):
        group = [(v, d) for v, d in items if d.status == status]
        lines += [f"## {title}", ""]
        if not group:
            lines += ["- none", ""]
            continue
        for v, d in group:
            label = v.table.label.short if v.table.label else "DATA STATUS NOT STATED"
            suffix = f" [{d.tag}]" if d.tag else ""
            lines += [f"### {v.table.name} [{label}]: {v.table.column_label(d.result)}{suffix}", ""]
            if d.status == BORDERLINE:
                lines += [f"**{d.tag}.**", ""]
            cals = [calibrate(v, d.result, m, "chosen" if m == d.chosen else "tie") for m in d.models]
            lines += _model_table(v.table, cals, v)
    lines += ["## Part C: not assessed (skipped): no calibration number is given", ""]
    lines += [f"- **{v.table.name}, {v.table.column_label(d.result)}** [{v.table.label.short if v.table.label else 'DATA STATUS NOT STATED'}]"
              f"{' [' + v.table.tag + ']' if v.table.tag else ''}: " + " ".join(f.text[:1].upper() + f.text[1:] for f in d.findings) for v, d in items if d.status == SKIPPED] + [""]
    return "\n".join(lines).rstrip() + "\n"
