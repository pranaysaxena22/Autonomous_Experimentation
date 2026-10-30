"""python -m cellpoc.reports [record folder or file] [output folder]: writes the report files for a run record (default: the platform run if there is one, otherwise the proof-of-concept demo run)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import ReportError, write_reports

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    if argv:
        source = Path(argv[0])
    else:
        source = ROOT / "runs" / "platform" if (ROOT / "runs" / "platform" / "record.json").exists() else ROOT / "runs" / "demo"
    try:
        result = write_reports(source, argv[1] if len(argv) > 1 else None)
    except ReportError as exc:
        print(exc)
        return 1
    print(f"Wrote {len(result.files)} files to {result.folder}:")
    for f in result.files:
        print(f"  {f.name}")
    for note in result.notes:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
