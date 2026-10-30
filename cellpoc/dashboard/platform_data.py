"""The 'Data and model' page (platform runs only): how the pieces of the platform connect for this run, what the data reader and the modelling step made of the data file, and what this run does not show.

All of it is text written into the record in advance (cellpoc/platform_info.py); this page only displays it.
"""
from __future__ import annotations

import streamlit as st

from . import style


def render(record) -> None:
    style.stamp(record.meta.banner)
    info = record.platform
    st.subheader("How the pieces connect in this run")
    st.caption(info.label)
    for line in info.pipeline:
        st.markdown(f"- {line}")
    st.subheader("The data file (as the reader found it)")
    for line in info.data_lines:
        st.markdown(f"- {line}")
    st.subheader("What the modelling step made of it")
    for line in info.model_lines:
        st.markdown(f"- {line}")
    st.subheader("What this run does not show")
    for line in info.limits:
        st.markdown(f"- {line}")
