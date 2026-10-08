"""Page 5 - Throughput: the autonomous cell against a manual baseline you can edit.

THE ONE CALCULATION THIS DASHBOARD MAKES: the autonomous trials per week (taken from the run
record) divided by the manual baseline (editable here, default taken from the run record). That
single division, in `multiple` below, is the documented exception to "the dashboard only reads
the run record"; an automated check enforces that nothing else is calculated anywhere.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from . import style


def render(record) -> None:
    style.stamp(record.meta.banner)
    summary = record.summary
    st.markdown("How much experimentation fits into the same calendar time, autonomous against manual. "
                "The manual baseline is an assumption: change it to match the client's real figure.")

    baseline = st.number_input("Manual baseline: trials per week", min_value=0.5, step=1.0,
                               value=float(summary.manual_baseline_trials_per_week))
    autonomous = summary.trials_per_week
    multiple = autonomous / baseline   # the dashboard's only calculation

    first, second, third = st.columns(3)
    first.metric("Autonomous (trials with results per week)", f"{autonomous:g}")
    second.metric("Manual baseline (trials per week)", f"{baseline:g}")
    third.metric("Autonomous is", f"{multiple:.1f}x manual")

    bars = pd.DataFrame([{"Who": "Autonomous cell", "Trials per week": autonomous},
                         {"Who": "Manual baseline", "Trials per week": baseline}])
    style.chart(alt.Chart(bars).mark_bar(size=70).encode(
        x=alt.X("Who:N", title=None, sort=["Autonomous cell", "Manual baseline"]), y=alt.Y("Trials per week:Q"),
        color=alt.Color("Who:N", legend=None, scale=alt.Scale(domain=["Autonomous cell", "Manual baseline"],
                                                              range=[style.GREEN, "#A0A0A0"])),
        tooltip=["Who", "Trials per week"]).properties(height=320))

    st.markdown(f"**This run:** {summary.attempts_text}. The lab was empty for {summary.unattended_hours:g} of "
                f"{summary.run_hours:g} hours, and {summary.trials_started_unattended} trials were started with nobody in the lab.")
    if record.about is not None:
        st.info(record.about.throughput_note)
