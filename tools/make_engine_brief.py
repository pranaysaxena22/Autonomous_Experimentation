r"""The decision engine's brief (Stage 4-1): what Stage 3 concluded about each result, one JSON file (for the engine) and one plain-words page (for you) per table, in runs/brief/ (not in git).

Run:  .venv\Scripts\python.exe tools\make_engine_brief.py        (or double-click make_engine_brief.bat)
It reads the saved answers of the full Stage 3a comparison (runs/modelling/cache_full/): if they are not there it first runs that comparison (about 10 minutes; double-click
run_full_validation.bat). It never refits a model, never touches a lab and never needs the internet.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.briefing import build_brief, render  # noqa: E402
from cellpoc.modelling import build_table_for_setup  # noqa: E402
from cellpoc.modelling.carry import decide_all  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    out = ROOT / "runs" / "brief"
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
    summary = ["# The decision engine's briefs: summary", "",
               "One brief per table. The engine may use only the results marked CARRIED, and only for the table they were judged on. Every table is labelled with its data status.", "",
               "| Table | Data status | Carried (usable) | Exploratory (not used) | Not assessed |", "|---|---|---|---|---|"]
    for v in validations:
        brief = build_brief(v, decisions)
        (out / f"brief_{brief.table}.json").write_bytes(brief.to_json().encode("utf-8"))
        (out / f"brief_{brief.table}.md").write_bytes(render(brief).encode("utf-8"))
        by = {s: [t.label for t in brief.targets if t.status == s] for s in ("carried", "exploratory", "not_assessed")}
        tag = f" [{brief.table_tag}]" if brief.table_tag else ""
        summary.append(f"| {brief.table}{tag} | {brief.data_label} | {', '.join(by['carried']) or '-'} | {', '.join(by['exploratory']) or '-'} | {', '.join(by['not_assessed']) or '-'} |")
        print(f"  wrote runs\\brief\\brief_{brief.table}.json and .md", flush=True)
    summary += ["", "For the real batch data (REAL PUBLIC DATA, NOT CLIENT DATA) hardness and tensile strength are carried, but no client-specified target exists for them, so Stage 4 does not run the engine on them."]
    (out / "brief_summary.md").write_bytes(("\n".join(summary) + "\n").encode("utf-8"))
    print(f"\n  wrote runs\\brief\\brief_summary.md\n\nFinished in {time.time() - started:.0f} s. Open the .md files in runs\\brief\\. Start with brief_summary.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
