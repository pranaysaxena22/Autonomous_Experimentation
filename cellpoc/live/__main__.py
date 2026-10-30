"""python -m cellpoc.live [setup file]: starts the live run's page on this computer (http://localhost:8504) and opens it in the browser. Stop it with Ctrl+C or by closing its window."""
from __future__ import annotations

import sys
import webbrowser

from ..connected import ConnectedError
from ..platform_runner import PlatformRunError
from . import PORT, LiveServer


def main(argv: list[str]) -> int:
    connected = None
    opens = "/"
    if argv and argv[0] == "console":                           # run_console.bat: open the operations console (a welcome, a tour and three views) instead of the plain live page
        opens, argv = "/console", argv[1:]
    if argv and argv[0] == "connected":                       # run_live.bat connected [scenario]: the loop connected (data, models, the adopted engine, the cell)
        connected = argv[1] if len(argv) > 1 else "baseline"
        argv = []
        print(f"The loop is connected: the experiment table, Stage 3's conclusions and the adopted engine choose the recipes ('{connected}' scenario, synthetic). Preparing...", flush=True)
    try:
        server = LiveServer(PORT, argv[0] if argv else None, connected=connected)
    except ConnectedError as exc:
        print(f"Cannot start: {exc}")
        return 1
    except PlatformRunError as exc:
        print(f"Cannot start: {exc}")
        return 1
    except OSError:
        print(f"The live page cannot start: port {PORT} is already in use. It is probably already running in another black window. Close that window, or open http://localhost:{PORT} in your browser.")
        return 1
    address = f"http://localhost:{server.port}"
    opens_at = address + opens
    print(f"The ILLUSTRATIVE live run (a simulation with made-up values) is ready at {opens_at} (this computer only). Press play on the page. Stop it with Ctrl+C or by closing this window.", flush=True)
    webbrowser.open(opens_at)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
