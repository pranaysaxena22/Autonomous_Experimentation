"""Which job runs next. A STUB: first come, first served.

This is the one place the real scheduling rules will go once they are written down (which drug first, what is reserved for whom, what to do when an ingredient is short). Until then the order is simply the order
the jobs were put in the queue, and a job that is blocked is passed over until someone restocks and starts it again. Everything that calls this function would work unchanged with a cleverer one.
"""
from __future__ import annotations

from ..contracts import PENDING


def choose_next(jobs, inventory):
    """The next job to start, or None when nothing is waiting. `jobs` are the queue's jobs in order; `inventory` is there for the real rules to look at (the stub does not)."""
    return next((job for job in jobs if job.status == PENDING), None)
