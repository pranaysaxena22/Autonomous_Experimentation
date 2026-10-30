"""Reading the run record for a page of the unified app. It uses the dashboard's reader, so the unified app and the dashboard can never disagree about which record is open."""
from __future__ import annotations

import streamlit as st

from cellpoc.dashboard import data


_VIEW = {"developer": False}


def set_developer(flag: bool) -> None:
    """Called once per run by the app's main page with the launcher's choice."""
    _VIEW["developer"] = bool(flag)


def developer() -> bool:
    """True in the developer view (every page, the technical detail); False in the client view. The launcher chooses; a page cannot."""
    return _VIEW["developer"]


def run_name(record) -> str:
    """The name shown on the top bar: the setup's name for a platform run, the run's id otherwise."""
    return record.platform.setup_name if record.platform is not None else record.meta.run_id


def load_record():
    """(the run record, the path it was read from). With no usable record the page says so in plain words and stops."""
    record, path, problem = data.load()
    if record is None:
        if developer():
            st.warning(f"{problem} Double-click run_app.bat (it builds a run first), then reload this page. Looked for: {path}")
        else:
            st.warning("The demo is not ready yet. Please ask the person who set it up to prepare it.")
        st.stop()
    return record, path
