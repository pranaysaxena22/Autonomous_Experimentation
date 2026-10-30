r"""Writes data quality reports.

  .venv\Scripts\python.exe tools\make_quality_report.py all [--out DIR]
      one report for each mock file (read with the bundled example setup) and, when data/public/ is on this computer, one for each real public dataset
  .venv\Scripts\python.exe tools\make_quality_report.py SETUP.yaml [--file data\mock\x.csv] [--out DIR]
      one report for one setup (optionally reading another file with it)

Reports go to runs\ingest\ by default (not saved in git). Reading only: nothing in the project is changed except the report files.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.ingest import report_for_setup, write_report  # noqa: E402
from cellpoc.setup import PROJECT_ROOT, example_setup_path  # noqa: E402

MOCKS = ["mock_formulation_small.csv", "mock_formulation_experiments.csv", "mock_formulation_hard.csv"]
FIXTURES = ROOT / "cellpoc" / "ingest" / "fixtures"
PUBLIC_NEEDED = {"literature_setup": ["formulation_literature/final Data All Exipients.csv"], "laboratory_setup": ["batch_production/Laboratory.csv"],
                 "process_setup": ["batch_production/Process.csv"],
                 "batch_production_joined_setup": ["batch_production/Laboratory.csv", "batch_production/Process.csv", "batch_production/Normalization.csv"]}


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_bytes().decode("utf-8"))


def make_all(out: Path) -> list[Path]:
    written = []
    example = load(example_setup_path())
    for name in MOCKS:
        setup = copy.deepcopy(example)
        setup["data"]["experiments_file"] = f"data/mock/{name}"
        _, text = report_for_setup(setup, None, PROJECT_ROOT)
        written.append(write_report(text, out / f"{Path(name).stem}_quality_report.md"))
    for stem, needed in PUBLIC_NEEDED.items():
        if all((ROOT / "data" / "public" / rel).exists() for rel in needed):
            _, text = report_for_setup(load(FIXTURES / f"{stem}.yaml"), None, PROJECT_ROOT)
            written.append(write_report(text, out / f"{stem.replace('_setup', '')}_quality_report.md"))
        else:
            print(f"skipped {stem}: the public data files are not on this computer (data/public/ is never in git)")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Write data quality reports.")
    parser.add_argument("target", help="'all', or the path of a setup (.yaml)")
    parser.add_argument("--file", help="read this file instead of the setup's experiments file")
    parser.add_argument("--out", default=str(ROOT / "runs" / "ingest"), help="folder for the reports")
    args = parser.parse_args()
    out = Path(args.out)
    if args.target == "all":
        written = make_all(out)
    else:
        setup = load(Path(args.target))
        if args.file:
            setup["data"]["experiments_file"] = args.file
        _, text = report_for_setup(setup, Path(args.target).resolve().parent, PROJECT_ROOT)
        written = [write_report(text, out / f"{Path(args.target).stem.replace('_setup', '')}_quality_report.md")]
    for path in written:
        print("wrote", path)
    print(f"\n{len(written)} report(s) written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
