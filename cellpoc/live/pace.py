"""The pacer: the live run's clock. Simulated time advances at `speed` simulated seconds per real second while the run is going, stands still while it is paused, and the simulation waits on it, so nothing can be
published before its simulated moment. The clock and the sleeping function can be replaced (the health check uses a fake clock so that it needs no real waiting)."""
from __future__ import annotations

import threading
import time


class LiveStopped(Exception):
    """The live run was stopped (restarted or shut down); the simulation thread ends quietly."""


class Pacer:
    def __init__(self, speed: float = 300.0, now=time.monotonic, sleep=time.sleep):
        self._now, self._sleep = now, sleep
        self.speed = float(speed)
        self._base = 0.0                 # simulated seconds at the moment the clock last changed
        self._since: float | None = None  # real time when it started running (None = standing still)
        self._lock = threading.Lock()
        self.stopped = False
        self.waiting_for = -1.0            # the simulated second the simulation last asked to wait for (lets a test know the simulation has caught up to a moment)

    def _sim(self) -> float:
        return self._base + (0.0 if self._since is None else (self._now() - self._since) * self.speed)

    def sim_s(self) -> float:
        with self._lock:
            return self._sim()

    @property
    def running(self) -> bool:
        return self._since is not None

    def resume(self) -> None:
        with self._lock:
            if self._since is None:
                self._since = self._now()

    def pause(self) -> None:
        with self._lock:
            self._base, self._since = self._sim(), None

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self._base, self._since = self._sim(), (None if self._since is None else self._now())
            self.speed = float(speed)

    def finish_at(self, sim_s: float) -> None:
        """The run is over: the clock stops at the end of the run window."""
        with self._lock:
            self._base, self._since = max(self._sim(), sim_s), None

    def jump_to(self, sim_s: float) -> None:
        """Put the clock, standing still, at a simulated moment (used to show the page part-way through a run, in the health check)."""
        with self._lock:
            self._base, self._since = float(sim_s), None

    def stop(self) -> None:
        self.stopped = True

    def wait_until(self, sim_s: float) -> None:
        """Block until the simulated clock has reached `sim_s` (and the run is not paused short of it)."""
        self.waiting_for = sim_s
        while True:
            if self.stopped:
                raise LiveStopped()
            if self.sim_s() >= sim_s - 1e-9:
                return
            self._sleep(0.02)
