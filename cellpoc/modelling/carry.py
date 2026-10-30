"""Which results are strong enough to be calibrated, warned about and replayed (Stage 3b), by a rule fixed before any calibration number existed.

A result is CARRIED when it is in a main comparison, its chosen model beats both baselines in every hold-out type that can be run, and its worst hold-out error is at most
CARRY_LINE of the result's spread. It is CARRIED BUT EXPLORATORY (borderline) when that error is above CARRY_LINE and at most SKIP_LINE. Anything else is SKIPPED: an exploratory or
robustness-only table, a result no model beats the baseline on, a result predicted too weakly to matter, or a table with too few held-out rows. A skipped result is never given
a calibration number: it is listed as "not assessed" with its reason. For a carried result the rule's choice and every model within its 5% tie are carried (they are interchangeable
choices), so calibration can say which of them states honest uncertainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .findings import Finding, make
from .selection import select
from .validate import Validation, score, spread

CARRY_LINE = 0.70
SKIP_LINE = 0.80
MIN_HELD_OUT_ROWS = 500

CARRIED, BORDERLINE, SKIPPED = "carried", "borderline", "skipped"
STATUS_WORDS = {CARRIED: "CARRIED", BORDERLINE: "CARRIED BUT EXPLORATORY (borderline)", SKIPPED: "NOT ASSESSED (skipped)"}


@dataclass
class CarryDecision:
    table: str
    result: str
    status: str
    chosen: str | None = None
    models: list[str] = field(default_factory=list)       # the rule's choice first, then the models within its 5% tie
    worst: float | None = None                              # the chosen model's worst hold-out error divided by the result's spread
    findings: list[Finding] = field(default_factory=list)

    @property
    def tag(self) -> str:
        """What every heading about a borderline result carries (nothing for a carried one)."""
        if self.status != BORDERLINE:
            return ""
        return f"EXPLORATORY: borderline result (worst error {self.worst:.2f} of the spread, between the {CARRY_LINE:.2f} carry line and the {SKIP_LINE:.2f} skip line)"


def decide(validation: Validation, result: str) -> CarryDecision:
    table = validation.table
    name = table.name
    out = CarryDecision(name, result, SKIPPED)
    if table.tag:
        why = "it is an exploratory comparison that is never part of the main findings" if table.exploratory else "it is a robustness-only table that cannot support a claim about learning accuracy"
        out.findings.append(make("M50", "tag", name, result, why=why))
        return out
    sel = select(validation, result)
    if sel.chosen is None:
        out.findings.append(make("M50", "no_model", name, result))
        return out
    kinds = sel.kinds
    scores = {k: score(validation.runs[(result, k)]) for k in kinds}
    rows = max(scores[k]["mean"].n for k in kinds)                  # the table's size: the most rows any hold-out type scores (a forward-in-time hold-out tests only the later dates)
    sd = spread(table, result)
    out.chosen, out.worst = sel.chosen, min(sel.worst[k] for k in sel.eligible)      # the line is judged on the BEST eligible model, not on a slightly weaker one the tie rule prefers
    if rows < MIN_HELD_OUT_ROWS:
        out.findings.append(make("M50", "small", name, result, n=rows, minimum=MIN_HELD_OUT_ROWS))
        return out
    if out.worst > SKIP_LINE:
        out.findings.append(make("M50", "weak", name, result, worst=f"{out.worst:.2f}", share=f"{max(0.0, 100 * (1 - out.worst ** 2)):.0f}"))
        return out
    out.models = list(sel.tie)
    if out.worst > CARRY_LINE:
        out.status = BORDERLINE
        out.findings.append(make("M51", "", name, result, worst=f"{out.worst:.2f}", carry=f"{CARRY_LINE:.2f}", skip=f"{SKIP_LINE:.2f}"))
    else:
        out.status = CARRIED
    return out


def decide_all(validations: list[Validation]) -> list[CarryDecision]:
    return [decide(v, r) for v in validations for r, t in v.table.responses.items() if t.usable]
