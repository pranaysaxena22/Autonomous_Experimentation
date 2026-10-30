"""The Live run page of the unified app (Stage C): a status line, Start and Stop buttons, and the live view in a frame.

It only calls the live-run supervisor (cellpoc.live_supervisor, which starts, watches and stops the live program on this computer only) and draws what the supervisor reports. It starts nothing by itself:
visiting the page starts no program. The frame's address is the supervisor's constant loopback address, never anything typed in an address bar.
"""
from __future__ import annotations

import html

import streamlit as st

from cellpoc.dashboard import style as dashboard_style
from cellpoc.live_supervisor import SCENARIOS, shared
from cellpoc.shell import context, landing

LOOK = {"running": "", "starting": "", "not running": "ub-quiet", "stopped": "ub-warn", "refused": "ub-bad"}
# what the client view says in each state, in place of the technical status line
CLIENT_SAYS = {"not running": ("Ready", "Press Start to watch the cell work."), "starting": ("Starting", "Getting the cell ready..."),
               "stopped": ("Stopped", "The live demo has stopped. Press Start to run it again."), "refused": ("Not available", "The live demo could not start on this computer. Please ask the demo team.")}
FRAME_HEIGHT = 1800
EMBEDDED = "embedded=1"          # tells the live page it is inside the app, so it hides its own title band (a look only: it cannot start or change anything)
LIVE_PORTS = {8510: 8514, 8511: 8515}          # each app of this project gets its own live port, so both can run their live view at the same time (any other app port uses 8514)


def supervisor_for(record):
    """The supervisor of this app: its own live port, and the connected loop when this app was opened on a connected run (the record's run id is `connected-NAME` with NAME one of the four scenarios)."""
    scenario = record.meta.run_id.removeprefix("connected-") if record.meta.run_id.startswith("connected-") else None
    return shared(LIVE_PORTS.get(st.get_option("server.port"), 8514), scenario if scenario in SCENARIOS else None)


@st.fragment(run_every=3)
def panel(shown_running: bool, supervisor, developer: bool = True) -> None:
    """The status line (it refreshes by itself every few seconds), and the two buttons. The client view says the same in plain words and leaves out the technical lines."""
    status = supervisor.status()
    running = status.state == "running"
    if running != shown_running:                       # the live program started or ended without a click here (it exited, or was found on another address): redraw the whole page
        st.rerun()
    if developer:
        st.markdown(f'<div class="ub-card {LOOK.get(status.state, "")}"><h4>{html.escape(status.state.capitalize())}</h4><p>{html.escape(status.text)}</p></div>', unsafe_allow_html=True)
    elif status.state in CLIENT_SAYS:
        title, text = CLIENT_SAYS[status.state]
        st.markdown(f'<div class="ub-card {LOOK.get(status.state, "")}"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>', unsafe_allow_html=True)
    left, right = st.columns(2)
    if left.button("Start the live view" if developer else "Start the live demo", key="live_start", type="primary", disabled=running, width="stretch"):
        if developer:
            note = "Starting the live view (the connected loop takes about a minute the first time)..." if supervisor.connected else "Starting the live view (a few seconds)..."
        else:
            note = "Getting the cell ready..."
        with st.spinner(note):
            supervisor.start()
        st.rerun()
    if right.button("Stop the live view" if developer else "Stop the live demo", key="live_stop", disabled=not running, width="stretch"):
        supervisor.stop()
        st.rerun()
    if developer and status.lines:
        with st.expander("What the live program said"):
            st.code("\n".join(status.lines), language="text")


def render() -> None:
    record, path = context.load_record()
    dashboard_style.stamp(record.meta.banner)
    if context.developer():
        st.subheader("Live run")
    else:
        st.markdown(landing.page_header("Monitor", "Live run", "The cell at work, with the camera checks as they happen."), unsafe_allow_html=True)
    supervisor = supervisor_for(record)
    if context.developer():
        st.caption("The simulated cell runs while you watch" + (", with the loop connected: the data is read, the models judged, and the decision engine chooses every recipe" if supervisor.connected else "") + ". It is a separate program that runs on this computer only; it stops when you press Stop or when this app closes. Illustrative: a simulation with made-up values.")
    status = supervisor.status()
    if not context.developer() and status.state != "running":
        st.markdown(landing.live_ready_html(), unsafe_allow_html=True)             # the client view's empty state: how to run the demo, beside the cell
    panel(status.state == "running", supervisor, context.developer())
    if status.state == "running":
        st.iframe(status.address + ("&" if "?" in status.address else "?") + EMBEDDED, height=FRAME_HEIGHT)
