"""Reading dates exactly as the setup says they are written. Day and month are never guessed, and the computer's own language settings are never used.

A date format is written with pieces: yyyy (4-digit year), yy (2-digit year), mm (month number), dd (day), mon (month name, short or full)
and month (month name, full or short), with . / - or a space between, for example "yyyy-mm-dd", "dd.mm.yyyy" or "mon.yy".
Month names come from the tables below (English and Slovenian) or from a list of twelve names in the setup.
A format with no day (such as "mon.yy") gives the first of the month and is marked as month-only precision.
A 2-digit year is read by a fixed rule (TWO_DIGIT_YEAR_RULE below), and every date read that way is reported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

MONTHS = {
    "en": (["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
           ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]),
    "sl": (["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"],
           ["januar", "februar", "marec", "april", "maj", "junij", "julij", "avgust", "september", "oktober", "november", "december"]),
}
PIECES = ("month", "yyyy", "mon", "yy", "mm", "dd")        # longer first, so 'month' is not read as 'mon'
LETTERS = r"[^\W\d_]+\.?"
PIECE_PATTERNS = {"yyyy": r"\d{4}", "yy": r"\d{2}", "mm": r"\d{1,2}", "dd": r"\d{1,2}", "mon": LETTERS, "month": LETTERS}
PLAUSIBLE_YEARS = (1950, 2100)
TWO_DIGIT_YEAR_PIVOT = 70                      # a 2-digit year below this is 20yy, from this up is 19yy
TWO_DIGIT_YEAR_RULE = f"00 to {TWO_DIGIT_YEAR_PIVOT - 1} mean 2000 to {2000 + TWO_DIGIT_YEAR_PIVOT - 1}, and {TWO_DIGIT_YEAR_PIVOT} to 99 mean {1900 + TWO_DIGIT_YEAR_PIVOT} to 1999"


def month_lookup(language: str = "en", months: list[str] | None = None) -> dict[str, int]:
    """Every accepted spelling of a month (lower case, no trailing dot) -> its number 1 to 12."""
    table: dict[str, int] = {}
    if months:
        for number, name in enumerate(months, start=1):
            key = str(name).strip().casefold().rstrip(".")
            table[key] = number
            table.setdefault(key[:3], number)
    else:
        short, full = MONTHS.get(language, MONTHS["en"])
        for names in (short, full):
            for number, name in enumerate(names, start=1):
                table[name] = number
    return table


@dataclass(frozen=True)
class DateFormat:
    text: str
    pattern: re.Pattern
    has_day: bool
    months: tuple
    two_digit_year: bool = False

    @classmethod
    def build(cls, text: str, language: str = "en", months: list[str] | None = None) -> "DateFormat | None":
        """None if the format text is not made of known pieces."""
        rest, regex, seen = text.strip().lower(), [], []
        while rest:
            if rest[0] in "./- ":
                regex.append(r"\s+" if rest[0] == " " else r"\s*" + re.escape(rest[0]) + r"\s*")
                rest = rest.lstrip(" ") if rest[0] == " " else rest[1:]
                continue
            for piece in PIECES:
                if rest.startswith(piece):
                    regex.append(f"(?P<{piece}>{PIECE_PATTERNS[piece]})")
                    seen.append(piece)
                    rest = rest[len(piece):]
                    break
            else:
                return None
        if len(seen) != len(set(seen)) or not any(p in seen for p in ("mm", "mon", "month")) or not any(p in seen for p in ("yyyy", "yy")):
            return None
        return cls(text, re.compile("^" + "".join(regex) + "$", re.IGNORECASE), "dd" in seen, tuple(sorted(month_lookup(language, months).items())), "yy" in seen)

    def parse(self, value: str) -> tuple[date | None, str]:
        """(the date, "day" or "month") or (None, "") when the text does not fit the format."""
        found = self.pattern.match(value.strip())
        if not found:
            return None, ""
        parts = found.groupdict()
        lookup = dict(self.months)
        if parts.get("mm"):
            month = int(parts["mm"])
        else:
            name = (parts.get("mon") or parts.get("month") or "").casefold().rstrip(".")
            month = lookup.get(name, 0)
        year = int(parts["yyyy"]) if parts.get("yyyy") else (2000 + int(parts["yy"]) if int(parts["yy"]) < TWO_DIGIT_YEAR_PIVOT else 1900 + int(parts["yy"]))
        day = int(parts["dd"]) if parts.get("dd") else 1
        try:
            return date(year, month, day), ("day" if self.has_day else "month")
        except ValueError:
            return None, ""


def parse_excel_date(value: str) -> tuple[date | None, str]:
    """A cell that Excel stored as a real date (it was written to text as year-month-day, with a time when it has one)."""
    try:
        return datetime.fromisoformat(value).date(), "day"
    except ValueError:
        return None, ""


ISO = "yyyy-mm-dd"
