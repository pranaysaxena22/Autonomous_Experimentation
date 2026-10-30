"""The dashboard. It reads the run record and displays it; it makes no decisions and does no calculations
(see throughput.py for the single documented exception)."""
from __future__ import annotations

import streamlit as st

from . import about, comparison, data, handovers, platform_data, platform_replay, platform_reports, run_view, style, throughput, timeline

TABS = ["The run", "Timeline", "Overnight handovers", "Does learning help?", "Throughput", "What this shows"]
PLATFORM_TABS = ["3D replay", "Data and model", "Reports"]


def main() -> None:
    style.apply()
    record, path, problem = data.load()
    style.header()
    if record is None:
        style.banner(style.FALLBACK_BANNER)
        st.warning(f"{problem} Double-click build_demo.bat (it takes about a minute or two), then reload this page. "
                   f"Looked for: {path}")
        return

    style.banner(record.meta.banner)
    # A record from a platform run (Stage 8) carries a 'platform' section and gets three more pages after the six (3D replay, Data and model, Reports); a proof-of-concept record has none and shows exactly the six pages it always showed.
    tabs = TABS + PLATFORM_TABS if record.platform is not None else TABS
    pages = st.tabs(tabs)
    for page, render in zip(pages, (run_view.render, timeline.render, handovers.render, comparison.render,
                                    throughput.render, about.render)):
        with page:
            render(record)
    if record.platform is not None:
        with pages[len(TABS)]:
            platform_replay.render(record, path)
        with pages[len(TABS) + 1]:
            platform_data.render(record)
        with pages[len(TABS) + 2]:
            platform_reports.render(record, path)
