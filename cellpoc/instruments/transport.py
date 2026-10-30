"""How the control computer talks to an instrument: a line-based transport.

Barcode scanners and balances usually speak simple text over a serial cable (RS-232, or USB that appears as a serial port) or over a network socket. A transport sends bytes and reads one line back, with a time limit.
Everything above this file (the scanner and balance drivers) works on a transport, so it can be tested with a FakeTransport that plays back what an instrument would say, and used on real hardware by giving it a SerialTransport.
The real serial transport needs the `pyserial` package, which is imported only when one is made (nothing else here needs it).
"""
from __future__ import annotations

from collections import deque
from typing import Protocol


class TransportError(Exception):
    """The instrument connection could not be opened or used. The message says why, in plain words."""


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read_line(self, timeout_s: float) -> bytes | None:
        """The next line the instrument sent (without its line ending), or None if nothing arrived within the time limit."""

    def close(self) -> None: ...


class FakeTransport:
    """Plays back a script of replies, one per read (None means 'nothing arrived: a timeout'), and remembers everything written. For tests and for running without hardware."""

    def __init__(self, replies: list[bytes | str | None] | None = None):
        self.replies: deque = deque(replies or [])
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))

    def read_line(self, timeout_s: float) -> bytes | None:
        if not self.replies:
            return None
        reply = self.replies.popleft()
        return reply.encode("ascii", "replace") if isinstance(reply, str) else reply

    def close(self) -> None:
        self.closed = True


class SerialTransport:
    """A real serial port (for example COM3). Needs the pyserial package (`pip install pyserial`), imported here and nowhere else."""

    def __init__(self, port: str, baud: int = 9600, line_ending: bytes = b"\r\n"):
        try:
            import serial                                   # noqa: PLC0415 - on purpose: only a real connection needs it
        except ImportError as exc:
            raise TransportError("Talking to a real instrument needs the 'pyserial' package. Install it with: .venv\\Scripts\\python.exe -m pip install pyserial") from exc
        try:
            self._port = serial.Serial(port, baud, timeout=1.0)
        except (OSError, ValueError, serial.SerialException) as exc:
            raise TransportError(f"The instrument port {port} could not be opened ({exc}). Check the cable, the port name in Device Manager and that no other program is using it.") from exc
        self.line_ending = line_ending

    def write(self, data: bytes) -> None:
        self._port.write(data)

    def read_line(self, timeout_s: float) -> bytes | None:
        self._port.timeout = timeout_s
        line = self._port.read_until(self.line_ending)
        return line[: -len(self.line_ending)] if line.endswith(self.line_ending) else (line or None)

    def close(self) -> None:
        self._port.close()
