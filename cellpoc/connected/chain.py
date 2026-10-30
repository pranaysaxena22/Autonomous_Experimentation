"""The data-to-engine chain of the connected loop: a client's experiment file, read and cleaned (Stage 2), turned into a modelling table and judged by the grouped validation (Stage 3), turned into the decision engine's
brief (Stage 4-1), with the engine's own history read from that same file. Every step is the existing step, unchanged; this only runs them in order for one setup and keeps what they produce.

The file is the development lab's synthetic history for a scenario (the world the engine was developed against, labelled SYNTHETIC). A finished brief is kept next to it and reused while the file is unchanged, because
fitting the models for the first time takes minutes (the fitted answers of the earlier runs are reused too, so after `make_dev_scenarios.bat` it takes seconds). Nothing here sees the lab's hidden truth.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..briefing import build_brief
from ..contracts import BRIEF_VERSION, EngineBrief
from ..modelling import build_table_for_setup
from ..modelling.carry import decide_all
from ..modelling.fixtures import synthetic_file_setup
from ..modelling.models import FULL
from ..modelling.validate import run_validation
from ..setup import PROJECT_ROOT
from ..virtual_lab.dev_lab import HISTORY_EXPERIMENTS, HISTORY_SEEDS, SCENARIOS, DevLab

FOLDER = PROJECT_ROOT / "runs" / "connected"
FITTED_ANSWERS = PROJECT_ROOT / "runs" / "devlab" / "cache_full"      # where make_dev_scenarios.bat keeps the fitted answers: reused so that nothing is fitted twice
SCENARIO_NAMES = tuple(SCENARIOS)
SOURCE = "cellpoc/virtual_lab/dev_lab.py"


class ConnectedError(Exception):
    """The loop cannot be connected for this request. The message says what to do, in plain words."""


@dataclass
class Chain:
    scenario: str
    setup: dict                  # the setup for this study: the example setup, with the history file as the experiment table and the modelling section the Stage 3 fixtures use
    file: Path
    history: pd.DataFrame        # the experiment table as it is read from the file, with the names the engine uses
    brief: EngineBrief
    brief_reused: bool
    steps: list[str] = field(default_factory=list)


def history_text(scenario: str) -> str:
    """The scenario's history as the CSV text make_dev_scenarios.py writes (the same generator, the same fixed fresh seed, the same layout)."""
    frame = DevLab(SCENARIOS[scenario], HISTORY_SEEDS[scenario]).history(HISTORY_EXPERIMENTS)
    return frame.to_csv(index=False, lineterminator="\n")


def study_setup(scenario: str) -> dict:
    """The setup of the connected study: the bundled example setup (its equipment, calendar, scripted faults and targets), the history file as the experiment table, and the Stage 3 modelling section."""
    relative = f"runs/connected/dev_{scenario}.csv"
    setup = synthetic_file_setup(relative, SOURCE)
    setup["project"] = {"name": f"Connected loop, {scenario.replace('_', ' ')} (synthetic)", "data_status": "synthetic"}
    return setup


def read_history(path: Path) -> pd.DataFrame:
    """The experiment table the engine learns from: the file itself, read back, with the column names the modelling table uses."""
    return pd.read_csv(path).rename(columns={"compression_force_kN": "compression_force_kn", "hardness": "hardness_kp"})


def _say(progress, text: str) -> None:
    if progress:
        progress(text)


def prepare(scenario: str = "baseline", jobs: int | None = None, progress=print, fitted_answers: Path = FITTED_ANSWERS) -> Chain:
    """Run the chain for a scenario: write (if needed) and read its history, judge it, build the engine's brief. Returns everything the run needs."""
    if scenario not in SCENARIOS:
        raise ConnectedError(f"There is no scenario called '{scenario}'. Choose one of: {', '.join(SCENARIO_NAMES)}.")
    FOLDER.mkdir(parents=True, exist_ok=True)
    file = FOLDER / f"dev_{scenario}.csv"
    text = history_text(scenario)
    if not file.exists() or file.read_bytes().replace(b"\r\n", b"\n") != text.encode("utf-8"):
        file.write_bytes(text.encode("utf-8"))
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    setup = study_setup(scenario)
    history = read_history(file)
    steps = [f"Experiment table: {len(history)} rows read from {file.relative_to(PROJECT_ROOT).as_posix()} (SYNTHETIC development-lab history)."]
    _say(progress, steps[-1])
    kept, stamp = FOLDER / f"brief_{scenario}.json", FOLDER / f"brief_{scenario}.sha256"
    if kept.exists() and stamp.exists() and stamp.read_text(encoding="utf-8").strip() == f"{digest} {BRIEF_VERSION}":
        brief, reused = EngineBrief.from_json(kept.read_text(encoding="utf-8")), True
        steps.append("The Stage 3 conclusions for this file were already worked out and the file has not changed, so they are reused.")
    else:
        _say(progress, "Judging the models on this file for the first time (grouped validation, calibration, the carry rule). This can take a few minutes once; it is kept for next time.")
        table = build_table_for_setup(setup, None, PROJECT_ROOT, f"dev_{scenario}")
        if not table.ok:
            raise ConnectedError("The experiment table could not be turned into a modelling table: " + "; ".join(f.text for f in table.findings if f.level == "error")[:300])
        validation = run_validation(table, FULL, n_jobs=jobs or max(1, (os.cpu_count() or 2) - 2), cache=fitted_answers)
        brief = build_brief(validation, decide_all([validation]))
        kept.write_bytes(brief.to_json().encode("utf-8"))
        stamp.write_text(f"{digest} {BRIEF_VERSION}\n", encoding="utf-8")
        reused = False
        steps.append("Stage 3 judged the models on this file and the carry rule decided which results the engine may use.")
    _say(progress, steps[-1])
    steps.append("Engine brief: " + "; ".join(f"{t.label} {t.status.replace('_', ' ')}" + (f" ({t.model_label})" if t.model_label else "") for t in brief.targets) + ".")
    _say(progress, steps[-1])
    return Chain(scenario, setup, file, history, brief, reused, steps)
