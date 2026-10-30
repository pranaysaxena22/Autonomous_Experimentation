"""The scorecard's data (Stage 3b-4): everything one table's page shows, gathered from the saved Stage 3a answers. Nothing is refitted and nothing new is decided here.

It joins what the earlier steps worked out: which results are carried (3b-1 rule), the chosen model's error, calibration, the four separate warning statuses, the replay on the synthetic mocks, and for each
kind of shift (whole batches, whole suppliers, later dates) whether the per-recipe distance warning can be trusted. That last reading is worked out for EACH result separately and is never averaged: it is
'picks out the large errors' only when the lift is above 1 in every result, and every result's own rows warned, lift and error ratio travel with the word so it is never shown alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .calibration import calibrate
from .calibration_report import _unsure
from .carry import BORDERLINE, CARRIED, SKIPPED, CarryDecision
from .domain import evaluate_kind
from .domain_report import _basis
from .findings import NO_REPLAY_SENTENCE
from .group_domain import NOUN, evaluate_groups
from .models import MODELS_BY_KEY as MODELS
from .replay import SYNTHETIC, TableReplay, reliability_word
from .selection import select
from .validate import Validation, score, spread

KINDS = ("batch", "supplier", "date")
WORD_PICKS, WORD_MIXED, WORD_DOES_NOT, WORD_CANNOT = "picks out the large errors", "mixed", "does not", "cannot be judged"
RELIABLE_WORDS = (WORD_PICKS,)                     # the only reading that counts as reliable; the other three are all "not reliable"
MOVED_TOLERANCE = 1e-9


@dataclass
class Numbers:
    """One result's own numbers for one kind of shift: they are always shown beside the word."""
    label: str
    rows: int                        # rows warned by the distance check
    lift: float | None
    ratio: float | None              # error ratio, warned over unwarned
    range_rows: int


@dataclass
class ShiftReading:
    kind: str
    heading: str
    results: list[Numbers]
    word: str
    group_text: str = ""             # the whole-group warning for the same kind, beside it


def shift_reading(kind: str, heading: str, numbers: list[Numbers], group_text: str = "") -> ShiftReading:
    """The reading for one kind of shift: worked out from each result's own rows and lift, never from an average."""
    return ShiftReading(kind, heading, numbers, reliability_word([n.rows for n in numbers], [n.lift for n in numbers]), group_text)


@dataclass
class KindAccuracy:
    heading: str
    chosen: float                    # error divided by the result's spread (1.0 is no better than guessing the average)
    mean: float | None
    nearest: float | None


@dataclass
class KindCal:
    heading: str
    hit: float
    ci: tuple[float, float] | None
    n_groups: int
    recal_hit: float | None
    moved: str | None                # "closer to 0.90", "farther from 0.90", "unchanged" or None (could not be recalibrated)


@dataclass
class KindWarn:
    heading: str
    n: int
    distance: tuple[float, float | None, float | None]       # share warned, error ratio, lift
    range_: tuple[float, float | None, float | None]
    category_share: float
    unseen: str
    group_text: str


@dataclass
class ResultCard:
    result: str
    label: str
    status: str
    tag: str                          # the borderline label, or ""
    reason: str = ""                  # why a skipped result was not assessed
    derived_note: str = ""
    model: str = ""
    why: str = ""
    worst: float | None = None
    accuracy: list[KindAccuracy] = field(default_factory=list)
    verdict: str = ""
    verdict_after: str | None = None
    calibration: list[KindCal] = field(default_factory=list)
    unsure: str = ""
    warnings: list[KindWarn] = field(default_factory=list)
    replay_sentence: str = ""         # the fixed sentence for a carried result on real data


@dataclass
class TableCard:
    name: str
    label: str                        # the data-status label, for example SYNTHETIC DATA
    synthetic: bool
    tag: str                          # exploratory or robustness-only label of the whole table, or ""
    results: list[ResultCard]
    readings: list[ShiftReading]
    replay: TableReplay | None = None
    supplier_share: float | None = None        # how much of an input's spread the supplier explains (the mocks' fixture limit)
    real_supplier_share: float | None = None   # the same measured on the real batch data, for comparison
    notes: list[str] = field(default_factory=list)

    def by_status(self, status: str) -> list[ResultCard]:
        return [r for r in self.results if r.status == status]


def _group_text(g) -> str:
    if g is None or not g.groups:
        return ""
    flagged = sum(x.warning.flagged for x in g.groups)
    return f"{flagged} of {len(g.groups)} {NOUN[g.kind]} flagged, threshold from {_basis(g)}"


def _moved(hit: float, after: float | None) -> str | None:
    if after is None:
        return None
    a, b = abs(after - 0.90), abs(hit - 0.90)
    return "closer to 0.90" if a < b - MOVED_TOLERANCE else "farther from 0.90" if a > b + MOVED_TOLERANCE else "unchanged"


def _unseen(own) -> str:
    return "; ".join(f"{c} = {v} ({n:,} rows)" for c, v, n in own.unseen) or "none"


def build_card(validation: Validation, decisions: list[CarryDecision], replay: TableReplay | None = None, real_supplier_share: float | None = None) -> TableCard:
    table = validation.table
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    card = TableCard(table.name, label, bool(table.label and table.label.status == SYNTHETIC), table.tag or "", [], [], replay,
                     replay.movement.supplier if replay is not None else None, real_supplier_share)
    refs: dict = {}
    per_kind: dict[str, list[Numbers]] = {}
    headings: dict[str, str] = {}
    group_bits: dict[str, list] = {}
    for d in (d for d in decisions if d.table == table.name):
        name = table.column_label(d.result)
        rc = ResultCard(d.result, name, d.status, d.tag)
        if d.status == SKIPPED:
            rc.reason = " ".join(f.text[:1].upper() + f.text[1:] for f in d.findings)
            card.results.append(rc)
            continue
        if d.result in table.derived_from:
            rc.derived_note = f"{name} is calculated from other columns, so it moves together with them and is one finding with them, not an independent one."
        sel = select(validation, d.result)
        sd = spread(table, d.result)
        rc.model, rc.why, rc.worst = MODELS[d.chosen].label, sel.why[:1].upper() + sel.why[1:], d.worst
        cal = calibrate(validation, d.result, d.chosen, "chosen")
        rc.verdict, rc.verdict_after, rc.unsure = cal.verdict, cal.verdict_after, _unsure(cal)
        for kind in KINDS:
            run = validation.runs.get((d.result, kind))
            if run is None or not run.plan.available:
                continue
            s = score(run)
            rc.accuracy.append(KindAccuracy(run.plan.heading, s[d.chosen].rmse / sd, s["mean"].rmse / sd if "mean" in s else None, s["nearest"].rmse / sd if "nearest" in s else None))
            if kind in cal.kinds:
                k = cal.kinds[kind]
                rc.calibration.append(KindCal(k.heading, k.hit, k.ci, k.n_groups, k.recal_hit, _moved(k.hit, k.recal_hit)))
            own = evaluate_kind(validation, d.result, kind, d.chosen, None, refs)
            groups = evaluate_groups(validation, d.result, kind, d.chosen)
            if own is None:
                continue
            p = own.parts
            gt = _group_text(groups)
            rc.warnings.append(KindWarn(own.heading, own.n, (p["distance"].share, p["distance"].error_ratio, p["distance"].lift), (p["range"].share, p["range"].error_ratio, p["range"].lift),
                                        p["category"].share, _unseen(own), gt))
            per_kind.setdefault(kind, []).append(Numbers(name + (" [EXPLORATORY: borderline]" if d.status == BORDERLINE else ""), p["distance"].n_warned, p["distance"].lift, p["distance"].error_ratio, p["range"].n_warned))
            headings[kind] = own.heading
            if groups is not None and groups.groups:
                group_bits.setdefault(kind, []).append(groups)
        if not card.synthetic and d.status == CARRIED:
            rc.replay_sentence = NO_REPLAY_SENTENCE
        card.results.append(rc)
    for kind in KINDS:
        if kind in per_kind:
            gs = group_bits.get(kind, [])
            flagged, total = sum(x.warning.flagged for g in gs for x in g.groups), sum(len(g.groups) for g in gs)
            basis = "chance alone" if gs and all(g.null_kinds == {"chance alone"} for g in gs) else "other training groups" if gs and all(g.null_kinds == {"group-based"} for g in gs) else "a mixture" if gs else ""
            text = f"{flagged} of {total} {NOUN[kind]} flagged, threshold from {basis}" if total else "not assessed"
            card.readings.append(shift_reading(kind, headings[kind], per_kind[kind], text))
    return card
