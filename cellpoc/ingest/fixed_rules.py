"""The rules the reader applies that never change. One list, used by docs/ingest_messages.md and by every quality report, so they cannot disagree."""
from __future__ import annotations

from .dates import TWO_DIGIT_YEAR_RULE

FIXED_RULES: list[str] = [
    f"**Two-digit years:** a year written with two digits is read as follows: **{TWO_DIGIT_YEAR_RULE}**. "
    "Every date read this way is reported (message I71, with an example) and the date column's report says how many were read this way. "
    "To avoid the rule, write four-digit years (`yyyy`) in the setup's date format.",
    "**Day and month are never guessed.** A date is read only in the format the setup states (`dd.mm.yyyy`, `mm/dd/yyyy`, `yyyy-mm-dd`, `mon.yy` ...). "
    "With no format stated, only year-month-day is read, and a warning says so (I49).",
    "**Month names** come from built-in English and Slovenian tables (short and full), or from twelve names in the setup. The computer's own language settings are never used.",
    "**A date with no day** (such as `nov.18`) becomes the first of that month and is marked month-only; a warning says the order of events inside a month is unknown (I65).",
    "**A missing value** is an empty cell or text the setup lists under `missing_markers`. Nothing else is assumed, and every marker found is counted (I64). Nothing is ever filled in.",
    "**A number** is read only when it is clearly one (`12.5`, `12,5` where the decimal mark allows, `1e-3`). Doubtful text is reported and left missing, never turned into a number.",
    "**Weight check:** a gap of exactly the stated tolerance passes; only a larger gap is flagged, and every row keeps its exact signed gap.",
    "**Rows are removed only by a stated rule** (missing values with `drop_row`, failed runs, replicate rows combined) and every removal is counted. "
    "The quality report opens with a row-accounting block that shows dropped rows and failed runs in capitals with their counts (messages I58 and I84 say the same).",
]
