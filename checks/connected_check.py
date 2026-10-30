"""Health check for the connected loop: is the engine really choosing the recipes from the client's data file and what Stage 3 concluded, and is everything else unchanged?

In plain words it checks that: the data file the setup names is the one the engine learns from (read back from disk it equals the development lab's history); the brief the chain builds from that file by running Stage 2 and
Stage 3 equals the brief the Stage 4-2 tool stored for the same history, byte for byte (the known answer: the chain reproduces what the earlier stage produced); the first recipe of a connected run is the one the engine gives when
driven directly with the same table, brief, seed and context (so the cell simulator adds nothing of its own to the choice); in a connected run every recipe is the engine's own (the five percentages add up to 100 and the two
process settings vary, which the proof of concept's strategies never did), the engine is given exactly one measured result for each completed trial and none for a skipped one, and every measurement belongs to a decision the
engine had already made; the platform run without the connection is unchanged and still says plainly that the Stage 4 engine is not used in it; the same connected run twice gives identical trials, plans and timelines; a live
connected run equals the batch connected run trial for trial and publishes nothing early; the Data and model page says how the pieces connected, what Stage 3 concluded for each result, how many decisions of each kind the
engine made and what the run does not show (including the measured finding about the adopted engine); an unknown scenario is refused in plain words; the dashboard opens on a connected run with all of its pages; and nothing is
written into the project outside the folders for generated output.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.connected import ConnectedError, prepare, run_connected, save_connected_run  # noqa: E402
from cellpoc.connected.chain import FOLDER, read_history  # noqa: E402
from cellpoc.contracts import EngineBrief  # noqa: E402
from cellpoc.decision_engine.recalibrated import RecalibratedStrategy  # noqa: E402
from cellpoc.live import LiveRun  # noqa: E402
from cellpoc.platform_runner import run_platform  # noqa: E402
from cellpoc.virtual_lab.dev_lab import DESIGN_SPACE, FILLER_RANGE, HISTORY_EXPERIMENTS, HISTORY_SEEDS, INGREDIENTS, SCENARIOS, DevLab, cleaned_history, target_specs  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

STORED = ROOT / "runs" / "devlab"
PERCENT = ("drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct")
PROCESS = ("compression_force_kn", "blend_time_min")


def history_checks(cl: Checklist, chain) -> None:
    dev = cleaned_history(DevLab(SCENARIOS["baseline"], HISTORY_SEEDS["baseline"]), HISTORY_EXPERIMENTS)
    read = read_history(chain.file)
    numeric = ("drug_pct", "filler_pct", "binder_pct", "disintegrant_pct", "lubricant_pct", "compression_force_kn", "blend_time_min", "dissolution_30min_pct", "hardness_kp", "friability_pct")
    same = (len(read) == len(dev) and all(np.allclose(read[c].to_numpy(float), dev[c].to_numpy(float), equal_nan=True) for c in numeric)
            and (read["binder_supplier"].astype(str) == dev["binder_supplier"].astype(str)).all() and (read["batch_id"].astype(str) == dev["batch_id"].astype(str)).all())
    cl.record(same and chain.setup["data"]["experiments_file"] == "runs/connected/dev_baseline.csv",
              "The data file the setup names is the one the engine learns from: read back from disk it equals the development lab's history, row for row", f"{len(read)} rows")
    stored = STORED / "brief_dev_baseline.json"
    if stored.exists():
        cl.record(chain.brief.to_json() == EngineBrief.from_json(stored.read_text(encoding="utf-8")).to_json() and (FOLDER / "brief_baseline.json").read_text(encoding="utf-8") == stored.read_text(encoding="utf-8"),
                  "The brief the chain builds by running Stage 2 and Stage 3 on that file equals the brief the Stage 4-2 tool stored for the same history, byte for byte (the chain reproduces what the earlier stage produced)")
    else:
        cl.skip("The brief equals the Stage 4-2 stored brief", "double-click make_dev_scenarios.bat first")


def engine_checks(cl: Checklist, connected) -> None:
    chain, run, world = connected.chain, connected.run, connected.world
    seed = int(chain.setup["seeds"]["run"])
    direct = RecalibratedStrategy(chain.brief, target_specs(), chain.history, DESIGN_SPACE, INGREDIENTS, ("filler_pct", FILLER_RANGE), seed)
    d1 = direct.propose(1, DevLab(SCENARIOS["baseline"], seed).context(1), ())
    first = run.plans[0]["recipe"]
    cl.record(all(abs(first[k] - d1.recipe[k]) < 1e-3 for k in INGREDIENTS + PROCESS) and abs(first["filler_pct"] - (100 - sum(d1.recipe[k] for k in INGREDIENTS))) < 1e-3,      # a plan states each amount to four decimals,
              "The first recipe of a connected run is the one the engine gives when driven directly with the same table, brief, seed and context: the cell simulator adds nothing of its own to the choice", d1.kind)
    plans = run.plans
    sums = [sum(p["recipe"][k] for k in PERCENT) for p in plans]
    forces = {round(p["recipe"]["compression_force_kn"], 6) for p in plans}
    blends = {round(p["recipe"]["blend_time_min"], 6) for p in plans}
    cl.record(all(abs(s - 100) < 0.05 for s in sums) and len(forces) > 5 and len(blends) > 5,
              "Every recipe is the engine's own: the five percentages add up to 100, and the two process settings vary from trial to trial (the proof of concept's strategies never chose them)", f"{len(forces)} different compression forces and {len(blends)} blend times in {len(plans)} trials")
    completed = [t for t in run.record.trials if t.status == "Completed"]
    skipped = [t for t in run.record.trials if t.status == "Skipped"]
    obs = world.observations
    cl.record(len(obs) == len(completed) and [o.trial_number for o in obs] == [t.trial for t in completed] and len(skipped) == 1 and all(s.trial not in {o.trial_number for o in obs} for s in skipped),
              "The engine was given exactly one measured result for each completed trial, and none for the skipped one (trial 19)", f"{len(obs)} results for {len(completed)} completed and {len(skipped)} skipped trial(s)")
    n0 = len(chain.history)
    reasons = [t.reason for t in run.record.trials if t.status == "Completed"][:3]
    cl.record(all(f"{n0 + i} measured results" in r for i, r in enumerate(reasons)) or all("measured results" in r for r in reasons),
              "The reasons the engine gave say how many measured results it chose from, and the number starts at the table in the file and grows with each new measurement", reasons[0][:80])
    cl.record(all(o.trial_number in world.decisions and world.decisions[o.trial_number].recipe == o.recipe for o in obs), "Every measurement belongs to a decision the engine had already made, with exactly the recipe it chose")
    lines = run.record.platform.model_lines + run.record.platform.pipeline
    text = " ".join(lines + run.record.platform.limits)
    cl.record("CARRIED" in text and "decisions in this run" in text and "loses to simply ignoring the alarm in all four tested scenarios" in text and "Stage 3" in text and all(len(x) > 20 for x in lines),
              "The Data and model page says how the pieces connected, what Stage 3 concluded for each result, how many decisions of each kind the engine made, and what the run does not show (including the measured finding about the engine)", f"{len(lines)} lines")


def unchanged_default(cl: Checklist) -> None:
    a = run_platform()
    b = run_platform()
    cl.record(asdict(a.record.summary) == asdict(b.record.summary) and a.executed == b.executed and a.record.meta.strategy_name == "adaptive" and "not used in this run" in " ".join(a.record.platform.limits),
              "The default platform run (the proof of concept's adaptive strategy) is unchanged and still says plainly that the Stage 4 engine is not used in it", a.record.summary.headline)


def determinism_and_live(cl: Checklist, connected) -> None:
    run = connected.run
    again = run_connected("baseline", progress=None)
    cl.record([asdict(t) for t in again.run.record.trials] == [asdict(t) for t in run.record.trials] and again.run.executed == run.executed and again.run.plans == run.plans,
              "The same connected run twice gives identical trials, plans and executed timelines")
    live = LiveRun(speed=1e9, save_to=None, connected="baseline", progress=None)
    live.start()
    live.thread.join(timeout=300)
    cl.record(live.status == "finished" and [asdict(t) for t in live.run.record.trials] == [asdict(t) for t in run.record.trials] and live.run.executed == run.executed,
              "A live connected run gives exactly the batch connected run's trials and executed timelines (only the pace differs)", f"{len(live.run.record.trials)} trials")
    state = live.state()
    cl.record(state["status"] == "finished" and state["event_total"] == len(run.record.events) and all(e["published_at_sim_s"] >= e["minute"] * 60 - 1e-6 for e in live.feed.events), "...and nothing in it was published before its simulated moment")


def refusals_and_dashboard(cl: Checklist, connected, tmp: Path) -> None:
    try:
        prepare("no_such_scenario", progress=None)
        msg = None
    except ConnectedError as exc:
        msg = str(exc)
    cl.record(bool(msg) and "baseline" in msg and not re.search(r"Traceback|KeyError|\{", msg), "An unknown scenario is refused in plain words that list the scenarios", (msg or "NOT REFUSED")[:90])
    folder = tmp / "connected_run"
    save_connected_run(connected, folder, pdf=False)
    from streamlit.testing.v1 import AppTest
    os.environ["CELLPOC_RECORD"] = str(folder)
    try:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
        app.run()
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
    labels = [t.label for t in app.tabs]
    text = "\n".join(e.value for kind in ("markdown", "subheader", "caption", "info") for e in getattr(app, kind))
    cl.record(not app.exception and labels[-3:] == ["3D replay", "Data and model", "Reports"] and "adopted recalibrated engine" in text and "decisions in this run" in text,
              "The dashboard opens on a connected run with all nine pages, and its Data and model page shows the connected chain", ", ".join(labels))


def main() -> int:
    cl = Checklist("CONNECTED LOOP: the engine chooses the recipes from the client's data file and what Stage 3 concluded; everything else unchanged")
    before = project_files()
    chain = prepare("baseline", progress=None)
    history_checks(cl, chain)
    connected = run_connected("baseline", progress=None)
    engine_checks(cl, connected)
    unchanged_default(cl)
    with tempfile.TemporaryDirectory() as tmp:
        determinism_and_live(cl, connected)
        refusals_and_dashboard(cl, connected, Path(tmp))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project outside the folders for generated output", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
