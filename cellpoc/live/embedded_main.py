"""python -m cellpoc.live.embedded_main --port N: the live run's server, as the unified app starts it (see docs/stage_c_design_note.md).

The same LiveServer as `python -m cellpoc.live`, but on the port it is given and WITHOUT opening a browser window. The address it listens on is not a setting here: LiveServer binds the constant HOST (127.0.0.1) and nothing
in this file can change that. It runs until it is stopped. The app that started it (cellpoc.live_supervisor) watches and stops it.
"""
from __future__ import annotations

import sys

from ..connected import ConnectedError
from ..platform_runner import PlatformRunError
from . import HOST, LiveServer


TESTS_ONLY = "--tests-autostart"        # never part of the command the app runs; the checks add it to let the live page press its own Start button when opened with ?autostart=1
USAGE = "Usage: python -m cellpoc.live.embedded_main --port N [--connected SCENARIO]   (N from 1024 to 65535)"


def parse(argv: list[str]) -> tuple[int, str | None, bool] | None:
    """(port, connected scenario or None, tests-only autostart) from `--port N [--connected NAME] [--tests-autostart]`, or None if anything else is given."""
    from ..connected import SCENARIO_NAMES
    rest = list(argv)
    tests = rest[-1:] == [TESTS_ONLY]
    if tests:
        rest = rest[:-1]
    if len(rest) not in (2, 4) or rest[0] != "--port" or not rest[1].isdigit() or not 1024 <= int(rest[1]) <= 65535:
        return None
    connected = None
    if len(rest) == 4:
        if rest[2] != "--connected" or rest[3] not in SCENARIO_NAMES:
            return None
        connected = rest[3]
    return int(rest[1]), connected, tests


def main(argv: list[str]) -> int:
    parsed = parse(argv)
    if parsed is None:
        print(USAGE)
        return 2
    port, connected, tests = parsed
    if connected:
        print(f"The loop is connected: the experiment table, Stage 3's conclusions and the adopted engine choose the recipes ('{connected}' scenario, synthetic). Preparing (about a minute the first time)...", flush=True)
    try:
        server = LiveServer(port, None, connected=connected, autostart_hook=tests)
    except (ConnectedError, PlatformRunError) as exc:
        print(f"Cannot start: {exc}")
        return 1
    except OSError:
        print(f"The live view cannot start: port {port} is already in use.")
        return 1
    print(f"The ILLUSTRATIVE live run (a simulation with made-up values) is ready at http://{HOST}:{server.port}/ (this computer only).", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
