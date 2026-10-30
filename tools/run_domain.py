r"""The applicability-domain warning (Stage 3b-2): is a recipe far from the data? Writes one report per table and a summary into runs/modelling/ (not in git).

Run:  .venv\Scripts\python.exe tools\run_domain.py        (or double-click run_domain.bat)
It reads the saved answers of the full Stage 3a comparison (runs/modelling/cache_full/): if they are not there it first runs that comparison (about 10 minutes; double-click
run_full_validation.bat). It never refits a model and never evaluates a skipped result.
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
from cellpoc.modelling.domain_report import build_report, build_summary  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
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
        table = build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name)
        validation = run_validation(table, FULL, n_jobs=args.jobs, cache=cache)
        validations.append(validation)
        path = out / f"domain_{name}.md"
        path.write_bytes(build_report(validation).encode("utf-8"))
        print(f"  wrote {path.relative_to(ROOT)}", flush=True)
    summary = out / "domain_summary.md"
    summary.write_bytes(build_summary(validations).encode("utf-8"))
    print(f"\n  wrote {summary.relative_to(ROOT)}\n\nFinished in {time.time() - started:.0f} s. Open the files in runs\\modelling\\. Start with domain_summary.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())