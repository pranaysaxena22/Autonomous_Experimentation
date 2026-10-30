"""Menu page: The run. The dashboard's first five pages as tabs, unchanged (the sixth, What this shows, is the About page)."""
import streamlit as st

from cellpoc.dashboard import comparison, handovers, run_view, throughput, timeline
from cellpoc.shell import context

record, path = context.load_record()
tabs = st.tabs(["The run", "Timeline", "Overnight handovers", "Does learning help?", "Throughput"])
for tab, render in zip(tabs, (run_view.render, timeline.render, handovers.render, comparison.render, throughput.render)):
    with tab:
        render(record)
