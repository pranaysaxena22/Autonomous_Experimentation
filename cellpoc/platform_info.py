"""Writes the platform section of a run record (Stage 8): the plain-text lines the dashboard's two platform tabs display.

The dashboard calculates nothing, so everything it shows about a platform run (how the pieces connect, what happened trial by trial, what the data reader and the modelling step made of the data file) is worked
out here, in advance, and stored in the record. It uses the data reader and the modelling table builder as they are and never sees the virtual lab's hidden truth.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import AboutRecord, PlatformInfo
from .ingest import report_for_setup
from .modelling import build_table_for_setup
from .platform_cell import PlatformRun
from .planner import weakest

ROOT = Path(__file__).resolve().parents[1]

ENGINE_SENTENCE = ("The decision engine of Stage 4 (the governed engine with its recalibration response) is not used in this run. The measured finding about it, from the full 4-4R comparison, is that "
                   "the adopted engine loses to simply ignoring the alarm in all four tested scenarios, not merely that it is undemonstrated as better (docs/decisions.md).")

LIMITS = [
    "This is a simulation. The arm, the tools and every time and reading are stand-ins (the Python stand-in executor and the proof of concept's virtual lab), not a real robot's reach, forces or cycle times and not a prediction about real tablets.",
    "The decision engine here is the proof of concept's adaptive strategy, which chooses the five ingredient levels. The process settings (for example compression force) are held at the middle of their ranges because that strategy does not choose them.",
    ENGINE_SENTENCE,
    "The data file named in the setup is read and checked, and a modelling table is built from it, but its fitted models do not steer this run (double-click run_platform.bat connected to see a run in which they do). The scorecards (run_scorecard.bat) show how those models do on held-out data; the sealed acceptance run (Stage 4-5) has not been carried out.",
    "The number of trials in a run is written as a range elsewhere ('about 29 to 30 trials') because the count hangs on a small timing margin; the figure of this run is what its setup produced and is not a target.",
    "Friability is planned only when the setup asks for it; the proof of concept's virtual lab does not measure it, so no friability reading appears.",
]


def _data_lines(setup: dict, base_dir) -> list[str]:
    """The reader's own words about the data file: its title (with data status), the row accounting and the points that need attention."""
    try:
        _, text = report_for_setup(setup, base_dir, ROOT)
    except Exception as exc:  # noqa: BLE001 - the tab must still show something plain
        return [f"The data file named in the setup could not be read ({type(exc).__name__}). No data summary is shown."]
    lines = text.splitlines()
    out = [lines[0].lstrip("# ").strip()] if lines else []
    if "```" in text:
        block = text.split("```")[1].strip().splitlines()
        out += [b.strip() for b in block if b.strip()]
    if "## What needs your attention" in text:
        part = text.split("## What needs your attention")[1].split("\n## ")[0]
        out += [b.strip("- ").replace("**", "").replace("`", "") for b in part.splitlines() if b.strip().startswith("- ")]
    return out or ["The data reader produced no summary."]


def _model_lines(setup: dict, base_dir) -> list[str]:
    """What the modelling step made of the data file: the table, and for each result whether it could be modelled."""
    try:
        table = build_table_for_setup(setup, base_dir, ROOT, "this setup's data file")
    except Exception as exc:  # noqa: BLE001
        return [f"The modelling table could not be built ({type(exc).__name__}). No model summary is shown."]
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    out = [f"Modelling table for the setup's data file [{label}]."]
    if table.frame is None:
        out.append("No modelling table was built for this setup's data file; the reason is given below. This does not affect the run. The scorecards (run_scorecard.bat) show how the models do on the mock and public tables.")
    else:
        out.append(f"{len(table.frame)} rows are in the table.")
    for name, response in table.responses.items():
        out.append(f"{table.column_label(name)}: {len(response.rows)} rows usable" + ("" if response.usable else " - not modelled (too few rows or no variation)") + ".")
    out += [f.text for f in table.findings if f.level in ("warning", "error")][:6]
    out.append("These models are checked on held-out data in the scorecards. They are shown here for information: this run's recipes come from the proof of concept's adaptive strategy.")
    return out


def _trial_rows(run: PlatformRun) -> list[str]:
    rows = []
    for plan, ex in zip(run.plans, run.executed):
        last = ex["actions"][-1]
        minutes = (last["actual_start_s"] + last["actual_duration_s"]) / 60
        recovery = sum(1 for a in ex["actions"] if a["origin"] == "recovery")
        fault = f"; fault: {ex['faults'][0]['cause']} ({'recovered' if ex['faults'][0]['recovered'] else 'not recovered, candidate skipped'})" if ex["faults"] else ""
        outcome = "skipped (no result)" if ex["outcome"] == "skipped" else f"result: {ex['result']['verdict']}"
        rows.append(f"Trial {ex['trial']}: {len(plan['actions'])} actions planned, {len(ex['actions'])} run ({recovery} recovery), {minutes:.0f} minutes; {outcome}{fault}.")
    return rows


def about_for(run: PlatformRun, info: PlatformInfo) -> AboutRecord:
    """The text of the 'What this shows' page for a platform run (the proof of concept's text is about its own demo run)."""
    s = run.record.summary
    shows = [
        f"One run of the configurable cell simulator on the setup '{info.setup_name}': {s.attempts_text.replace(' attempted', ' attempted in this run')}.",
        "Every trial is planned (a list of arm and tool actions) and run by an executor, which reports what really happened, including faults and the recovery actions after them; the timeline, alerts and handovers come from that.",
        "A 3D replay of those same executed timelines, and the data file and modelling table the setup names.",
    ]
    comparison_note = "A platform run is one run, so there is no strategy comparison here. The proof of concept's demo record (run.bat without a platform record) holds the comparison."
    throughput = (f"Autonomous: {s.trials_with_result} trials with results in {s.run_hours:g} hours, scaled to a 168-hour week, is {s.trials_per_week:g} per week. The manual baseline "
                  f"({s.manual_baseline_trials_per_week:g} per week by default) is an assumption you can edit. Dividing the first by the second is the only calculation this dashboard performs.")
    return AboutRecord(shows, list(info.limits), comparison_note, throughput)


def platform_info(run: PlatformRun, base_dir=None, replay_file: str = "replay.html", loop: dict | None = None) -> PlatformInfo:
    setup = run.setup
    status = weakest(setup["project"]["data_status"], run.layout.get("data_status", "illustrative"))
    executor = run.executed[0]["executor"] if run.executed else "none"
    pipeline = [
        f"Setup '{setup['project']['name']}' (data status: {status}). Every number below comes from it and from the equipment layout '{run.layout['layout_id']}'.",
        "Decision engine: chooses the next recipe from the measurements so far. It never sees the virtual lab's hidden truth.",
        "Motion planner: turns the recipe, the setup and the layout into a plan of actions (move, pick, place, pour, shake, press, stir, scan, read, wait) in five steps: dispense, mix, press, test, clean.",
        f"Executor ({executor}): runs the plan action by action and reports what really happened: actual times, readings, faults and the recovery actions after a fault.",
        "Virtual lab: supplies the instrument readings when the test step has finished.",
        "Cell simulator: reads the executed timelines to write the run record this dashboard shows (the run, timeline, handovers, alerts).",
        "3D replay: replays the same executed timelines as a picture of the cell. It calculates no result of its own.",
    ]
    model_lines, limits = _model_lines(setup, base_dir), LIMITS
    if loop is not None:                                    # the connected loop (cellpoc/connected) says in its own words how the pieces connected, what Stage 3 concluded and what this run does not show
        pipeline, model_lines, limits = loop["pipeline"], loop["model_lines"], loop["limits"]
    return PlatformInfo(label=f"{status.upper()} platform run: a simulation, not a result about real tablets.", setup_name=setup["project"]["name"], executor=executor, replay_file=replay_file, pipeline=pipeline,
                        trial_rows=_trial_rows(run), data_lines=_data_lines(setup, base_dir), model_lines=model_lines, limits=limits)
