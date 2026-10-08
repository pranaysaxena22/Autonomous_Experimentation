"""Page 6 - What this shows and does not show, in plain language (the same text as the scenario page's Limitations)."""
from __future__ import annotations

import streamlit as st

from . import style


def render(record) -> None:
    style.stamp(record.meta.banner)
    if record.about is None:
        st.info("This run record does not carry the explanatory text. Rebuild it with build_demo.bat.")
        return
    st.subheader("What this shows")
    for line in record.about.shows:
        st.markdown(f"- {line}")
    st.subheader("What it does not show")
    for line in record.about.does_not_show:
        st.markdown(f"- {line}")
