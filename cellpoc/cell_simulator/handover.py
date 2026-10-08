"""Writes the "what happened while nobody was in the lab" summaries, ready to display as they are."""
from __future__ import annotations

from ..contracts import AlertRecord, CalendarBlock, HandoverSummary, TrialRecord
from .clock import RunClock


def _count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def _trial_list(trials: list[TrialRecord]) -> str:
    numbers = [str(t.trial) for t in trials]
    return ("trial " if len(numbers) == 1 else "trials ") + ", ".join(numbers)


def build_handovers(clock: RunClock, calendar: list[CalendarBlock], trials: list[TrialRecord],
                    alerts: list[AlertRecord]) -> list[HandoverSummary]:
    summaries = []
    for block in calendar:
        if block.staffed:
            continue
        a, b = block.start_minute, block.end_minute
        started = [t for t in trials if a <= t.start_minute < b]
        finished = [t for t in trials if a < t.end_minute <= b]
        with_result = [t for t in finished if t.status == "Completed"]
        skipped = [t for t in finished if t.status == "Skipped"]
        good = [t for t in with_result if t.outcome == "Good"]
        block_alerts = [x for x in alerts if a <= x.minute <= b]
        for_staff = [x for x in block_alerts if x.needs_human]
        hours = (b - a) / 60
        until_end = b == clock.duration_minutes

        lines = [f"Nobody was in the lab from {clock.when(a)} to {clock.when(b)} ({hours:g} hours)."]
        if finished:
            lines.append(f"The cell finished {_count(len(finished), 'trial')}: {len(with_result)} with a result"
                         + (f" and {len(skipped)} skipped" if skipped else "") + ".")
        else:
            lines.append("No trial finished in this period.")
        lines.append(f"Recipes measured good: {_trial_list(good)}." if good else "No recipe was measured good in this period.")
        for alert in block_alerts:
            lines.append(f"{alert.when} - {alert.message}.")
        everything_so_far = [t for t in trials if t.end_minute <= b and t.status == "Completed"]
        if everything_so_far:
            best = max(everything_so_far, key=lambda t: t.margin)  # type: ignore[arg-type,return-value]
            lines.append(f"Best result so far: trial {best.trial}, dissolution {best.dissolution_pct:.1f}%, "
                         f"hardness {best.hardness_kp:.2f} kP ({best.outcome.lower()}).")
        if for_staff:
            lines.append(f"Needs your attention on arrival: {_count(len(for_staff), 'alert')} waiting "
                         f"(queued for {for_staff[0].queued_for}).")
        elif until_end:
            lines.append("The run ended with nothing waiting for staff.")
        else:
            lines.append("Nothing needs your attention.")

        summaries.append(HandoverSummary(
            a, b, clock.iso(a), clock.iso(b),
            f"While the lab was empty: {clock.when(a)} to {clock.when(b)}", " ".join(lines),
            len(started), len(with_result), len(skipped), len(good), len(block_alerts), len(for_staff)))
    return summaries
