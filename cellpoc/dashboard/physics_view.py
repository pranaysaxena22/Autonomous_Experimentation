"""The 'Physics (MuJoCo)' page (platform runs only): shows the animated pictures and the physics checks that were written next to the run record.

MuJoCo is a physics engine; the pictures are two trials of the run (one with a jam) played by an arm in a MuJoCo model of the same cell. Everything on this page was worked out in advance and saved as files next to the run record
(run_app.bat does it the first time); this page only places them on the screen. Nothing here is worked out.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import style

PICTURES = ("physics_view_1.webp", "physics_view_2.webp")
SUMMARY = "physics_summary.md"


def render(record, record_path) -> None:
    style.stamp(record.meta.banner)
    st.subheader("Physics view of this run (MuJoCo)")
    st.caption(record.platform.label)
    folder = Path(record_path).parent
    summary = folder.joinpath(SUMMARY)
    if not summary.exists():
        st.warning("The MuJoCo view has not been drawn for this run yet. Double-click run_app.bat (it draws it the first time, about two minutes) or make_physics_view.bat, then reload this page.")
        return
    for picture in PICTURES:
        image = folder.joinpath(picture)
        if image.exists():
            st.caption(folder.joinpath(picture.replace(".webp", ".txt")).read_text(encoding="utf-8"))
            st.image(str(image))
    st.markdown(summary.read_text(encoding="utf-8"))