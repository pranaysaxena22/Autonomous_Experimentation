r"""The decision-usefulness replay (Stage 3b-3), on the SYNTHETIC mocks only. Writes one report per mock and a summary into runs/modelling/ (not in git).

Run:  .venv\Scripts\python.exe tools\run_replay.py        (or double-click run_replay.bat)
It reads the saved answers of the full Stage 3a comparison (runs/modelling/cache_full/): if they are not there it first runs that comparison (about 10 minutes; double-click
run_full_validation.bat). It never refits a model, never runs on real data and never invents a target: the targets are the ones in each mock's setup.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import build_table_for_setup  # noqa: E402
from cellpoc.modelling.carry import decide_all  # noqa: E402
from cellpoc.modelling.fixtures import MOCK_FILES, NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.replay import replay_table, targets_from_setup  # noqa: E402
from cellpoc.modelling.replay_report import build_report, build_summary  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    out = ROOT / "runs" / "modelling"
    cache = out / "cache_full"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    validations = []
    for name in NAMES:
        if not fixture_available(name):
            print(f"  skipped {name}: its data files are not on this computer")
            continue
        validations.append(run_validation(build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name), FULL, n_jobs=args.jobs, cache=cache))
    decisions = decide_all(validations)
    replays = {}
    for v in validations:
        name = v.table.name
        if name not in MOCK_FILES:                                   # only the synthetic mocks are ever replayed
            continue
        replays[name] = replay_table(v, decisions, targets_from_setup(fixture_setup(name)))
        path = out / f"replay_{name}.md"
        path.write_bytes(build_report(v, replays[name]).encode("utf-8"))
        print(f"  wrote {path.relative_to(ROOT)}", flush=True)
    summary = out / "replay_summary.md"
    summary.write_bytes(build_summary(validations, decisions, {n: r for n, r in replays.items() if r.targets}).encode("utf-8"))
    print(f"\n  wrote {summary.relative_to(ROOT)}\n\nFinished in {time.time() - started:.0f} s. Open the files in runs\\modelling\\. Start with replay_summary.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
