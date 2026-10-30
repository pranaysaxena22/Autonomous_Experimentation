"""The welcome and the guided tour of the app (client view only).

When someone opens the app for the first time in a session a welcome window says, in a few lines, what this product is, and offers a tour. The tour is a short card at the top of each page, step by step, that says what the page is for and what to try,
with Back, Next and End tour; it opens the right page for each step. A "Take the tour" button in the left menu starts it again at any time. Everything here is fixed text; nothing is worked out and nothing is sent anywhere.
"""
from __future__ import annotations

import html
from typing import NamedTuple

import streamlit as st

from cellpoc.shell import landing

PAGES = "cellpoc/shell/pages/"


class Step(NamedTuple):
    id: str
    page: str           # the page file this step is about, relative to the app's launcher file
    title: str
    text: str
    tip: str            # one thing to try on that page ("" for none)
    prev: str           # the id of the step before ("" for the first)
    next: str           # the id of the step after ("" for the last)
    label: str          # "Step 2 of 8", written out so that nothing has to be counted


STEPS = [
    Step("overview", PAGES + "overview.py", "Start here: the headline",
         "The Overview shows what the cell delivered in this run: more experiments per week than working by hand, how much ran unattended, how quickly it found a good recipe and how many recipes met the requirements.",
         "Press Start the live demo to watch the cell work.", "", "live", "Step 1 of 8"),
    Step("live", PAGES + "live_run.py", "Watch the cell work",
         "Press Start the live demo and wait a few seconds, then press Start the run inside the live view. Simulated time runs faster than real time: the Speed menu changes how fast. The clock, the four numbers across the top and the charts update as the run goes on.",
         "Choose 600x for a quick look.", "overview", "camera", "Step 2 of 8"),
    Step("camera", PAGES + "live_run.py", "What the camera checks mean",
         "When the arm picks up an ingredient bottle, the camera scans its barcode, reads its printed name and looks at the liquid. A green flashing frame means the right bottle, red means a wrong one and amber means please check. A pressed tablet is inspected the same way.",
         "Open Demo scenario at the top and choose a wrong bottle or a defective tablet to see the red case.", "live", "results", "Step 3 of 8"),
    Step("results", PAGES + "results.py", "Results at a glance",
         "Charts of what the run delivered: how well each recipe dissolved, the good recipes so far, where the good recipes are, what happened when something went wrong, and the handover for the morning team.",
         "", "camera", "vision", "Step 4 of 8"),
    Step("vision", PAGES + "vision.py", "Vision",
         "Pick a sample picture, take one with your camera or upload a photo of liquids. The cell reads which solution is in each vessel and how full it is.",
         "Choose a different sample from the list.", "results", "setup", "Step 5 of 8"),
    Step("setup", PAGES + "setup.py", "Describe your own study",
         "Set the ingredients, targets, step times and calendar in ten short screens. The app checks what you enter as you go; you can save the setup and run it as a simulation.",
         "Press Load example to start from a ready-made study.", "vision", "reports", "Step 6 of 8"),
    Step("reports", PAGES + "reports.py", "Take it away",
         "Download the report as a web page, a PDF or an Excel workbook, or the tables as CSV files. Every file says it is a simulation.",
         "", "setup", "about", "Step 7 of 8"),
    Step("about", PAGES + "about.py", "What this does and does not show",
         "Every number here is an illustrative value from a simulation. Read this page before drawing any conclusion about real equipment, real tablets or real accuracy.",
         "", "reports", "", "Step 8 of 8"),
]
BY_ID = {step.id: step for step in STEPS}
FIRST = STEPS[0]

CSS = """<style>
@keyframes ub-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(134,188,37,0.0); } 50% { box-shadow: 0 0 0 10px rgba(134,188,37,0.35), 0 0 28px 6px rgba(134,188,37,0.45); } }
@keyframes ub-sweep { 0% { transform: translateX(-120%); } 100% { transform: translateX(320%); } }
.ub-welcome { text-align: center; padding: 6px 4px 2px; }
.ub-welcome .ub-ring { width: 64px; height: 64px; border-radius: 50%; margin: 4px auto 14px; border: 4px solid #86BC25; display: flex; align-items: center; justify-content: center; animation: ub-pulse 1.6s ease-in-out infinite; }
.ub-welcome .ub-ring i { width: 22px; height: 22px; border-radius: 50%; background: #86EB22; display: block; }
.ub-welcome h2, [data-testid="stDialog"] [role="dialog"] .ub-welcome h2 { margin: 0 0 4px; font-size: 1.75rem; line-height: 1.2; letter-spacing: -0.01em; text-transform: none; font-weight: 700; color: #FFFFFF; }
.ub-welcome .ub-lead { color: #E6E6E6; font-size: 1.05rem; margin: 0 0 14px; }
.ub-welcome .ub-bar-sweep { height: 3px; width: 100%; background: #282728; border-radius: 999px; overflow: hidden; margin: 0 0 16px; }
.ub-welcome .ub-bar-sweep i { display: block; height: 3px; width: 30%; background: #86BC25; animation: ub-sweep 2.2s linear infinite; }
.ub-points { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 0 0 12px; text-align: left; }
.ub-point { background: #282728; border-left: 4px solid #86BC25; border-radius: 8px; padding: 10px 12px; font-size: 0.9rem; }
.ub-point b { display: block; color: #FFFFFF; margin-bottom: 2px; }
.ub-welcome .ub-small { color: #E6E6E6; font-size: 0.8rem; margin: 0 0 6px; }
.ub-tour { background: #282728; border: 2px solid #86BC25; border-radius: 12px; padding: 12px 16px; margin: 4px 0 6px; animation: ub-pulse 1.6s ease-in-out 3; }
.ub-tour .ub-tour-step { color: #86EB22; font-weight: 800; font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; }
.ub-tour h4 { margin: 2px 0 4px; }
.ub-tour p { margin: 0 0 4px; font-size: 0.92rem; }
.ub-tour .ub-tour-tip { color: #86EB22; }
@media (max-width: 900px) { .ub-points { grid-template-columns: minmax(0, 1fr); } }
@media (prefers-reduced-motion: reduce) { .ub-welcome .ub-ring, .ub-welcome .ub-bar-sweep i, .ub-tour { animation: none; } }
</style>"""

WELCOME = ("""<div class="ub-welcome"><div class="ub-ring"><i></i></div>
<h2>Welcome to the Autonomous Formulation Cell</h2>
<p class="ub-lead">Experiments that run themselves, day and night.</p>
<div class="ub-bar-sweep"><i></i></div>
<div class="lp-duo">
<div class="lp-duo-col"><span class="lp-eyebrow">The challenge</span><p>Formulating a tablet is slow and manual: about 9 experiments a week by hand (an assumption), nothing at night or at weekends, and every bottle and tablet checked by eye.</p></div>
<div class="lp-duo-col lp-duo-gain"><span class="lp-eyebrow">The solution</span><p>A robotic lab station that makes, tests and learns from tablet recipes by itself, around the clock, and checks every ingredient bottle and every tablet with its own cameras.</p></div>
</div>
<div class="ub-points">""" + "".join(f'<div class="ub-point"><b>{title}</b>{text}</div>' for _, title, text in landing.SOLUTION) + """</div>
<p class="ub-small">This is a simulated prototype: every number you will see is illustrative.</p></div>""")


def start() -> None:
    """Begin the tour at its first step, on the right page."""
    st.session_state["tour"] = FIRST.id
    st.switch_page(FIRST.page)


def _go(step_id: str) -> None:
    st.session_state["tour"] = step_id or None
    if step_id:
        st.switch_page(BY_ID[step_id].page)
    st.rerun()


@st.dialog("Welcome", width="large")
def _welcome() -> None:
    st.markdown(WELCOME, unsafe_allow_html=True)
    left, right = st.columns(2)
    if left.button("Take the tour", key="welcome_tour", type="primary", width="stretch"):
        st.session_state["tour"] = FIRST.id                 # a window's buttons only redraw the window: ask for the whole page to be drawn again, and the app's main page opens the first step's page (see open_pending)
        st.session_state["tour_goto"] = FIRST.page
        st.rerun()
    if right.button("Explore on my own", key="welcome_skip", width="stretch"):
        st.rerun()


def open_pending() -> None:
    """If the welcome window asked for the tour to begin, open the first step's page now."""
    target = st.session_state.pop("tour_goto", None)
    if target:
        st.switch_page(target)


def welcome_once() -> None:
    """The welcome window, the first time in a session only (closing it, or choosing either button, does not bring it back)."""
    if st.query_params.get("welcome") == "off":                # a link can skip the welcome (for example a link to one page, or a presenter who has already said hello)
        st.session_state["welcomed"] = True
    if not st.session_state.get("welcomed"):
        st.session_state["welcomed"] = True
        _welcome()


def card() -> None:
    """The tour's card for the current step, at the top of the page, with Back, Next and End tour. Nothing is drawn when no tour is running."""
    step_id = st.session_state.get("tour")
    if step_id not in BY_ID:
        return
    step = BY_ID[step_id]
    tip = f'<p class="ub-tour-tip">Try this: {html.escape(step.tip)}</p>' if step.tip else ""
    st.markdown(f'<div class="ub-tour"><div class="ub-tour-step">Tour &middot; {html.escape(step.label)}</div><h4>{html.escape(step.title)}</h4><p>{html.escape(step.text)}</p>{tip}</div>', unsafe_allow_html=True)
    back, forward, end, space = st.columns([1, 1, 1, 5])
    if step.prev and back.button("Back", key="tour_back", width="stretch"):
        _go(step.prev)
    if forward.button("Next" if step.next else "Finish", key="tour_next", type="primary", width="stretch"):
        _go(step.next)
    if end.button("End tour", key="tour_end", width="stretch"):
        _go("")
    st.page_link(step.page, label=f"Open: {step.title}", icon=":material/arrow_forward:")


def sidebar_button() -> None:
    """'Take the tour' in the left menu, so the tour can be started again at any time."""
    if st.sidebar.button("Take the tour", key="tour_again", icon=":material/explore:", width="stretch"):
        start()
