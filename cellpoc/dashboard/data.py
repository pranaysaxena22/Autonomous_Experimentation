"""Reading the run record. This is the dashboard's only source of information."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from cellpoc import run_store

DEFAULT_RECORD = Path(__file__).resolve().parents[2].joinpath("runs", "demo", "record.json")


@st.cache_data(show_spinner="Loading the run record...")
def _read(path: str, saved_at: float):
    return run_store.load(path)


def load():
    """(the run record or None, the path looked at, a plain-English problem or None).

    A record written by an older version of the program is reported as out of date, not as a crash.
    """
    path = Path(os.environ.get("CELLPOC_RECORD", str(DEFAULT_RECORD)))
    if path.is_dir():
        path = path.joinpath(run_store.store.RECORD_NAME)
    if not path.exists():
        return None, path, "There is no run record to show yet."
    try:
        return _read(str(path), path.stat().st_mtime), path, None
    except Exception:  # noqa: BLE001 - any failure to read means the file is unusable
        return None, path, "The run record on disk is out of date or damaged (it was probably written by an older version)."
