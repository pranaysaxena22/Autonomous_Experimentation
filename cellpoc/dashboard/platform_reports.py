"""The 'Reports' page (platform runs only): download buttons for the report files that were written next to the run record (the branded report page and PDF, the Excel workbook and the CSV tables).

The files are written in advance by cellpoc/reports (double-click make_reports.bat, or run a platform run); this page only offers them. Nothing here is worked out or sent anywhere.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import style

OFFERED = (
    ("report.html", "Report page (opens in any browser)", "text/html"),
    ("report.pdf", "Report as PDF", "application/pdf"),
    ("report.xlsx", "Excel workbook (summary, trials, events, alerts, handovers, data and model, limitations)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("trials.csv", "Trials as a CSV table", "text/csv"),
    ("events.csv", "Events as a CSV table", "text/csv"),
    ("alerts.csv", "Alerts as a CSV table", "text/csv"),
)


def render(record, record_path, client: bool = False) -> None:
    """`client` leaves out the technical wording (the developer view keeps it)."""
    style.stamp(record.meta.banner)
    if client:
        st.markdown('<div class="lp-pagehead"><span class="lp-eyebrow">Output</span><h1>Reports</h1><p>Take the results away: a report as a web page, a PDF or an Excel workbook, and the tables as CSV files. Every file carries the illustrative label and says it is a simulation.</p></div>', unsafe_allow_html=True)
    else:
        st.subheader("Reports and exports")
        st.caption(record.platform.label + " Every file carries this label and says it is a simulation.")
    folder = Path(record_path).parent.joinpath("reports")
    offered = 0
    for name, text, mime in OFFERED:
        file = folder.joinpath(name)
        if file.exists():
            st.download_button(text, data=file.read_bytes(), file_name=name, mime=mime, key=f"download_{name}")
            offered = offered + 1
    if offered == 0:
        st.info("The reports are not ready yet. Please ask the person who set up the demo to prepare them." if client else f"No report files were found next to the run record (looked in {folder}). Double-click make_reports.bat to write them.")
