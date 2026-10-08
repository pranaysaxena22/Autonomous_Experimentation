"""The dashboard. It reads the run record and displays it; it makes no decisions and does no calculations
(see throughput.py for the single documented exception)."""
from __future__ import annotations

import streamlit as st

from . import about, comparison, data, handovers, run_view, style, throughput, timeline

TABS = ["The run", "Timeline", "Overnight handovers", "Does learning help?", "Throughput", "What this shows"]


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
    pages = st.tabs(TABS)
    for page, render in zip(pages, (run_view.render, timeline.render, handovers.render, comparison.render,
                                    throughput.render, about.render)):
        with page:
            render(record)
