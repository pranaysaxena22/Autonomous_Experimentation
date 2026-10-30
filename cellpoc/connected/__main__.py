"""python -m cellpoc.connected [scenario]: runs the connected loop once (the default scenario is baseline) and writes the run, its 3D replay and its report files into runs/connected_run. The dashboard opens on it with run_platform.bat connected."""
from __future__ import annotations

import sys

from . import SCENARIO_NAMES, ConnectedError, run_connected, save_connected_run
from ..platform_runner import PlatformRunError


def main(argv: list[str]) -> int:
    scenario = argv[0] if argv else "baseline"
    print(f"Connecting the loop on the '{scenario}' scenario (synthetic): data, then models, then the engine, then the cell.", flush=True)
    try:
        connected = run_connected(scenario)
    except (ConnectedError, PlatformRunError) as exc:
        print(f"Cannot run: {exc}")
        print(f"Scenarios: {', '.join(SCENARIO_NAMES)}")
        return 1
    record = save_connected_run(connected)
    print(f"Saved: {record}")
    print(connected.run.record.summary.headline)
    print(connected.run.record.summary.attempts_text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
