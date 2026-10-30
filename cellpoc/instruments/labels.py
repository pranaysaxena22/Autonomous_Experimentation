"""The vial label: how a trial's vial is named on its barcode, and how a scanned text is recognised as such.

The text on a label is `prefix` followed by the trial number padded to `digits` digits (the default, V- and 3 digits, gives V-008 for trial 8). The format is data (an optional block in the equipment layout file),
so a different labelling scheme is a settings change, not a code change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelFormat:
    prefix: str = "V-"
    digits: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.prefix, str) or not 1 <= len(self.prefix) <= 8 or not re.fullmatch(r"[A-Za-z0-9_\-]+", self.prefix):
            raise ValueError("The label prefix must be 1 to 8 letters, digits, '-' or '_'.")
        if not isinstance(self.digits, int) or isinstance(self.digits, bool) or not 1 <= self.digits <= 8:
            raise ValueError("The number of digits on a label must be a whole number from 1 to 8.")

    def label(self, trial: int) -> str:
        """The text on the vial of this trial."""
        return f"{self.prefix}{trial:0{self.digits}d}"

    def matches(self, text: str) -> bool:
        """Is this text shaped like one of our labels (whichever trial it names)?"""
        return re.fullmatch(re.escape(self.prefix) + r"\d{" + str(self.digits) + r"}", text) is not None

    def trial_of(self, text: str) -> int | None:
        return int(text[len(self.prefix):]) if self.matches(text) else None


def format_from_layout(layout: dict) -> LabelFormat:
    """The label format named in the layout's optional `instruments.barcode` block (the defaults when it is absent)."""
    block = (layout.get("instruments") or {}).get("barcode") or {}
    return LabelFormat(block.get("prefix", LabelFormat.prefix), block.get("digits", LabelFormat.digits))
