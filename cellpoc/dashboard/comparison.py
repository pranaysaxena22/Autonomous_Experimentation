"""Page 4 - Does learning help?: the multi-campaign comparison and the difficulty table."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from . import style

WITHOUT = "Without faults (the headline comparison)"
WITH = "With the scripted faults applied to every strategy"


def _when(trial, limit) -> str:
    return str(trial) if trial is not None else f"not within {limit}"


def _curves(comparison, measure, title) -> alt.Chart:
    rows = [{"Strategy": s.label, "Trial": trial, "% of campaigns that have found one": pct}
            for s in comparison.strategies for trial, pct in enumerate(getattr(s, measure).cumulative_pct, start=1)]
    return alt.Chart(pd.DataFrame(rows)).mark_line(interpolate="step-after", strokeWidth=3).encode(
        x=alt.X("Trial:Q", scale=alt.Scale(domain=[1, comparison.trials_per_campaign])),
        y=alt.Y("% of campaigns that have found one:Q", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("Strategy:N", scale=alt.Scale(domain=list(style.STRATEGY_COLOURS), range=list(style.STRATEGY_COLOURS.values()))),
        tooltip=["Strategy", "Trial", "% of campaigns that have found one"]).properties(height=300, title=title)


def render(record) -> None:
    style.stamp(record.meta.banner)
    choice = WITHOUT
    if record.comparison_with_faults is not None:
        choice = st.radio("Show", [WITHOUT, WITH], horizontal=True)
    comparison = record.comparison_with_faults if choice == WITH else record.comparison
    if comparison is None:
        st.info("This run record does not contain the strategy comparison.")
        return
    limit = comparison.trials_per_campaign

    st.markdown(f"{comparison.campaigns} campaigns of {limit} trials each. Every strategy faces the same {comparison.campaigns} "
                "seeds (the same lab, the same measurement noise), so the comparison is paired.")
    st.markdown(f"**Headline measure:** {comparison.headline_label}")
    st.info(comparison.headline_text)

    table = pd.DataFrame([{"Strategy": s.label,
                           "25% of campaigns had found one by trial": _when(s.truly_good.trial_by_25pct, limit),
                           "Half had by trial (median)": _when(s.truly_good.median_trial, limit),
                           "75% had by trial": _when(s.truly_good.trial_by_75pct, limit),
                           f"Found one within {limit} trials": f"{s.truly_good.found_pct:.0f}% of campaigns"}
                          for s in comparison.strategies])
    st.dataframe(table, hide_index=True, width="stretch")

    left, right = st.columns(2)
    with left:
        style.chart(_curves(comparison, "truly_good", "HEADLINE: first trial whose recipe was truly good"))
    with right:
        style.chart(_curves(comparison, "measured_pass", "Second measure: first trial measured as passing"))

    st.markdown("**Campaign by campaign (same seed), who found one first**")
    for pair in comparison.paired:
        st.markdown(f"- {pair.sentence}  *(measure: {'truly good' if pair.measure == 'first_truly_good' else 'measured as passing'})*")
    with st.expander("How to read these measures"):
        for note in comparison.measure_notes:
            st.markdown(f"- {note}")

    st.subheader("Does it depend on how rare good recipes are?")
    rows = []
    for row in comparison.difficulty:
        for strategy in row.strategies:
            rows.append({"Difficulty": row.level, "Random recipes that are truly good": f"{row.good_share_pct:g}%",
                         "Strategy": strategy.label, f"Found one within {limit} trials": f"{strategy.found_pct:.0f}% of campaigns",
                         "Median trial": _when(strategy.median_trial, limit)})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Same comparison, same seeds and same engine, without faults, on an easier and a harder version of the hidden truth.")
    if record.about is not None:
        st.info(record.about.comparison_note)
