"""The Overview page: what this is, the run in numbers, and the pages in demo order.

Every number is a field the simulator wrote into the run record (its summary); the page only displays them and works nothing out.
"""
from __future__ import annotations

import html

import streamlit as st

from cellpoc.dashboard import client_results
from cellpoc.dashboard import style as dashboard_style
from cellpoc.shell import context, landing, menu

# The metric cards and their labels. The labels are fixed text so that a check can find each card and compare it with the record.
LABELS = {"attempted": "Trials attempted", "with_result": "Trials with a result", "good": "Good recipes", "skipped": "Skipped (no result)",
          "recovered": "Faults recovered", "alerts": "Alerts for staff", "per_week": "Trials with a result per week", "manual": "Manual baseline per week", "times": "Times the manual rate"}

# The loop the cell repeats for every trial, as four short steps (fixed text). The presenter explains; the page only shows.
LOOP = [
    ("Sense", "Reads the instruments"),
    ("Reason", "Chooses the next recipe"),
    ("Act", "Makes and tests the tablets"),
    ("Adapt", "Recovers, then hands over"),
]

# What is real and what is not, in a few words (fixed text).
HONESTY = [
    ("Simulated here", "The cell's motions, timings, readings and results. All values are made up.", ""),
    ("Built and tested", "Setup, decision engine, planner, executor, instrument drivers, physics reach check.", "ub-card-green"),
    ("Needs hardware or real data", "A real arm, real instruments, a real study's data.", "ub-quiet"),
]


def _client(record, path) -> None:
    """The Overview as the people the demo is for see it: a product page (what it is, the challenge, the solution, how it works), what this run delivered, where to go next, and the run in numbers."""
    summary = record.summary
    dashboard_style.stamp(record.meta.banner)
    landing.render_top()
    landing.render_story()
    st.markdown(landing.section("The proof", "What this run delivered", "Illustrative values from a simulated run. The manual comparison is an assumption."), unsafe_allow_html=True)
    story = client_results.load_story(path)
    if story is not None:
        client_results.headline_cards(story)
    landing.render_explore()
    st.markdown(landing.section("The run in numbers", "This run in numbers"), unsafe_allow_html=True)
    first = st.columns(6)
    first[0].metric(LABELS["attempted"], summary.trials_attempted)
    first[1].metric(LABELS["with_result"], summary.trials_with_result)
    first[2].metric(LABELS["good"], summary.trials_good)
    first[3].metric(LABELS["skipped"], summary.trials_skipped)
    first[4].metric(LABELS["recovered"], summary.faults_recovered)
    first[5].metric(LABELS["alerts"], summary.alerts_for_staff)
    st.caption(f"{summary.headline}. {summary.attempts_text}. About 29 to 30 trials fit a run. Illustrative values.")
    st.page_link("cellpoc/shell/pages/about.py", label="What this shows, and what it does not", icon=":material/info:")


def render() -> None:
    record, path = context.load_record()
    if not context.developer():
        _client(record, path)
        return
    summary = record.summary
    dashboard_style.stamp(record.meta.banner)
    st.markdown('<div class="ub-hero"><div class="ub-eyebrow">Autonomous experimentation &middot; tablet formulation</div>'
                '<h1>Experiments that run themselves, <span class="ub-accent">day</span> and night</h1>'
                '<p>A robotic lab station that makes and tests tablets by itself. A simulated prototype: all values are illustrative.</p></div>', unsafe_allow_html=True)
    if record.platform is not None:
        st.caption(record.platform.label)
    st.page_link("cellpoc/shell/pages/live_run.py", label="Start the live demo", icon=":material/play_circle:")
    story = client_results.load_story(path)
    if story is not None:                                              # the four numbers a client remembers (a platform run saved with its results summary)
        client_results.headline_cards(story)
        st.caption("Illustrative values. The manual comparison is an assumption.")
    loop = "".join(f'<div class="ub-loop-step"><div class="ub-loop-name">{html.escape(name)}</div><div class="ub-loop-text">{html.escape(text)}</div></div>' for name, text in LOOP)
    st.markdown(f'<div class="ub-loop">{loop}</div><div class="ub-loop-caption">Repeated for every trial, day and night.</div>', unsafe_allow_html=True)

    st.subheader("This run in numbers")
    first = st.columns(6)
    first[0].metric(LABELS["attempted"], summary.trials_attempted)
    first[1].metric(LABELS["with_result"], summary.trials_with_result)
    first[2].metric(LABELS["good"], summary.trials_good)
    first[3].metric(LABELS["skipped"], summary.trials_skipped)
    first[4].metric(LABELS["recovered"], summary.faults_recovered)
    first[5].metric(LABELS["alerts"], summary.alerts_for_staff)
    second = st.columns(3)
    second[0].metric(LABELS["per_week"], f"{summary.trials_per_week:.1f}")
    second[1].metric(LABELS["manual"], f"{summary.manual_baseline_trials_per_week:g}")
    second[2].metric(LABELS["times"], f"{summary.speedup_vs_manual:.1f}x")
    st.caption(f"{summary.headline}. {summary.attempts_text}. About 29 to 30 trials fit a run. Illustrative values.")

    st.subheader("What is real, and what is not")
    for column, (title, text, extra) in zip(st.columns(3), HONESTY):
        column.markdown(f'<div class="ub-card ub-tall {extra}"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>', unsafe_allow_html=True)

    st.subheader("The pages, in demo order")
    for number, entry in enumerate(_pages(record), start=1):
        left, right = st.columns([6, 1], vertical_alignment="center")
        left.markdown(f'<div class="ub-card ub-step"><div class="ub-num">{number}</div><div><h4>{html.escape(entry.title)}</h4><p>{html.escape(entry.what)}</p></div></div>', unsafe_allow_html=True)
        right.page_link(entry.path, label="Open", icon=":material/arrow_forward:")


def _pages(record) -> list:
    """The menu entries that exist for this run, in menu order (the 3D replay, data and report pages only for a platform run); the Overview itself and the About page are left out of the walk."""
    found = []
    for entries in menu.SECTIONS.values():
        for entry in entries:
            if entry.title in ("Overview", "About and limits"):
                continue
            if entry.needs_platform and record.platform is None:
                continue
            found.append(entry)
    return found
