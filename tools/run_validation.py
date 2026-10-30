r"""Fits every model on every fold of the test tables and writes a plain model-comparison report for each, plus one summary, into runs/modelling/ (not in git).

Run:  .venv\Scripts\python.exe tools\run_validation.py --mode fast          (or double-click run_fast_validation.bat)
      .venv\Scripts\python.exe tools\run_validation.py --mode full          (or double-click run_full_validation.bat: the full comparison, Stage 3a-4)
Several folds run at the same time (--jobs); the answers do not depend on how many. Every fold's answer is saved as soon as it is done (runs/modelling/cache_<mode>/),
so a run that is stopped can be started again and carries on where it stopped; --fresh ignores the saved answers. The real public datasets are included when their
files are on this computer.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import build_table_for_setup  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FAST, FULL  # noqa: E402
from cellpoc.modelling.report import build_report  # noqa: E402
from cellpoc.modelling.summary import build_summary  # noqa: E402
from cellpoc.modelling.validate import build_with_flags_removed, run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402


def clock(seconds: float) -> str:
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest:02d} s" if minutes else f"{rest} s"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fast", "full"], default="fast")
    parser.add_argument("--tables", nargs="*", default=None, help="which tables (default: all that are on this computer)")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--fresh", action="store_true", help="ignore and replace the saved fold answers")
    args = parser.parse_args()
    settings = FAST if args.mode == "fast" else FULL
    out = ROOT / "runs" / "modelling"
    cache = out / f"cache_{args.mode}"
    if args.fresh and cache.exists():
        shutil.rmtree(cache)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    validations = []
    for name in args.tables or NAMES:
        if not fixture_available(name):
            print(f"  skipped {name}: its data files are not on this computer")
            continue
        table = build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name)
        begun = time.time()
        last = [0.0]

        def progress(done: int, total: int, label: str = name) -> None:
            if time.time() - last[0] > 20 or done == total:
                last[0] = time.time()
                print(f"    {label}: {done} of {total} fold answers ready ({clock(time.time() - begun)})", flush=True)

        print(f"  {name}: fitting every model on every fold ({args.jobs} at a time) ...", flush=True)
        validation = run_validation(table, settings, n_jobs=args.jobs, progress=progress, cache=cache)
        alt = None
        without = build_with_flags_removed(table)
        if without is not None:
            print(f"  {name}: again without the flagged rows ...", flush=True)
            alt = run_validation(without, settings, n_jobs=args.jobs, progress=lambda d, t: progress(d, t, name + " (without flagged rows)"), cache=cache)
        validations.append(validation)
        path = out / f"model_report_{args.mode}_{name}.md"
        path.write_bytes(build_report(validation, alt).encode("utf-8"))
        problems = sorted({e for run in validation.runs.values() for f in run.folds for e in f.errors})
        print(f"    wrote {path.relative_to(ROOT)} in {clock(time.time() - begun)}" + (f"; {len(problems)} kinds of model failure (see the report)" if problems else ""), flush=True)
        for p in problems[:5]:
            print("      technical detail:", p)
    summary = out / f"model_summary_{args.mode}.md"
    summary.write_bytes(build_summary(validations, args.mode).encode("utf-8"))
    print(f"\n  wrote {summary.relative_to(ROOT)}")
    print(f"\nFinished in {clock(time.time() - started)}. Open the files in runs\\modelling\\ (they open in VS Code or any text editor). Start with {summary.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())