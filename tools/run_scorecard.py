r"""The model scorecard (Stage 3b-4): one stand-alone web page per table plus an index, written into runs/scorecard/ (not in git).

Run:  .venv\Scripts\python.exe tools\run_scorecard.py        (or double-click run_scorecard.bat, which also opens the index)
It reads the saved answers of the full Stage 3a comparison (runs/modelling/cache_full/): if they are not there it first runs that comparison (about 10 minutes; double-click
run_full_validation.bat). It never refits a model, never needs the internet and never evaluates a result that was not carried. The replay is shown for the synthetic mocks only.
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
from cellpoc.modelling.replay import movement, replay_table, targets_from_setup  # noqa: E402
from cellpoc.modelling.scorecard import build_card  # noqa: E402
from cellpoc.modelling.scorecard_html import render_index, render_table  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    out = ROOT / "runs" / "scorecard"
    cache = ROOT / "runs" / "modelling" / "cache_full"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    validations = []
    for name in NAMES:
        if not fixture_available(name):
            print(f"  skipped {name}: its data files are not on this computer")
            continue
        validations.append(run_validation(build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name), FULL, n_jobs=args.jobs, cache=cache))
    decisions = decide_all(validations)
    real = next((v for v in validations if v.table.name == "batch_production"), None)
    real_share = None
    if real is not None:
        first = next(r for r, t in real.table.responses.items() if t.usable)
        real_share = movement(real.table, first).supplier        # the same measure that is shown for the mocks, on the real data
    cards, files = [], {}
    for v in validations:
        name = v.table.name
        replay = replay_table(v, decisions, targets_from_setup(fixture_setup(name))) if name in MOCK_FILES else None
        card = build_card(v, decisions, replay, real_share)
        cards.append(card)
        files[name] = f"scorecard_{name}.html"
        (out / files[name]).write_bytes(render_table(card).encode("utf-8"))
        print(f"  wrote {(out / files[name]).relative_to(ROOT)}", flush=True)
    index = out / "index.html"
    index.write_bytes(render_index(cards, files).encode("utf-8"))
    print(f"\n  wrote {index.relative_to(ROOT)}\n\nFinished in {time.time() - started:.0f} s. Open runs\\scorecard\\index.html in any web browser (no internet needed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
