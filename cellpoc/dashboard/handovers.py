"""Page 3 - Overnight handovers: what happened while nobody was in the lab, then the full event log."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import style


def render(record) -> None:
    style.stamp(record.meta.banner)
    st.markdown("Each summary below is what the cell would hand over to the first person to walk in.")
    for handover in record.handovers:
        with st.container(border=True):
            st.subheader(handover.title)
            st.write(handover.text)
            started, with_result, skipped, good, staff = st.columns(5)
            started.metric("Trials started", handover.trials_started)
            with_result.metric("With a result", handover.trials_with_result)
            skipped.metric("Skipped", handover.trials_skipped)
            good.metric("Measured good", handover.trials_good)
            staff.metric("Alerts for staff", handover.alerts_for_staff)

    st.subheader("Event log")
    log = pd.DataFrame([{"When": e.when, "Trial": e.trial, "Station": e.station, "Someone in the lab?": "yes" if e.attended else "no",
                         "Event": e.message} for e in record.events])
    st.dataframe(log, hide_index=True, width="stretch")
