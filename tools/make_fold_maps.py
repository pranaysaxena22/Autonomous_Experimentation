r"""Writes a fold map for each test table into runs/modelling/ (not in git): how every table is divided into training and test rows.

Run:  .venv\Scripts\python.exe tools\make_fold_maps.py        (or double-click make_fold_maps.bat)
The two real public datasets are included when their files are on this computer.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import build_table_for_setup  # noqa: E402
from cellpoc.modelling.foldmap import build_fold_map  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402


def main() -> int:
    out = ROOT / "runs" / "modelling"
    out.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        if not fixture_available(name):
            print(f"  skipped {name}: its data files are not on this computer")
            continue
        table = build_table_for_setup(fixture_setup(name), None, PROJECT_ROOT, name)
        path = out / f"fold_map_{name}.md"
        path.write_bytes(build_fold_map(table).encode("utf-8"))
        print("  wrote", path.relative_to(ROOT))
    print("\nOpen the files in runs\\modelling\\ (they open in VS Code or any text editor).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
