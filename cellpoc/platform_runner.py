"""Wires the platform pieces together and runs the configurable cell simulator on a setup. The platform's counterpart of `runner.py`: the only place that knows all of them.

Run `python -m cellpoc.platform_runner` (or double-click make_platform_demo.bat) to build a platform run from the example setup and open its 3D replay.
Everything it makes is labelled with the weakest data status of its inputs (illustrative or synthetic), and nothing leaves the computer.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import client_story, run_store
from .decision_engine import AdaptiveStrategy, FixedListStrategy
from .executor import PythonStandInExecutor
from .platform_cell import PlatformRun, PlatformSimulation
from .viewer import build_viewer
from .planner import weakest
from .platform_info import about_for, platform_info
from .reports import write_reports
from .setup import example_setup_path, has_errors, load_setup, resolve_reference, to_poc_settings, validate
from .settings.loader import settings_from_dict
from .virtual_lab import VirtualLab

PLATFORM_FOLDER = Path(__file__).resolve().parents[1] / "runs" / "platform"


class PlatformRunError(Exception):
    """The setup cannot be simulated. The message says what to change, in plain words."""


def build_inputs(setup: dict, base_dir: Path | str | None = None):
    """Check and convert a setup that is already in memory: returns (layout, the proof of concept's settings built from it). Refuses, in plain words, a setup that has errors or cannot be represented."""
    problems = validate(setup, base_dir=base_dir)
    if has_errors(problems):
        first = [p.text for p in problems if p.level == "error"][:3]
        raise PlatformRunError("The setup has errors, so it cannot be simulated: " + "; ".join(first))
    conversion = to_poc_settings(setup, problems)
    if not conversion.ok:
        raise PlatformRunError("This setup cannot be simulated yet: " + " ".join(n.text for n in conversion.notes))
    layout_path = resolve_reference(setup["equipment"]["layout_file"], Path(base_dir) if base_dir else None)
    if layout_path is None:
        raise PlatformRunError(f"The layout file '{setup['equipment']['layout_file']}' named in the setup was not found.")
    return json.loads(layout_path.read_text(encoding="utf-8")), settings_from_dict(conversion.settings)


def load_inputs(setup_path: Path | str | None = None):
    """Read, check and convert a setup file: returns (setup, layout, the proof of concept's settings built from it)."""
    path = Path(setup_path) if setup_path else example_setup_path()
    loaded = load_setup(path)
    if loaded.setup is None:
        raise PlatformRunError("The setup file could not be read: " + "; ".join(p.text for p in loaded.problems[:2]))
    layout, settings = build_inputs(loaded.setup, loaded.base_dir)
    return loaded.setup, layout, settings


def run_platform(setup_path: Path | str | None = None, run_id: str = "platform", strategy: str = "adaptive") -> PlatformRun:
    """One platform run: the whole run window of the setup, planned and executed trial by trial, faults from the setup. Its record carries the platform section the dashboard's two platform tabs display."""
    path = Path(setup_path) if setup_path else example_setup_path()
    loaded = load_setup(path)
    setup, layout, settings = load_inputs(path)
    run = run_setup(setup, layout, settings, run_id, strategy)
    run.record.platform = platform_info(run, loaded.base_dir)
    run.record.about = about_for(run, run.record.platform)
    return run


def run_setup(setup: dict, layout: dict, settings, run_id: str = "platform", strategy: str = "adaptive") -> PlatformRun:
    """The same for a setup, layout and settings already in memory."""
    if strategy == "adaptive":
        engine = AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine, settings.run.random_seed)
    elif strategy == "fixed_list":
        capacity = int(settings.run.duration_hours * 60 // settings.cell.minutes_per_trial)
        engine = FixedListStrategy(settings.design_space, max(capacity, settings.comparison.trials_per_campaign), settings.run.random_seed)
    else:
        raise PlatformRunError(f"Unknown strategy '{strategy}': use 'adaptive' or 'fixed_list'.")
    return PlatformSimulation(settings, setup, layout, VirtualLab(settings), engine, run_id, PythonStandInExecutor()).run_platform()


def save_platform_run(run: PlatformRun, folder: Path | str = PLATFORM_FOLDER) -> Path:
    """Write the run record (the same file the dashboard reads), every trial's plan and executed timeline, the layout and an index that says what is where."""
    folder = Path(folder)
    for sub in ("plans", "executed"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    record_path = run_store.save(run.record, folder)
    story = client_story.build(json.loads(record_path.read_text(encoding="utf-8")), run.setup)             # the run told as results for the Results page, worked out here so the page calculates nothing
    (folder / client_story.STORY_FILE).write_text(json.dumps(story, indent=1) + "\n", encoding="utf-8")
    for plan, executed in zip(run.plans, run.executed):
        (folder / "plans" / f"{plan['plan_id']}.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
        (folder / "executed" / f"{executed['executed_id']}.json").write_text(json.dumps(executed, indent=1) + "\n", encoding="utf-8")
    (folder / "layout.json").write_text(json.dumps(run.layout, indent=1) + "\n", encoding="utf-8")
    status = weakest(run.setup["project"]["data_status"], run.layout.get("data_status", "illustrative"))
    index = {"format_version": 1, "label": f"{status.upper()} platform run: the plans and executed timelines of every trial of one simulated run", "data_status": status, "run_id": run.record.meta.run_id,
             "executor": run.executed[0]["executor"] if run.executed else None, "record_file": record_path.name, "layout_file": "layout.json",
             "trials": [{"trial": e["trial"], "plan_file": f"plans/{e['plan_id']}.json", "executed_file": f"executed/{e['executed_id']}.json", "outcome": e["outcome"], "verdict": e["result"]["verdict"],
                         "fault": e["faults"][0]["cause"] if e["faults"] else None} for e in run.executed]}
    (folder / "platform_index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return record_path


def build_replay(run: PlatformRun, folder: Path | str = PLATFORM_FOLDER) -> Path:
    """The 3D replay of every trial of a run, as one self-contained HTML file next to the saved run."""
    return build_viewer(run.layout, run.executed, Path(folder) / "replay.html", "Robot cell: 3D replay of a platform run")


def main(argv: list[str]) -> int:
    """python -m cellpoc.platform_runner [a saved setup file] [--out folder]: with no file it uses the example setup. Everything is written into runs/platform, or into the folder named after --out (the setup app's
    'Run this setup' uses runs/setup_run). A setup that cannot be simulated is refused in plain words (exit code 1). The last two lines printed are the run's headline and its attempts."""
    out = PLATFORM_FOLDER
    if "--out" in argv:
        at = argv.index("--out")
        if at + 1 >= len(argv):
            print("Cannot run: --out needs a folder name after it.")
            return 1
        out = Path(argv[at + 1]).resolve()
        argv = argv[:at] + argv[at + 2:]
    source = argv[0] if argv else None
    print(f"Running the ILLUSTRATIVE platform simulation (made-up values, not a prediction about real tablets) on {Path(source).name if source else 'the example setup'} (a few seconds)...", flush=True)
    try:
        run = run_platform(source)
    except PlatformRunError as exc:
        print(f"Cannot run: {exc}")
        return 1
    print(f"Saved: {save_platform_run(run, out)}")
    print(f"3D replay: {build_replay(run, out)}")
    reports = write_reports(out)
    print(f"Report files: {reports.folder} ({len(reports.files)} files)")
    for note in reports.notes:
        print(note)
    print(run.record.summary.headline)
    print(run.record.summary.attempts_text)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
