"""The one list of units this program knows, and how an ID's unit suffix is compared with a written unit.

Rule (decision 5): the units clearly conflict -> an error; anything less clear (an unknown unit, an ID with no unit
suffix, a spelling or capital-letter difference) -> a warning. Every message that names the allowed units reads this list.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Unit:
    symbol: str      # how a person writes it
    dimension: str   # what it measures
    suffix: str      # the ending of an ID that carries this unit
    name: str        # in words


UNITS: tuple[Unit, ...] = (
    Unit("%", "share of the tablet or a percentage", "_pct", "percent"),
    Unit("g", "mass", "_g", "grams"),
    Unit("kN", "force", "_kn", "kilonewtons"),
    Unit("kP", "force", "_kp", "kilopond"),
    Unit("N", "force", "_n", "newtons"),
    Unit("min", "time", "_min", "minutes"),
    Unit("s", "time", "_s", "seconds"),
    Unit("h", "time", "_h", "hours"),
    Unit("m", "length", "_m", "metres"),
    Unit("deg", "angle", "_deg", "degrees"),
)


def allowed_symbols() -> str:
    return ", ".join(u.symbol for u in UNITS)


def unit_for_symbol(text: str) -> tuple[Unit | None, bool]:
    """(the unit, whether it was written with exactly the right capital letters). (None, False) if unknown."""
    if not isinstance(text, str):
        return None, False
    for u in UNITS:
        if u.symbol == text.strip():
            return u, True
    for u in UNITS:
        if u.symbol.lower() == text.strip().lower():
            return u, False
    return None, False


def unit_for_id(identifier: str) -> Unit | None:
    """The unit an ID ends with (the longest matching suffix), or None."""
    if not isinstance(identifier, str):
        return None
    matches = [u for u in UNITS if identifier.endswith(u.suffix) and len(identifier) > len(u.suffix)]
    return max(matches, key=lambda u: len(u.suffix)) if matches else None


@dataclass(frozen=True)
class UnitVerdict:
    level: str        # "ok", "warning" or "error"
    reason: str       # "ok", "conflict", "unknown_unit", "no_suffix" or "case"
    suffix_unit: Unit | None = None
    written_unit: Unit | None = None


def compare(identifier: str, written_unit) -> UnitVerdict:
    """Compare the unit an ID ends with against the unit written beside it."""
    from_id = unit_for_id(identifier)
    written, exact = unit_for_symbol(written_unit)
    if written is None:
        return UnitVerdict("warning", "unknown_unit", from_id, None)
    if from_id is None:
        return UnitVerdict("warning", "no_suffix", None, written)
    if from_id.symbol != written.symbol:
        return UnitVerdict("error", "conflict", from_id, written)   # different units (or different kinds of quantity): clearly in conflict
    if not exact:
        return UnitVerdict("warning", "case", from_id, written)
    return UnitVerdict("ok", "ok", from_id, written)
