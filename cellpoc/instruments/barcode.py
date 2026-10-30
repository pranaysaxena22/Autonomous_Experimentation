"""The barcode scanner: one interface, a simulated scanner now and a serial scanner for real hardware.

A scanner is asked to read once and answers with a ScanResult: ok (a label shaped like ours was read), unreadable (nothing came back, or it could not decode), or garbled (something came back that is not a label).
`classify` then compares what was read with the label the plan expects and gives the verdict the executor acts on: ok, unreadable (try again) or wrong_vial (a DIFFERENT vial is in front of the scanner: stop, a person must look).
The same classify logic runs whether the scanner is the simulated one or a real one, so the simulation exercises exactly the decision the real cell will make.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .labels import LabelFormat
from .transport import Transport


@dataclass(frozen=True)
class ScanResult:
    status: str                      # ok, unreadable, garbled
    text: str | None                 # the decoded label (only when status is ok)
    raw: str = ""                    # exactly what the scanner sent (for the log)


class BarcodeScanner(Protocol):
    def read(self) -> ScanResult: ...


def classify(result: ScanResult, expected: str) -> str:
    """ok, unreadable or wrong_vial."""
    if result.status != "ok":
        return "unreadable"
    return "ok" if result.text == expected else "wrong_vial"


class SimulatedBarcodeScanner:
    """A scanner with no hardware behind it. It reads the label of the vial it is shown, unless told to misbehave:
    `misbehaviour` is None (always reads right), 'unreadable' (the first read fails; later reads work if `retry_works`) or 'wrong_vial' (it reads another vial's label every time)."""

    def __init__(self, vial_label: str, misbehaviour: str | None = None, retry_works: bool = True, other_label: str | None = None):
        if misbehaviour not in (None, "unreadable", "wrong_vial"):
            raise ValueError("misbehaviour must be None, 'unreadable' or 'wrong_vial'.")
        self.vial_label, self.misbehaviour, self.retry_works = vial_label, misbehaviour, retry_works
        self.other_label = other_label or "V-000"
        self.reads = 0

    def read(self) -> ScanResult:
        self.reads += 1
        if self.misbehaviour == "wrong_vial":
            return ScanResult("ok", self.other_label, self.other_label)
        if self.misbehaviour == "unreadable" and (self.reads == 1 or not self.retry_works):
            return ScanResult("unreadable", None, "")
        return ScanResult("ok", self.vial_label, self.vial_label)


class SerialBarcodeScanner:
    """A real scanner on a transport. Most scanners send the decoded text and a line ending when they read a code; some need a trigger command first (`trigger`, for example b'\\x16T\\r' on some models; see the scanner's manual)."""

    def __init__(self, transport: Transport, label_format: LabelFormat, timeout_s: float = 2.0, trigger: bytes | None = None):
        self.transport, self.format, self.timeout_s, self.trigger = transport, label_format, timeout_s, trigger

    def read(self) -> ScanResult:
        if self.trigger:
            self.transport.write(self.trigger)
        line = self.transport.read_line(self.timeout_s)
        if line is None:
            return ScanResult("unreadable", None, "")
        raw = line.decode("ascii", "replace").strip("\r\n\x00 \t")
        return ScanResult("ok", raw, raw) if self.format.matches(raw) else ScanResult("garbled", None, raw)
