"""Turning one cell of text into a number, or into 'no value', or into 'below/above a limit'. Nothing is guessed:
a cell that is not clearly a number is reported, never silently turned into one.
"""
from __future__ import annotations

import math
import re

_POINT = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?$")
_COMMA = re.compile(r"^[+-]?(?:\d+(?:,\d+)?|,\d+)(?:[eE][+-]?\d+)?$")
_LIMIT = re.compile(r"^([<>])\s*([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))$")


def parse_number(text: str, decimal: str = "auto") -> float | None:
    """The number written in the text, or None when it is not clearly one.

    decimal: "point" accepts 12.5 only, "comma" accepts 12,5 only, "auto" accepts either (a cell with both marks, like 1,234.5, is refused).
    """
    text = text.strip()
    if not text:
        return None
    if decimal == "point":
        ok, value = _POINT.match(text), text
    elif decimal == "comma":
        ok, value = _COMMA.match(text), text.replace(",", ".")
    else:
        ok = _POINT.match(text) or _COMMA.match(text)
        value = text.replace(",", ".")
    if not ok:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_limit(text: str, decimal: str = "auto") -> tuple[str, float] | None:
    """('<' or '>', the limit) for a cell such as '<0.05' or '> 100'; None if the cell is not written that way."""
    found = _LIMIT.match(text.strip())
    if not found:
        return None
    number = parse_number(found.group(2), decimal)
    return (found.group(1), number) if number is not None else None


class Markers:
    """Text that means 'no value': an empty cell always, plus the markers the setup lists (compared ignoring capital letters)."""

    def __init__(self, markers):
        self.keys = {str(m).strip().casefold(): str(m).strip() for m in (markers or []) if str(m).strip()}

    def is_missing(self, text: str) -> str | None:
        """'' for an empty cell, the marker's own spelling for a listed marker, None when the cell holds a value."""
        stripped = text.strip()
        if not stripped:
            return ""
        return self.keys.get(stripped.casefold())
