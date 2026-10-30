"""Turning Stage 3's saved answers into the decision engine's brief (Stage 4-1).

Nothing here is decided: every status, model and calibration verdict comes from the Stage 3 rules exactly as they were fixed (the carry rule of 3b-1, the selection rule of 3a, the calibration of 3b-1).
The one number this adds is the range factor, fixed in docs/decisions.md before it was built: the MEDIAN of the later-dates recalibration factors (each learned from EARLIER steps only, as 3b-1 guards),
never below 1, so the engine never trusts a range narrower than the model stated and no single swinging fold decides it. It refits nothing and sees no lab.
"""
from __future__ import annotations

from statistics import median

from ..contracts import BRIEF_VERSION, STATUS_CARRIED, STATUS_EXPLORATORY, STATUS_NOT_ASSESSED, EngineBrief, TargetBrief
from ..modelling.calibration import calibrate
from ..modelling.carry import BORDERLINE, CARRIED, CarryDecision
from ..modelling.findings import UNIFYING_STATEMENT
from ..modelling.models import MODELS_BY_KEY as MODELS
from ..modelling.validate import Validation

CAVEATS = (
    UNIFYING_STATEMENT,
    "Which results are carried depends on the table they were judged on. A different table, or a client's own data, needs the Stage 3 rule run again before the engine may use anything.",
    "The calibration and the warnings behind these statuses were measured on whole batches, whole suppliers and later dates of the table named here. They say nothing about real tablets or a client.",
)
STATUS_OF = {CARRIED: STATUS_CARRIED, BORDERLINE: STATUS_EXPLORATORY}


def range_factor(factors: list[float | None]) -> float | None:
    """The median of the later-dates scale factors that could be learned, never below 1. None when there are none."""
    usable = [f for f in factors if f is not None]
    return max(1.0, float(median(usable))) if usable else None


def _basis(factors: list[float | None]) -> str:
    usable = [f for f in factors if f is not None]
    if not usable:
        return "no later-dates factor could be learned for this result, so the stated range is used as it is"
    return f"the median of {len(usable)} later-dates scale factor(s), each learned from earlier steps only, and never below 1 (so the range is never narrower than the model stated)"


def build_brief(validation: Validation, decisions: list[CarryDecision]) -> EngineBrief:
    table = validation.table
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    targets = []
    for d in (d for d in decisions if d.table == table.name):
        name = table.column_label(d.result)
        calculated = tuple(table.derived_from.get(d.result, ()))
        if d.status not in STATUS_OF:
            targets.append(TargetBrief(d.result, name, STATUS_NOT_ASSESSED, reason=" ".join(f.text[:1].upper() + f.text[1:] for f in d.findings), calculated_from=calculated))
            continue
        cal = calibrate(validation, d.result, d.chosen, "chosen")
        factors = list(cal.kinds["date"].factors) if "date" in cal.kinds else []
        rt = table.responses[d.result]
        targets.append(TargetBrief(d.result, name, STATUS_OF[d.status], d.chosen, MODELS[d.chosen].label, cal.verdict, cal.verdict_after, range_factor(factors), _basis(factors),
                                   d.tag if d.status == BORDERLINE else "", calculated, tuple(rt.numeric), tuple(rt.categorical)))
    return EngineBrief(BRIEF_VERSION, table.name, label, table.tag or "", tuple(targets), CAVEATS)
