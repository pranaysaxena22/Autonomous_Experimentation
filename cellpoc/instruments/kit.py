"""The set of instruments one trial uses: a barcode scanner and a balance (simulated now, real devices one day)."""
from __future__ import annotations

from dataclasses import dataclass

from .balance import Balance
from .barcode import BarcodeScanner


@dataclass
class Instruments:
    scanner: BarcodeScanner
    balance: Balance
