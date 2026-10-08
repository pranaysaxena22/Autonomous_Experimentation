"""Page 2 - Timeline: every trial across the run, with night/weekend shading, and faults and skips marked."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from . import style


def _shading(record) -> alt.Chart:
    blocks = pd.DataFrame([{"Start": b.start, "End": b.end, "Lab": b.kind} for b in record.calendar])
    return alt.Chart(blocks).mark_rect(opacity=0.55).encode(
        x=alt.X("Start:T", title="Date and time"), x2="End:T",
        color=alt.Color("Lab:N", scale=alt.Scale(domain=list(style.SHADE_COLOURS), range=list(style.SHADE_COLOURS.values())),
                        legend=alt.Legend(title="Lab")))


def _bars(record, row) -> alt.Chart:
    rows = [{"Trial": t.trial, "Station": s.step, "Stage": s.label, "Start": s.start, "End": s.end, "What": s.look,
             "Someone in the lab when it began": "yes" if s.attended else "no"}
            for t in record.trials for s in t.steps]
    return alt.Chart(pd.DataFrame(rows)).mark_bar(height=12).encode(
        x="Start:T", x2="End:T", y=row,
        color=alt.Color("What:N", scale=alt.Scale(domain=list(style.LOOK_COLOURS), range=list(style.LOOK_COLOURS.values())),
                        legend=alt.Legend(title="What happened")),
        tooltip=["Trial", "Stage", "Start", "End", "What", "Someone in the lab when it began"])


def render(record) -> None:
    style.stamp(record.meta.banner)
    st.markdown("Every trial across the run. **Grey shading = nobody in the lab** (darker = weekend). "
                "Red, amber and brown bars are faults; a triangle marks an alert.")

    alerts = pd.DataFrame([{"Trial": a.trial, "Time": a.time, "When": a.when, "Alert": a.message, "Severity": a.severity}
                           for a in record.alerts])
    markers = alt.Chart(alerts).mark_point(shape="triangle-up", size=260, filled=True, opacity=1).encode(
        x="Time:T", y=alt.Y("Trial:O"),
        color=alt.Color("Severity:N", scale=alt.Scale(domain=["Recovered", "Needs attention"], range=["#F5A623", "#D0021B"]),
                        legend=alt.Legend(title="Alert")),
        tooltip=["When", "Alert", "Severity"])
    by_trial = (_shading(record) + _bars(record, alt.Y("Trial:O", sort="ascending", title="Trial")) + markers).properties(
        height=620, title="Trials across the run")
    style.chart(by_trial)

    by_station = (_shading(record) + _bars(record, alt.Y("Stage:N", title=None, sort=[s.label for s in record.steps]))).properties(
        height=230, title="The same run, station by station")
    with st.expander("Station by station", expanded=False):
        style.chart(by_station)

    phases = pd.DataFrame([{"Trial": t.trial, "Phase": p.phase, "Start": p.start, "End": p.end, "What it did": p.description}
                           for t in record.trials for p in t.phases])
    phase_chart = alt.Chart(phases).mark_bar(height=14).encode(
        x=alt.X("Start:T", title="Date and time"), x2="End:T",
        y=alt.Y("Phase:N", title=None, sort=["Act", "Sense", "Reason", "Adapt"]),
        color=alt.Color("Phase:N", scale=alt.Scale(domain=list(style.PHASE_COLOURS), range=list(style.PHASE_COLOURS.values()))),
        tooltip=["Trial", "Phase", "Start", "End", "What it did"]).properties(
        height=170, title="Act, Sense, Reason, Adapt for every trial (hover for what each did)")
    with st.expander("Sense / Reason / Act / Adapt over time", expanded=False):
        style.chart(phase_chart)
