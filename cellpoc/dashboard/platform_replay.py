"""The '3D replay' page (platform runs only): shows the replay file that was written next to the run record, and what each trial of the run did, as the record states it.

The replay file replays the executed timelines it contains and works offline; this page only places it on the screen. Nothing here is worked out: the lines come from the record.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import style


HIDE_BAND = "<style>header .band{display:none}</style>"          # the replay's own title band, hidden when the page sits inside the unified app (whose top bar and page heading already say it)


def render(record, record_path, embedded: bool = False) -> None:
    """With embedded=False (the default, and what the old dashboards use) the replay file is shown exactly as saved; embedded=True only adds the one style rule that hides its title band and trims the frame."""
    style.stamp(record.meta.banner)
    info = record.platform
    st.subheader("3D replay of this run")
    st.caption(info.label)
    replay = Path(record_path).parent.joinpath(info.replay_file)
    if replay.exists():
        # Use the Play button, the Trials strip and the Camera list inside the picture. It runs on this computer; nothing is fetched from the internet.
        page = replay.read_text(encoding="utf-8")
        if embedded:
            components.html(page.replace("</head>", HIDE_BAND + "</head>", 1), height=1040, scrolling=True)
        else:
            components.html(page, height=1100, scrolling=True)
    else:
        st.warning(f"The 3D replay file was not found next to the run record (looked for {replay}). Double-click make_platform_demo.bat to build it again.")
    st.subheader("What happened, trial by trial")
    st.caption(f"Plans were run by: {info.executor}. Each line says what the planner made and what the executor reported.")
    for row in info.trial_rows:
        st.markdown(f"- {row}")
