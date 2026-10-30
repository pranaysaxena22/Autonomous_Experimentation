"""The decision engine's brief (Stage 4-1): what Stage 3 concluded about each result, in a form the engine reads. Values only.

Stage 3 decides, by rules fixed in advance, which results a model predicts well enough to carry (carried), which only just (carried but exploratory) and which not at all (not assessed).
The engine must treat them accordingly and must not re-decide it: this shape is the whole of what it is told. It holds no measurements and nothing from any lab.
Only a CARRIED result may be used to rank recipes. An exploratory or not-assessed result gets no model and no probability from the engine.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

BRIEF_VERSION = 1
STATUS_CARRIED, STATUS_EXPLORATORY, STATUS_NOT_ASSESSED = "carried", "exploratory", "not_assessed"
STATUSES = (STATUS_CARRIED, STATUS_EXPLORATORY, STATUS_NOT_ASSESSED)


@dataclass(frozen=True)
class TargetBrief:
    result: str                                   # the result's column name
    label: str                                    # how it is named for people
    status: str                                   # carried, exploratory or not_assessed
    model_key: str | None = None                  # the model the Stage 3 rule chose (carried and exploratory only)
    model_label: str | None = None
    calibration_verdict: str | None = None        # honest, over-confident, under-confident or inconsistent, as the model states its 90% range
    calibration_verdict_after: str | None = None  # the same after recalibration (None: it could not be recalibrated)
    range_factor: float | None = None             # how much to widen the stated range: the median of the later-dates scale factors, never below 1
    range_factor_basis: str = ""                  # that, in words
    reason: str = ""                              # why it was not assessed, or the exploratory label
    calculated_from: tuple[str, ...] = ()         # columns this result is calculated from: it is one finding with them, not an independent one
    numeric_inputs: tuple[str, ...] = ()          # the inputs the Stage 3 model for this result was fitted on (the engine must use exactly these)
    categorical_inputs: tuple[str, ...] = ()

    @property
    def usable_for_decisions(self) -> bool:
        """The only rule that matters: a result is used to rank recipes only when Stage 3 carried it."""
        return self.status == STATUS_CARRIED


@dataclass(frozen=True)
class EngineBrief:
    version: int
    table: str
    data_label: str                               # for example SYNTHETIC DATA or REAL PUBLIC DATA, NOT CLIENT DATA
    table_tag: str                                # the exploratory or robustness-only label of the whole table, or ""
    targets: tuple[TargetBrief, ...]
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def target(self, result: str) -> TargetBrief:
        return next(t for t in self.targets if t.result == result)

    def usable(self) -> tuple[TargetBrief, ...]:
        return tuple(t for t in self.targets if t.usable_for_decisions)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"

    @staticmethod
    def from_json(text: str) -> "EngineBrief":
        raw = json.loads(text)
        if raw.get("version") != BRIEF_VERSION:
            raise ValueError(f"this brief is version {raw.get('version')}, but this program reads version {BRIEF_VERSION}")
        targets = []
        for t in raw["targets"]:
            if t["status"] not in STATUSES:
                raise ValueError(f"'{t['result']}' has an unknown status '{t['status']}'")
            targets.append(TargetBrief(**{**t, "calculated_from": tuple(t.get("calculated_from", ())), "numeric_inputs": tuple(t.get("numeric_inputs", ())),
                                          "categorical_inputs": tuple(t.get("categorical_inputs", ()))}))
        return EngineBrief(raw["version"], raw["table"], raw["data_label"], raw["table_tag"], tuple(targets), tuple(raw.get("caveats", ())))
