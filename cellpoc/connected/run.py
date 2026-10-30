"""The connected run: one platform run in which the loop is closed. The experiment table is read and judged (Stage 2 and 3), its conclusions become the engine's brief (Stage 4-1), and the adopted engine (Stage 4) chooses
every recipe, process settings included, from that table and the measurements so far; the planner, the executor, the cell simulator and the lab are the existing ones.

Everything is the development lab's synthetic world, labelled SYNTHETIC: it shows that the chain works end to end, not that it works on real data. The default platform run (the proof of concept's adaptive strategy) is unchanged."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..executor import PythonStandInExecutor
from ..platform_cell import PlatformRun, PlatformSimulation
from ..platform_info import ENGINE_SENTENCE, about_for, platform_info
from ..platform_runner import PlatformRunError, build_inputs, build_replay, save_platform_run
from ..reports import write_reports
from .chain import FOLDER, Chain, prepare
from .world import ConnectedWorld

CONNECTED_RUN_FOLDER = FOLDER.parent / "connected_run"


@dataclass
class ConnectedRun:
    run: PlatformRun
    chain: Chain
    world: ConnectedWorld


def loop_lines(chain: Chain, world: ConnectedWorld, run: PlatformRun | None = None) -> dict:
    """The words of the Data and model page for a connected run: how the pieces connected, what Stage 3 concluded, what the engine did, and what this run does not show."""
    setup, brief = chain.setup, chain.brief
    pipeline = [
        f"Setup '{setup['project']['name']}' (data status: synthetic): the example setup's equipment, calendar and scripted faults, with the development lab's history as the experiment table.",
        f"Data reader (Stage 2): reads and cleans {chain.file.name}, accounts for every row and writes down every assumption (see the data page).",
        "Modelling (Stage 3): judges the models only on groups they have not seen (whole batches, suppliers, later dates), checks whether each model's stated range is honest, and the carry rule decides which results the engine may use.",
        "Engine brief (Stage 4-1): what Stage 3 concluded, in the form the engine reads. A result that was not carried is never modelled.",
        "Decision engine (the adopted recalibrated engine, Stage 4): chooses each recipe, process settings included, from this table, the brief and the measurements so far. It never sees the lab's hidden truth.",
        "Motion planner and executor: turn each recipe into a plan of arm actions and run it, with the faults the setup scripts.",
        "Development lab: the synthetic world the table came from; it supplies the instrument readings when each test has finished, and the engine is told only those.",
        "Cell simulator, dashboard, 3D replay and reports: read the same executed timelines and the same run record.",
    ]
    label_of = {"carried": "CARRIED (the engine may model it)", "exploratory": "carried but exploratory (the engine makes no decision from it)", "not_assessed": "NOT ASSESSED (never modelled)"}
    model_lines = list(chain.steps)
    for t in brief.targets:
        line = f"{t.label}: {label_of.get(t.status, t.status)}"
        if t.model_label:
            line += f"; model {t.model_label}"
        if t.range_factor is not None:
            line += f"; its stated 90% range is widened by a factor of {t.range_factor:.2f}"
        model_lines.append(line + ".")
    if world.decisions:
        kinds = Counter(d.kind for d in world.decisions.values())
        watch = sum(1 for d in world.decisions.values() if d.stale)
        model_lines.append(f"The engine made {len(world.decisions)} decisions in this run: " + ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in sorted(kinds.items())) + f". The staleness watch flagged a target at {watch} of them.")
    limits = [
        "This is a simulation. The arm, the tools and every time and reading are stand-ins, not a real robot's reach, forces or cycle times, and not a prediction about real tablets.",
        "The experiment table is the development lab's synthetic history and the lab that measures the recipes is the same synthetic world. This shows that the chain works from data to model to engine to cell, not that it works on real data or on a client's file.",
        "Here the recipes are chosen by the adopted Stage 4 engine from this table and the measurements so far. " + ENGINE_SENTENCE.split("is not used in this run. ")[-1],
        "The engine also models friability, but this cell's instruments read only dissolution and hardness, so a trial counts as good on those two (the targets the proof of concept's records judge).",
        "The engine's stated chances and ranges have known weaknesses (a high false-alarm rate of its watch, intermediate chances not reliably honest) and five of its constants are provisional; they are recorded in docs/decisions.md. Its sealed acceptance run has not been done.",
        "The number of trials in a run is written as a range elsewhere ('about 29 to 30 trials') because the count hangs on a small timing margin; the figure of this run is what its setup produced and is not a target.",
    ]
    return {"pipeline": pipeline, "model_lines": model_lines, "limits": limits}


def finish(run: PlatformRun, chain: Chain, world: ConnectedWorld, base_dir=None) -> None:
    """Attach what the platform pages show for a connected run to its record."""
    run.record.platform = platform_info(run, base_dir, loop=loop_lines(chain, world, run))
    run.record.about = about_for(run, run.record.platform)


def build_simulation(chain: Chain, simulation_class=PlatformSimulation, **extra):
    """The platform simulation wired to the connected world. Returns (simulation, world); `simulation_class` lets the live run add its pacing."""
    layout, settings = build_inputs(chain.setup, None)
    world = ConnectedWorld(chain, int(chain.setup["seeds"]["run"]))
    sim = simulation_class(settings, chain.setup, layout, world, world, f"connected-{chain.scenario}", PythonStandInExecutor(), world=world, **extra)
    return sim, world


def run_connected(scenario: str = "baseline", progress=print, jobs: int | None = None) -> ConnectedRun:
    """One connected run of the whole run window, planned and executed trial by trial, faults from the setup."""
    chain = prepare(scenario, jobs, progress)
    sim, world = build_simulation(chain)
    run = sim.run_platform()
    finish(run, chain, world)
    return ConnectedRun(run, chain, world)


def save_connected_run(connected: ConnectedRun, folder: Path | str = CONNECTED_RUN_FOLDER, pdf: bool = True) -> Path:
    """Write the run (record, plans, executed timelines, 3D replay, report files) the same way a platform run is written."""
    record = save_platform_run(connected.run, folder)
    build_replay(connected.run, folder)
    write_reports(folder, pdf=pdf)
    return record


__all__ = ["CONNECTED_RUN_FOLDER", "ConnectedRun", "PlatformRunError", "build_simulation", "finish", "loop_lines", "run_connected", "save_connected_run"]
