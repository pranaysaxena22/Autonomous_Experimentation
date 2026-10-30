"""The unified app: page settings, the dark look, the top bar, and the left menu that opens each page. It reads the run record and displays it; it calculates nothing."""
from __future__ import annotations

import streamlit as st

from cellpoc.dashboard import data
from cellpoc.dashboard import style as dashboard_style
from cellpoc.shell import context, landing, menu, style, tour


def main(developer: bool = False) -> None:
    """`developer` is the launcher's choice: the full developer view (every page, the technical detail) or, by default, the client view."""
    context.set_developer(developer)
    st.set_page_config(page_title="Autonomous formulation cell", page_icon=dashboard_style.FAVICON, layout="wide")
    # the dashboard's pages are drawn with its style sheet (set_page_config is called once, above), then the dark look goes over it
    st.markdown(dashboard_style.CSS, unsafe_allow_html=True)
    st.markdown(style.CSS, unsafe_allow_html=True)
    record, path, problem = data.load()
    if record is None:
        if developer:
            st.warning(f"{problem} Double-click run_app.bat (it builds a run first), then reload this page. Looked for: {path}")
        else:
            st.warning("The demo is not ready yet. Please ask the person who set it up to prepare it.")
        return
    style.topbar(context.run_name(record), record.summary.trials_attempted, developer)
    guided = not developer and record.platform is not None            # the welcome and the tour are for the client view of a platform run (the pages they visit all exist there)

    pages = {}
    for section, entries in (menu.SECTIONS if developer else menu.CLIENT_SECTIONS).items():
        shown = []
        for entry in entries:
            if entry.needs_platform and record.platform is None:
                continue
            shown.append(st.Page(entry.path, title=entry.title, icon=entry.icon, default=entry.title == "Overview"))
        if shown:
            pages[section] = shown
    current = st.navigation(pages, position="sidebar")                # the pages are registered first: switching to a page (which the tour does) is only possible after that
    if not developer:
        st.markdown(landing.CSS, unsafe_allow_html=True)              # the client view's product-page look (and it hides the web framework's own toolbar)
    if guided:
        st.markdown(tour.CSS, unsafe_allow_html=True)
        tour.open_pending()
        tour.welcome_once()
        tour.card()
        tour.sidebar_button()
    current.run()
