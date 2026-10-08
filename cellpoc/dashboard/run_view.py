"""Page 1 - The run: a time slider, Next/Previous event buttons, and the state of the cell at that moment."""
from __future__ import annotations

import streamlit as st

from . import style

KEY = "snap_index"
PHASE_TITLES = {"Act": "ACT", "Sense": "SENSE", "Reason": "REASON", "Adapt": "ADAPT"}


def _go(index) -> None:
    st.session_state[KEY] = index


def render(record) -> None:
    style.stamp(record.meta.banner)
    snaps = record.snapshots
    if KEY not in st.session_state:
        st.session_state[KEY] = 0
    now = snaps[st.session_state[KEY]]

    left, middle, right = st.columns([1, 6, 1])
    left.button("Previous event", key="previous_event", on_click=_go, args=(now.previous_event_index,),
                disabled=now.previous_event_index is None, width="stretch")
    right.button("Next event", key="next_event", on_click=_go, args=(now.next_event_index,),
                 disabled=now.next_event_index is None, width="stretch")
    middle.select_slider("Moment in the run", options=list(range(len(snaps))), key=KEY,
                         format_func=lambda i: snaps[i].when)

    st.subheader(now.when)
    badge = "lab-in" if now.staff_present else "lab-out"
    st.markdown(f'<span class="lab-badge {badge}">{now.staff_text}</span>', unsafe_allow_html=True)
    if now.just_happened:
        st.markdown("**At this moment:** " + " / ".join(now.just_happened))

    st.markdown("#### Stations")
    for column, station in zip(st.columns(len(now.stations)), now.stations):
        column.markdown(f'<div class="tile tile-{station.state}"><div class="tile-title">{station.station}</div>'
                        f'<div class="tile-text">{station.text}</div></div>', unsafe_allow_html=True)

    st.markdown("#### Sense / Reason / Act / Adapt")
    st.caption("These four phases form a loop that repeats for every trial. The highlighted box is the phase the cell is in at this moment.")
    for column, phase in zip(st.columns(len(now.phases)), now.phases):
        column.markdown(f'<div class="phase phase-{phase.state}">{PHASE_TITLES[phase.phase]}</div>', unsafe_allow_html=True)
    for phase in now.phases:
        if phase.state == "active":
            st.markdown(f"**Now, {phase.phase}:** {phase.description}")
    with st.expander("What each phase did in this trial"):
        for phase in now.phases:
            st.markdown(f"**{phase.phase}** ({phase.state.replace('_', ' ')}): {phase.description}")

    st.markdown(f"#### {now.trial_headline}")
    recipe, outcome = st.columns(2)
    if now.recipe_lines:
        recipe.markdown("**Recipe**")
        for line in now.recipe_lines:
            recipe.markdown(f"- {line}")
        if now.why:
            recipe.markdown("**Why this recipe**")
            recipe.info(now.why)
    outcome.markdown("**Result**")
    shown = {"good": outcome.success, "not_good": outcome.warning, "no_result": outcome.error, "pending": outcome.info}
    if now.result_kind in shown:
        shown[now.result_kind](now.result_text)

    st.caption(f"Trials finished: {now.trials_finished}   |   Results known: {now.results_so_far}   |   "
               f"Good so far: {now.good_so_far}   |   {now.best_text}")
    if now.alerts_so_far:
        st.markdown("**Alerts so far**")
        for alert in now.alerts_so_far:
            st.markdown(f"- {alert}")
    with st.expander("Recent events (newest first)"):
        for line in now.recent_events:
            st.markdown(f"- {line}")
