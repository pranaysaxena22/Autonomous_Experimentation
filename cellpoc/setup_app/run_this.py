"""'Run this setup' (part of screen 10): saves the setup, then simulates a run of the SAVED file, and offers to open the dashboard on it or to watch it live.

This part of the app runs and shows nothing of its own. It starts the platform's own programs as separate processes (`python -m cellpoc.platform_runner`, the dashboard, `python -m cellpoc.live`), exactly as double-clicking
run_platform.bat or run_live.bat does, and shows what they print. It imports only the setup part and writes no file (the programs it starts write into runs/setup_run, which is generated output). Everything it starts listens on THIS computer only
(the dashboard is started with --server.address localhost; the live page binds 127.0.0.1), and the pages it links to are on this computer: the health checks test both by looking at the real listening addresses, not at the wording of this file.
"""
from __future__ import annotations

import os
import subprocess
import sys

import streamlit as st

from cellpoc.setup import PROJECT_ROOT

RUN_FOLDER = "runs/setup_run"                 # generated output, not saved in git
DASHBOARD_PORT = 8506                         # the platform dashboard is 8503 and the connected one 8505; this one is for the setup run
LIVE_PORT = 8504
RUN_SECONDS = 600


def local_address(port: int) -> str:
    """The address of a page served on this computer. It is the plain address of this computer (localhost), never another host: the health check allows only this one address form in the app's code."""
    return f"http://localhost:{port}"


def _own_window() -> int:
    """A server started from here gets its own black window (as run.bat does), so it can be closed like any other."""
    return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def simulate(setup_file: str) -> tuple[bool, list[str]]:
    """Run the saved setup file through the platform simulation. Returns (it worked, the lines the program printed)."""
    try:
        done = subprocess.run([sys.executable, "-B", "-m", "cellpoc.platform_runner", setup_file, "--out", RUN_FOLDER], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=RUN_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return False, ["The simulation could not be started or took too long."]
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done.returncode == 0, lines


def dashboard_command(port: int = DASHBOARD_PORT) -> list[str]:
    """The command that starts the dashboard. `--server.address localhost` makes it answer this computer only; without it the dashboard listens on every network address of the computer and other machines on the network could open it
    (the setup app itself is started the same way by run.bat setup)."""
    return [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port), "--server.address", "localhost", "--server.headless", "true", "--browser.gatherUsageStats", "false"]


def start_dashboard() -> None:
    env = dict(os.environ, CELLPOC_RECORD=str(PROJECT_ROOT / RUN_FOLDER))
    subprocess.Popen(dashboard_command(), cwd=PROJECT_ROOT, env=env, creationflags=_own_window())


def start_live(setup_file: str) -> None:
    subprocess.Popen([sys.executable, "-B", "-m", "cellpoc.live", setup_file], cwd=PROJECT_ROOT, creationflags=_own_window())


def show_result() -> None:
    """What the last run said, with the two ways to look at it. Nothing is worked out here: the lines are the program's own."""
    result = st.session_state.get("run_result")
    if not result:
        return
    client = bool(st.session_state.get("client_view"))       # the unified app's client view leaves out the technical detail
    if not result["ok"]:
        refused = [line for line in result["lines"] if line.startswith("Cannot run:")]
        st.error(refused[0] if refused else ("The simulation stopped unexpectedly, so there is no run to show. Please ask the demo team." if client else "The simulation stopped unexpectedly, so there is no run to show. Double-click check_cellsim.bat to see what is wrong."))
        return
    st.success(f"Finished: {result['lines'][-2]}. {result['lines'][-1]}." if len(result["lines"]) >= 2 else "Finished.")
    st.caption("Simulated from your saved setup. Everything is illustrative." if client else f"Simulated from the saved file {result['file']}. The run, its plans, its 3D replay and its report files are in {RUN_FOLDER}. Everything is illustrative.")
    if st.session_state.get("inside_unified_app"):             # inside the unified app: no separate windows; the app's own Live run page lists saved setups
        if client:
            st.markdown("**To watch this setup run live:** open the Live run page, press Start the live demo, and choose your saved setup in the list at the top of the live page.")
        else:
            st.markdown("**To watch this setup run live:** open the Live run page, press Start the live view, and choose your saved setup in the list at the top of the live page.")
        st.page_link("cellpoc/shell/pages/live_run.py", label="Open the Live run page", icon=":material/play_circle:")
        if not client:
            st.caption("To see this setup's run in every page of the app, drag the saved setup file (in the setups folder) onto run_app.bat.")
        return
    left, right = st.columns(2)
    with left:
        if st.button("Open the dashboard on this run", key="open_dashboard"):
            start_dashboard()
            st.session_state["dashboard_started"] = True
        if st.session_state.get("dashboard_started"):
            st.link_button(f"Open {local_address(DASHBOARD_PORT)}", local_address(DASHBOARD_PORT))
            st.caption("A new black window runs the dashboard: close it to stop it. If the page is not ready, wait a few seconds and refresh.")
    with right:
        if st.button("Watch this setup run live", key="watch_live"):
            start_live(result["file"])
            st.session_state["live_started"] = True
        if st.session_state.get("live_started"):
            st.link_button(f"Open {local_address(LIVE_PORT)}", local_address(LIVE_PORT))
            st.caption("A new black window runs it: close it to stop it. If a live page is already open in another black window, close that one first.")


def intro(can_run: bool, reasons: list[str]) -> None:
    st.markdown("#### Run this setup (a simulation)")
    st.caption("Saves the setup, then simulates a run of the saved file: every recipe is planned, run through the cell and measured in the stand-in lab, with the ingredient ranges, targets, step times, calendar and faults you set. "
               "It takes a few seconds. Everything is illustrative.")
    if not can_run:
        for reason in reasons:
            st.warning(reason)
