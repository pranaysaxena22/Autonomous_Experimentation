"""Health check for the launchers that start a dashboard: does the dashboard they start really answer THIS computer only, looked at where it matters (the addresses the computer is really listening on), not in the wording of a file?

In plain words it checks that: the real launcher run_platform.bat, run for real in both variants (the platform run, and "connected", the loop connected; each builds its run and starts the dashboard), leaves a dashboard listening on 127.0.0.1 and on no other address, and a connection through the
computer's other network address is refused; the command the launcher uses to start the dashboard (one command, shared by the 8503 and the 8505 variants) carries the localhost flag; a self-test takes that very command with the flag
removed, starts it, and sees it listening on every address (0.0.0.0) and accepting a connection from the computer's other address, so the check can fail and the flag is what makes the difference; and every other launcher that starts a
dashboard is listed with what it does (run.bat's dashboard on 8501 is the one that still listens on every address, as the README records). The servers it starts are stopped again, whole process trees, and nothing is left running.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

PLATFORM_BAT = ROOT / "run_platform.bat"
PORT_REAL, PORT_FLAGLESS, PORT_CONNECTED = 8594, 8593, 8592


def listening_on(port: int) -> list[str]:
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    return sorted({cols[1] for line in out.splitlines() if "LISTENING" in line for cols in [line.split()] if len(cols) >= 4 and cols[1].endswith(f":{port}")})


def kill_tree(proc: subprocess.Popen) -> None:
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_until_up(port: int, seconds: int = 180) -> bool:
    for _ in range(seconds):
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2).read().strip() == b"ok":
                return True
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return False


def look(port: int) -> tuple[list[str], bool]:
    """(the addresses the computer is listening on for this port, whether the computer's other network address could connect)."""
    listening = []
    for _ in range(20):
        listening = listening_on(port)
        if listening:
            break
        time.sleep(1)
    lan = socket.gethostbyname(socket.gethostname())
    reachable = False
    if not lan.startswith("127."):
        try:
            socket.create_connection((lan, port), timeout=3).close()
            reachable = True
        except OSError:
            reachable = False
    return listening, reachable


def streamlit_commands(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if "-m streamlit run" in line and not line.strip().lower().startswith("rem")]


def main() -> int:
    cl = Checklist("LAUNCHERS: the dashboard run_platform.bat starts answers this computer only (looked at on the real listening addresses)")
    before = project_files()
    text = PLATFORM_BAT.read_text(encoding="utf-8")
    commands = streamlit_commands(text)
    cl.record(len(commands) == 1 and "--server.address localhost" in commands[0] and "%PORT%" in commands[0],
              "run_platform.bat starts the dashboard with ONE command, shared by the 8503 and the 8505 variants, and it carries --server.address localhost", commands[0][:110] if commands else "no command found")
    cl.record("8503" in text and "8505" in text and "CELLPOC_PORT" in text, "The launcher still uses 8503 (the platform run) and 8505 (the connected loop), and lets the health check choose another port")

    # the real launcher, run for real on another port
    env = dict(os.environ, CELLPOC_PORT=str(PORT_REAL))
    proc = subprocess.Popen(["cmd", "/c", str(PLATFORM_BAT)], cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = wait_until_up(PORT_REAL)
        only_here, reachable = look(PORT_REAL) if up else ([], False)
        cl.record(up and bool(only_here) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in only_here) and not reachable,
                  "Run for real, run_platform.bat leaves a dashboard listening on this computer only: 127.0.0.1 and no other address, and the computer's other network address cannot connect to it", f"listening on {only_here}; up: {up}")
    finally:
        kill_tree(proc)

    # the connected variant (the loop connected), run for real too: it builds the connected run first, then starts the same dashboard command
    env = dict(os.environ, CELLPOC_PORT=str(PORT_CONNECTED))
    proc = subprocess.Popen(["cmd", "/c", str(PLATFORM_BAT), "connected"], cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = wait_until_up(PORT_CONNECTED, 400)
        only_here, reachable = look(PORT_CONNECTED) if up else ([], False)
        cl.record(up and bool(only_here) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in only_here) and not reachable,
                  "Run for real, 'run_platform.bat connected' (the loop connected) also leaves its dashboard listening on this computer only, and the other network address cannot connect", f"listening on {only_here}; up: {up}")
    finally:
        kill_tree(proc)

    # the self-test: the very same command, with the flag taken out
    command = commands[0].replace("%PORT%", str(PORT_FLAGLESS)).replace("--server.address localhost", "").replace('".venv\\Scripts\\python.exe"', str(ROOT / ".venv" / "Scripts" / "python.exe"))
    args = [a for a in command.split() if a]
    flagless = subprocess.Popen(args + ["--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=ROOT, env=dict(os.environ, CELLPOC_RECORD=str(ROOT / "runs" / "platform")),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = wait_until_up(PORT_FLAGLESS, 60)
        everywhere, reachable = look(PORT_FLAGLESS) if up else ([], False)
        cl.record(up and any(a.startswith(("0.0.0.0:", "[::]:")) for a in everywhere),
                  "Self-test: the same command with the flag taken out is seen listening on every address (so this check can fail, and the flag is what makes the difference)", f"listening on {everywhere}" + ("; the computer's other address could connect" if reachable else ""))
        cl.record(up and (reachable or socket.gethostbyname(socket.gethostname()).startswith("127.")), "...and, without the flag, a connection through the computer's other network address succeeds (the exposure this guards against is real)")
    finally:
        kill_tree(flagless)
    time.sleep(2)
    cl.record(not listening_on(PORT_REAL) and not listening_on(PORT_FLAGLESS) and not listening_on(PORT_CONNECTED), "The servers this check started are stopped again: nothing is left listening on its ports")

    # an honest list of what each launcher that starts a dashboard does
    launchers = {}
    for bat in sorted(ROOT.glob("*.bat")):
        t = bat.read_text(encoding="utf-8", errors="replace")
        for cmd in streamlit_commands(t):
            launchers.setdefault(bat.name, []).append("this computer only" if "--server.address localhost" in cmd else "EVERY network address")
    expected = {"run.bat": {"this computer only", "EVERY network address"}, "run_platform.bat": {"this computer only"}, "run_app.bat": {"this computer only"}}
    cl.record(set(launchers) == set(expected) and set(launchers["run_platform.bat"]) == {"this computer only"} and set(launchers["run_app.bat"]) == {"this computer only"} and "EVERY network address" in set(launchers["run.bat"]),
              "Every launcher that starts a dashboard is accounted for: run_platform.bat and run_app.bat (the unified app) answer this computer only; run.bat's dashboard (8501) still listens on every address, as the README records, and run.bat's setup app answers this computer only", "; ".join(f"{k}: {sorted(set(v))}" for k, v in launchers.items()))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project outside the folders for generated output", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
