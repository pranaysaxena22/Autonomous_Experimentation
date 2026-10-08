"""Simulated time and the staffing calendar."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..contracts import CalendarBlock
from ..settings.models import People, Run


class RunClock:
    """Converts "minutes since the run began" into dates, and tells whether anyone is in the lab."""

    def __init__(self, run: Run, people: People):
        self._start = run.start
        self._people = people
        self.duration_minutes = int(round(run.duration_hours * 60))

    def moment(self, minute: float) -> datetime:
        return self._start + timedelta(minutes=minute)

    def iso(self, minute: float) -> str:
        return self.moment(minute).strftime("%Y-%m-%d %H:%M")

    def when(self, minute: float) -> str:
        return self.moment(minute).strftime("%a %d %b %H:%M")

    def attended(self, minute: float) -> bool:
        moment = self.moment(minute)
        return (moment.weekday() in self._people.staffed_weekdays
                and self._people.staffed_from <= moment.time() < self._people.staffed_until)

    def next_staffed_start(self, minute: float) -> int | None:
        """The first minute after `minute` at which someone arrives, or None if nobody does before the run ends."""
        now = int(minute)
        for later in range(now + 1, self.duration_minutes + 1):
            if self.attended(later) and not self.attended(later - 1):
                return later
        return None

    def calendar(self) -> list[CalendarBlock]:
        """The whole run cut into alternating staffed / unattended blocks."""
        blocks: list[CalendarBlock] = []
        block_start = 0
        state = self.attended(0)
        for minute in range(1, self.duration_minutes + 1):
            now = self.attended(minute) if minute < self.duration_minutes else not state
            if now != state:
                blocks.append(self._block(block_start, minute, state))
                block_start, state = minute, now
        return blocks

    def _kind(self, start: int, end: int, staffed: bool) -> str:
        """Staffed, or for an empty lab: a Weekend if it touches Saturday or Sunday, a Night if it sits wholly between
        closing and opening time, otherwise plain Unattended."""
        if staffed:
            return "Staffed"
        if any(self.moment(m).weekday() >= 5 for m in range(start, end, 60)):
            return "Weekend"
        first, last = self.moment(start), self.moment(end)
        if first.time() >= self._people.staffed_until and last.date() > first.date() and last.time() <= self._people.staffed_from:
            return "Night"
        return "Unattended"

    def _block(self, start: int, end: int, staffed: bool) -> CalendarBlock:
        return CalendarBlock(start, end, self.iso(start), self.iso(end), staffed,
                             "Staffed" if staffed else "Unattended", self._kind(start, end, staffed))
