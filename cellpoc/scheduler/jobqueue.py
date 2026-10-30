"""The job queue: a list of jobs for several drugs, each with a status (pending, in progress, completed, blocked), started one at a time or run one after another by itself.

The cell does one job at a time. A job is one campaign, run by something the queue is given (a runner), so the queue knows nothing about simulations, pages or files: it only watches how each job is going.
A job that runs out of an ingredient stops, is marked blocked with the reason in plain words, and, when the queue is running itself, the next job starts. Nothing fails silently.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from ..contracts import BLOCKED, COMPLETED, IN_PROGRESS, PENDING, JobRecord, QueueRecord
from .inventory import Inventory
from .policy import choose_next


class RunHandle(Protocol):
    """What the queue needs from a job that has been started."""
    status: str                       # ready, running, paused, finished, blocked, failed or stopped
    reason: str                       # why it blocked or failed, in plain words
    folder: str                       # where its own run record was saved (empty until it is)

    def progress(self) -> tuple[int, int, int]: ...          # (trials started, trials with a result, good results)
    def stop(self) -> None: ...


class JobRunner(Protocol):
    def minimum_need(self, job: "Job") -> dict[str, float]: ...        # the least of each ingredient that one batch of this job could possibly need
    def start(self, job: "Job", inventory: Inventory) -> RunHandle: ...


@dataclass
class Job:
    id: str
    drug: str
    setup_id: str
    setup_label: str
    status: str = PENDING
    reason: str = ""
    trials_started: int = 0
    trials_with_result: int = 0
    good: int = 0
    folder: str = ""
    handle: RunHandle | None = None

    def record(self) -> JobRecord:
        folder = self.handle.folder if self.handle is not None and self.status in (COMPLETED, BLOCKED) else self.folder          # a run saves itself a moment after it ends, so ask it again each time
        return JobRecord(self.id, self.drug, self.setup_id, self.setup_label, self.status, self.reason, self.trials_started, self.trials_with_result, self.good, folder)


class JobQueue:
    def __init__(self, jobs: list[Job], inventory: Inventory, runner: JobRunner, policy=choose_next, watch: bool = True, every: float = 0.25):
        self.jobs, self.inventory, self.runner, self.policy = jobs, inventory, runner, policy
        self.automated = False
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._every = every
        if watch:
            threading.Thread(target=self._watch, name="job-queue", daemon=True).start()

    # ------------------------------------------------------------------ what the page shows
    def snapshot(self) -> QueueRecord:
        with self._lock:
            return QueueRecord([j.record() for j in self.jobs], self.inventory.levels(), self.automated, self._active_id())

    def _active_id(self) -> str | None:
        return next((j.id for j in self.jobs if j.status == IN_PROGRESS), None)

    # ------------------------------------------------------------------ what a person can do
    def start(self, job_id) -> str | None:
        """Start one job. Returns a plain sentence when it cannot be started."""
        with self._lock:
            job = next((j for j in self.jobs if j.id == job_id), None)
            if job is None:
                return "That job is not in the queue."
            if self._active_id() is not None:
                return "A job is already running. Wait for it to finish, or reset the queue."
            if job.status == COMPLETED:
                return "That job is already completed. Reset the queue to run it again."
            self._begin(job)
            return None

    def run_all(self) -> str | None:
        """Let the queue run itself: the next waiting job starts as soon as the one before it has finished or been blocked."""
        with self._lock:
            if all(j.status != PENDING for j in self.jobs) and self._active_id() is None:
                return "No job is waiting. Reset the queue, or restock and start a blocked job again."
            self.automated = True
            self._advance()
            return None

    def stop_automation(self) -> None:
        with self._lock:
            self.automated = False

    def restock(self) -> None:
        with self._lock:
            self.inventory.restock()

    def reset(self) -> None:
        """Back to the start: every job waiting, the shelf as it was, nothing running."""
        with self._lock:
            active = next((j for j in self.jobs if j.status == IN_PROGRESS), None)
            if active is not None and active.handle is not None:
                active.handle.stop()
            self.automated = False
            for job in self.jobs:
                job.status, job.reason, job.trials_started, job.trials_with_result, job.good, job.folder, job.handle = PENDING, "", 0, 0, 0, "", None
            self.inventory.reset()

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            self.automated = False
            for job in self.jobs:
                if job.status == IN_PROGRESS and job.handle is not None:
                    job.handle.stop()

    # ------------------------------------------------------------------ moving on
    def _begin(self, job: Job) -> None:
        """Start the job, unless the shelf cannot cover even the smallest batch: then it is blocked at once, with the reason."""
        short = self.inventory.preflight(self.runner.minimum_need(job))
        if short is not None:
            job.status, job.reason, job.handle = BLOCKED, short.message + " The job did not start.", None
            return
        job.status, job.reason, job.trials_started, job.trials_with_result, job.good = IN_PROGRESS, "", 0, 0, 0
        job.handle = self.runner.start(job, self.inventory)

    def _advance(self) -> None:
        """While the queue runs itself and nothing is running: start the next job the policy picks (a job blocked at once is passed over and the next is tried)."""
        while self.automated and self._active_id() is None:
            nxt = self.policy(self.jobs, self.inventory)
            if nxt is None:
                self.automated = False
                return
            self._begin(nxt)

    def tick(self) -> None:
        """Look at the job in progress and note how it is going; when it ends, say how, and move on if the queue runs itself."""
        with self._lock:
            job = next((j for j in self.jobs if j.status == IN_PROGRESS), None)
            if job is None or job.handle is None:
                self._advance()
                return
            job.trials_started, job.trials_with_result, job.good = job.handle.progress()
            state = job.handle.status
            if state == "finished":
                job.status, job.folder = COMPLETED, job.handle.folder
            elif state == "blocked":
                job.status, job.reason, job.folder = BLOCKED, job.handle.reason, job.handle.folder
            elif state == "failed":
                job.status, job.reason = BLOCKED, job.handle.reason or "The run stopped unexpectedly. Its own page has the details."
            elif state == "stopped":
                job.status, job.reason, job.handle = PENDING, "", None          # a person stopped it (a restart, or another study chosen): it can be started again
                self.automated = False
                return
            else:
                return
            self._advance()

    def _watch(self) -> None:
        while not self._closed.wait(self._every):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the watcher must never die; the page shows the jobs as they last were
                pass
