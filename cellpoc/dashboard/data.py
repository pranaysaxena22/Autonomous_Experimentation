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
    """(the run record or None if there is none yet, the path that was looked at)."""
    path = Path(os.environ.get("CELLPOC_RECORD", str(DEFAULT_RECORD)))
    if path.is_dir():
        path = path.joinpath(run_store.store.RECORD_NAME)
    if not path.exists():
        return None, path
    return _read(str(path), path.stat().st_mtime), path
