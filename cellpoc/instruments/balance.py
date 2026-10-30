"""The balance: one interface, a simulated balance now and a serial balance (the common 'SICS' text style) for real hardware.

A balance is asked to tare (zero itself) and to read: it answers with a Weight. A reading counts only when the balance says it is STABLE (not still settling). `dose_check` compares what was weighed with what the plan asked for.
Different balance makers use different text; this driver speaks the Mettler-Toledo SICS style (`S` asks for a stable weight, the reply is `S S   12.3456 g` when stable and `S D ...` while still settling) that many
balances offer. If the balance chosen later speaks another style, only the parsing in SicsBalance changes; the executor and the checks do not.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Protocol

from .transport import Transport

UNITS = {"g": 1.0, "mg": 0.001, "kg": 1000.0}
REPLY = re.compile(r"^S\s+(?P<flag>[SD])\s+(?P<value>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>g|mg|kg)?\s*$")


@dataclass(frozen=True)
class Weight:
    status: str                      # ok (stable), unstable, overload, underload, busy, timeout, garbled
    grams: float | None              # the weight in grams (only when status is ok)
    raw: str = ""                    # exactly what the balance sent


class Balance(Protocol):
    def tare(self) -> bool: ...

    def read(self) -> Weight: ...


def dose_check(expected_g: float, measured_g: float, tolerance_pct: float) -> str:
    """ok, under or over: is the weighed amount within the tolerance (a percentage of what was asked for)?"""
    allowed = abs(expected_g) * tolerance_pct / 100.0
    if measured_g < expected_g - allowed:
        return "under"
    if measured_g > expected_g + allowed:
        return "over"
    return "ok"


class SimulatedBalance:
    """A balance with no hardware behind it: it adds up what is poured onto it. With `noise_g` above zero it adds a repeatable (seeded) reading error."""

    def __init__(self, noise_g: float = 0.0, seed: int = 0):
        self.total = 0.0
        self.noise_g = noise_g
        self._noise = random.Random(f"balance:{seed}")

    def add(self, grams: float) -> None:
        self.total += grams

    def tare(self) -> bool:
        self.total = 0.0
        return True

    def read(self) -> Weight:
        value = self.total + (self._noise.gauss(0.0, self.noise_g) if self.noise_g else 0.0)
        return Weight("ok", round(value, 2), f"{value:.2f} g")


class SicsBalance:
    """A real balance on a transport, SICS style. `read` asks again (up to `attempts` times) while the balance says it is still settling."""

    def __init__(self, transport: Transport, timeout_s: float = 5.0, attempts: int = 3):
        self.transport, self.timeout_s, self.attempts = transport, timeout_s, attempts

    def tare(self) -> bool:
        self.transport.write(b"T\r\n")
        line = self.transport.read_line(self.timeout_s)
        return line is not None and line.decode("ascii", "replace").strip().startswith("T S")

    def read(self) -> Weight:
        last = Weight("timeout", None, "")
        for _ in range(self.attempts):
            self.transport.write(b"S\r\n")
            line = self.transport.read_line(self.timeout_s)
            if line is None:
                last = Weight("timeout", None, "")
                continue
            raw = line.decode("ascii", "replace").strip()
            match = REPLY.match(raw)
            if match:
                grams = float(match["value"]) * UNITS.get(match["unit"] or "g", 1.0)
                if match["flag"] == "S":
                    return Weight("ok", round(grams, 4), raw)
                last = Weight("unstable", None, raw)                          # still settling: ask again
                continue
            code = {"S +": "overload", "S -": "underload", "S I": "busy"}.get(raw[:3])
            last = Weight(code or "garbled", None, raw)
            if code in ("overload", "underload"):
                return last
        return last
