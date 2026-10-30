"""The live run: the platform's configurable cell simulator, running on its own thread against the pacer, publishing everything it does into a feed as it happens.

It is the SAME simulation as a batch platform run (same setup, same seeds, same engine, planner, executor and lab): only the pace differs. Every event waits for its simulated moment before it is published, so the next
recipe is chosen at the cell's Reason step, a result is published when its test finishes, a fault when it happens. The health check proves a live run gives exactly the batch run's trials, timelines and record.
It never sees the virtual lab's hidden truth: it asks the injected lab to measure, as the batch run does.
"""
from __future__ import annotations

import threading
from pathlib import Path

from ..contracts import meets_spec
from ..decision_engine import AdaptiveStrategy
from ..executor import PythonStandInExecutor
from ..platform_cell import PlatformRun, PlatformSimulation
from ..platform_info import about_for, platform_info
from ..platform_runner import PlatformRunError, build_replay, load_inputs, save_platform_run
from ..setup import example_setup_path, load_setup
from ..virtual_lab import VirtualLab
from .pace import LiveStopped, Pacer

LIVE_FOLDER = Path(__file__).resolve().parents[2] / "runs" / "live"
ALERT_KINDS = {"fault", "recovery", "candidate_skipped", "alert_queued"}


class Feed:
    """What the simulation has published so far. Thread-safe: the simulation appends, the page's requests read."""

    def __init__(self):
        self.lock = threading.Lock()
        self.events: list[dict] = []
        self.timelines: list[dict] = []
        self.timeline_times: list[float] = []           # the simulated second at which each trial's timeline was published
        self.results: list[dict] = []
        self.alerts: list[dict] = []

    def add_event(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)
            if event["kind"] in ALERT_KINDS:
                self.alerts.append(event)

    def add_timeline(self, executed: dict, published_at_sim_s: float = 0.0) -> None:
        with self.lock:
            self.timelines.append(executed)
            self.timeline_times.append(published_at_sim_s)

    def add_result(self, row: dict) -> None:
        with self.lock:
            self.results.append(row)

    def read(self, timelines_seen: int, events_seen: int) -> dict:
        with self.lock:
            return {"timelines": self.timelines[timelines_seen:], "timeline_total": len(self.timelines), "events": self.events[events_seen:], "event_total": len(self.events),
                    "results": list(self.results), "alerts": list(self.alerts)}


class LiveSimulation(PlatformSimulation):
    """The platform simulation with a pace: every event waits for its simulated moment, then is published."""

    def __init__(self, *args, pacer: Pacer, feed: Feed, **kwargs):
        super().__init__(*args, **kwargs)
        self.pacer, self.feed = pacer, feed
        self._good = 0

    def log(self, minute: float, kind: str, message: str, trial: int | None = None, station: str | None = None) -> None:
        self.pacer.wait_until(minute * 60)
        super().log(minute, kind, message, trial, station)
        event = self.events[-1]
        self.feed.add_event({"minute": minute, "when": event.when, "kind": kind, "trial": trial, "message": message, "published_at_sim_s": self.pacer.sim_s()})
        if kind == "measurement":                                   # a result is published at the moment its test has finished
            m = self.history[-1]
            good = meets_spec(m.dissolution_pct, m.hardness_kp, self.settings.specifications)
            self._good += int(good)
            self.feed.add_result({"trial": trial, "when": event.when, "minute": minute, "published_at_sim_s": self.pacer.sim_s(), "dissolution_pct": m.dissolution_pct, "hardness_kp": m.hardness_kp, "verdict": "Good" if good else "Not good", "good_so_far": self._good})
        elif kind == "candidate_skipped":
            self.feed.add_result({"trial": trial, "when": event.when, "minute": minute, "published_at_sim_s": self.pacer.sim_s(), "dissolution_pct": None, "hardness_kp": None, "verdict": "No result", "good_so_far": self._good})

    def plan_and_run(self, trial, start_minute, formulation, why, readings, fault):
        plan, executed = super().plan_and_run(trial, start_minute, formulation, why, readings, fault)
        if getattr(readings, "real", False):                       # the real run of a trial (not the trial run without readings that only learns how long it will take)
            self.pacer.wait_until(start_minute * 60)               # the trial starts when the cell reaches it
            self.feed.add_timeline(executed, self.pacer.sim_s())
        return plan, executed


class LiveRun:
    """One live run: starts paused, runs on its own thread once started, and saves the finished run like a batch run."""

    def __init__(self, setup_path: Path | str | None = None, speed: float = 300.0, pacer: Pacer | None = None, save_to: Path | str | None = LIVE_FOLDER, connected: str | None = None, progress=print):
        """`connected` names a development scenario to run with the loop connected (the experiment table, Stage 3's conclusions and the adopted engine choose the recipes); without it the run is the platform run with the
        proof of concept's adaptive strategy."""
        self.pacer = pacer or Pacer(speed)
        self.feed = Feed()
        self.save_to = Path(save_to) if save_to else None
        self.status = "ready"            # ready, running, paused, finished, stopped, failed
        self.message = ""
        self.saved: str | None = None
        self.run: PlatformRun | None = None
        self.thread: threading.Thread | None = None
        self.chain = self.world = None
        if connected:
            from ..connected import build_simulation, prepare            # imported here: the connected loop is opt-in and fits models the first time
            self.chain = prepare(connected, None, progress)
            self.sim, self.world = build_simulation(self.chain, LiveSimulation, pacer=self.pacer, feed=self.feed)
            self.setup, self.layout, self.settings, self.base_dir = self.chain.setup, self.sim.layout, self.sim.settings, None
            return
        path = Path(setup_path) if setup_path else example_setup_path()
        loaded = load_setup(path)
        self.setup, self.layout, self.settings = load_inputs(path)
        self.base_dir = loaded.base_dir
        engine = AdaptiveStrategy(self.settings.design_space, self.settings.specifications, self.settings.engine, self.settings.run.random_seed)
        self.sim = LiveSimulation(self.settings, self.setup, self.layout, VirtualLab(self.settings), engine, "live", PythonStandInExecutor(), pacer=self.pacer, feed=self.feed)

    # ---- controls
    def _launch(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self._work, name="live-run", daemon=True)
            self.thread.start()

    def start(self) -> None:
        self._launch()
        self.pacer.resume()
        if self.status in ("ready", "paused"):
            self.status = "running"

    def pause(self) -> None:
        if self.status == "running":
            self.pacer.pause()
            self.status = "paused"

    def set_speed(self, speed: float) -> None:
        self.pacer.set_speed(speed)

    def stop(self) -> None:
        self.pacer.stop()

    def fast_forward(self, to_sim_s: float, then_speed: float) -> None:
        """Put the run at a simulated moment and stand still there: the simulation publishes everything up to it at once, then waits (used by the health check to show the page part-way through a run)."""
        self.pacer.jump_to(to_sim_s)
        self._launch()
        self.status = "paused"
        while self.pacer.waiting_for <= to_sim_s and self.thread.is_alive():
            threading.Event().wait(0.002)
        self.set_speed(then_speed)

    # ---- the simulation thread
    def _work(self) -> None:
        try:
            run = self.sim.run_platform()
            if self.chain is not None:
                from ..connected import finish
                finish(run, self.chain, self.world)
            else:
                run.record.platform = platform_info(run, self.base_dir)
                run.record.about = about_for(run, run.record.platform)
            self.run = run
            self.pacer.finish_at(self.sim.duration * 60)
            self.status = "finished"
            if self.save_to:
                save_platform_run(run, self.save_to)
                build_replay(run, self.save_to)
                self.saved = str(self.save_to)
        except LiveStopped:
            self.status = "stopped"
        except PlatformRunError as exc:
            self.status, self.message = "failed", str(exc)
        except Exception:  # noqa: BLE001 - the page shows a plain sentence, never a technical trace
            self.status, self.message = "failed", "The live run stopped unexpectedly. Double-click check_live.bat to see what is wrong."

    # ---- what the page asks for
    def state(self, timelines_seen: int = 0, events_seen: int = 0) -> dict:
        sim_s = self.pacer.sim_s()
        when = self.sim.clock.when(min(sim_s, self.sim.duration * 60) / 60)
        out = {"run_id": "live", "label": "ILLUSTRATIVE live run: a simulation, not a result about real tablets.", "status": self.status, "speed": self.pacer.speed, "sim_s": sim_s, "duration_s": self.sim.duration * 60,
               "clock_when": when, "message": self.message, "saved": self.saved, "good_so_far": self.sim._good}
        out.update(self.feed.read(timelines_seen, events_seen))
        if self.run is not None:
            s = self.run.record.summary
            out["summary"] = {"headline": s.headline, "attempts_text": s.attempts_text}
        return out
