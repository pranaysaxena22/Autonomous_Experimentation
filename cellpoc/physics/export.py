"""Writes the cell scene as a MuJoCo file so it can be opened in MuJoCo's own viewer: `python -m cellpoc.physics.export` (then view_physics.bat). Defaults to the platform run's layout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scene import build_mjcf

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the cell as a MuJoCo scene file.")
    parser.add_argument("--layout", default=str(ROOT / "runs" / "platform" / "layout.json"))
    parser.add_argument("--out", default=str(ROOT / "runs" / "physics" / "cell.xml"))
    args = parser.parse_args()
    layout = json.loads(Path(args.layout).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_mjcf(layout, with_vial=True), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
