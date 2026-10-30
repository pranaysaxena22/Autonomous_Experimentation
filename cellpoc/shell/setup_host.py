"""The Setup page of the unified app (Stage B): the setup app's ten screens, drawn inside this app.

The screens, their checks and their buttons are the setup app's own (cellpoc.setup_app.app.embedded draws exactly what the stand-alone app draws, minus its page settings, header and banner).
This file adds only the illustrative label (once, as on every other page) and puts the dark look back over the setup app's style sheet, which is drawn for a light page.
It starts no process and touches no file; the setup app's own code does that, as it always has.
"""
from __future__ import annotations

import streamlit as st

from cellpoc.dashboard import style as dashboard_style
from cellpoc.setup_app.app import embedded
from cellpoc.shell import context, style


def render() -> None:
    record, path = context.load_record()
    dashboard_style.stamp(record.meta.banner)
    embedded(client=not context.developer())
    # the setup app's style sheet came after the dark look: put the dark look over it again (a style sheet draws nothing by itself)
    st.markdown(style.CSS, unsafe_allow_html=True)
