"""The brief in plain words, for a person to read (the engine reads the JSON, not this)."""
from __future__ import annotations

from ..contracts import STATUS_CARRIED, STATUS_EXPLORATORY, EngineBrief

WORDS = {STATUS_CARRIED: "CARRIED: the engine may use it to rank recipes", STATUS_EXPLORATORY: "CARRIED BUT EXPLORATORY: the engine gets no model for it and makes no decision from it",
         "not_assessed": "NOT ASSESSED: no model, no probability; it is only ever measured"}


def render(brief: EngineBrief) -> str:
    tag = f" [{brief.table_tag}]" if brief.table_tag else ""
    lines = [f"# What the decision engine is told about {brief.table} [{brief.data_label}]{tag}", "",
             f"**This brief is {brief.data_label}.** It holds only what Stage 3 concluded about each result: no measurements, nothing from any lab, nothing about real tablets or a client.", ""]
    if brief.table_tag:
        lines += [f"**{brief.table_tag}.**", ""]
    usable = brief.usable()
    lines += [f"The engine may use **{len(usable)}** of {len(brief.targets)} results to rank recipes" + (": " + ", ".join(t.label for t in usable) + "." if usable else "."), ""]
    for t in brief.targets:
        lines += [f"## {t.label} [{brief.data_label}]{tag}", "", f"**{WORDS[t.status]}.**", ""]
        if t.reason:
            lines += [f"- {t.reason}"]
        if t.model_label:
            lines += [f"- Model the Stage 3 rule chose: {t.model_label}.",
                      f"- Is its stated 90% range honest? As stated: {t.calibration_verdict}; after recalibration: {t.calibration_verdict_after or 'could not be recalibrated'}."]
            lines += [f"- Range widening factor: {t.range_factor:.2f}, {t.range_factor_basis}." if t.range_factor is not None else f"- Range widening factor: none; {t.range_factor_basis}."]
        if t.calculated_from:
            lines += [f"- Calculated from other columns ({', '.join(t.calculated_from)}), so it is one finding with them and not an independent one."]
        lines += [""]
    lines += ["## What this does not say", ""] + [f"- {c}" for c in brief.caveats]
    return "\n".join(lines) + "\n"
