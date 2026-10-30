"""The setup app: ten screens that edit a setup, show the checker's messages beside each field, and save or preview it.

It calculates no results. Everything it knows about what is acceptable comes from cellpoc.setup (the same checker the
health check uses). Run it with `streamlit run setup_app.py` (or the launcher).

Web addresses that open a screen or a setup directly (used for bookmarks and for the screenshot tool):
  ?screen=3            show screen 3 of 10
  ?start=blank         begin with a blank setup       ?start=example   begin with the bundled example (?start=example2 and ?start=example3 for the other two)
  ?open=my-study       open setups/my-study.yaml
"""
from __future__ import annotations

import streamlit as st

from cellpoc.setup import SCREENS

from . import state, style
from .review import review
from .screens import SCREEN_FUNCTIONS
from .widgets import Form

LAST = len(SCREENS) - 1


def _apply_web_address() -> None:
    """Honour ?start=, ?open= and ?screen= once, when the page is first opened."""
    if st.session_state["linked"]:
        return
    st.session_state["linked"] = True
    query = st.query_params
    if query.get("start") == "blank":
        state.start_blank()
    elif str(query.get("start", "")).startswith("example"):          # ?start=example (the standard one), ?start=example2, ?start=example3
        suffix = str(query.get("start"))[len("example"):]
        state.load_example(number=int(suffix) if suffix.isdigit() else None)
    elif query.get("open"):
        state.open_saved(query.get("open"))
    if st.session_state["setup"] is not None and str(query.get("screen", "")).isdigit():
        st.session_state["screen"] = min(max(int(query["screen"]), 1), len(SCREENS)) - 1


def _sidebar(problems) -> None:
    with st.sidebar:
        st.markdown("### Start")
        st.button("Start blank", key="start_blank", on_click=state.start_blank, width="stretch")
        labels = state.example_labels()
        if len(labels) > 1:
            st.selectbox("Illustrative example", labels, key="example_choice", help="Three illustrative studies to start from: they differ in run length, faults, targets and ranges.")
        st.button("Load example", key="load_example", on_click=state.load_example, args=("example_choice",), width="stretch")
        names = state.saved_names()
        if names:
            chosen = st.selectbox("Open a saved setup", names, index=None, placeholder="Choose a file", key="open_choice")
            st.button("Open", key="open_saved", disabled=chosen is None, on_click=state.open_saved, args=(chosen,), width="stretch")
        else:
            st.caption("No saved setups yet. Saved setups appear here.")
        if problems is None:
            return
        st.markdown("### Screens")
        clean = sum(not any(state.counts(problems, name)) for name in SCREENS)
        st.progress(clean / len(SCREENS), text=f"{clean} of {len(SCREENS)} screens have no errors or warnings")
        for number, name in enumerate(SCREENS):
            summary = state.count_text(*state.counts(problems, name))
            here = number == st.session_state["screen"]
            st.button(f"{'► ' if here else ''}{number + 1}. {name}: {summary}" + (" (you are here)" if here else ""),
                      key=f"nav_{number}", on_click=state.go, args=(number,), type="primary" if here else "secondary", width="stretch")


def _welcome() -> None:
    st.markdown("### Start a setup")
    st.markdown("Choose **Start blank** to fill everything in yourself, or **Load example** to begin from the bundled illustrative example. "
                "Both buttons are in the panel on the left. You can also open a setup you saved earlier.")
    for problem in st.session_state["load_problems"]:
        style.message(problem.level, problem.message)
    labels = state.example_labels()
    if len(labels) > 1:
        st.selectbox("Illustrative example", labels, key="welcome_example_choice")
    left, right = st.columns(2)
    with left:
        st.button("Start blank", key="welcome_blank", on_click=state.start_blank, width="stretch")
    with right:
        st.button("Load example", key="welcome_example", on_click=state.load_example, args=("welcome_example_choice",), width="stretch")


def _screen(problems, layout) -> None:
    setup = st.session_state["setup"]
    number = st.session_state["screen"]
    name = SCREENS[number]
    st.progress((number + 1) / len(SCREENS), text=f"Screen {number + 1} of {len(SCREENS)}: {name}")
    st.markdown(f"## {number + 1}. {name}")
    errors, warnings = state.counts(problems, name)
    st.markdown(f"<span class='sa-count'>This screen: {state.count_text(errors, warnings)}.</span>", unsafe_allow_html=True)
    if number == LAST:
        review(problems, setup)
    else:
        form = Form(setup, problems, layout)
        SCREEN_FUNCTIONS[number](form)
        left_over = form.leftovers(name)
        if left_over:
            st.markdown("#### Other messages on this screen")
            for problem in left_over:
                style.message(problem.level, problem.message)
    back, _, forward = st.columns([1, 4, 1])
    with back:
        st.button("Back", key="back", disabled=number == 0, on_click=state.go, args=(number - 1,), width="stretch")
    with forward:
        st.button("Next", key="next", disabled=number == LAST, on_click=state.go, args=(number + 1,), width="stretch")


def _body() -> None:
    """Everything under the header and the banner: the welcome page, or the working setup with its side panel and the current screen."""
    setup = st.session_state["setup"]
    if setup is None:
        _sidebar(None)
        _welcome()
        return
    problems, layout = state.check()
    status = setup.get("project", {}).get("data_status") if isinstance(setup.get("project"), dict) else None
    style.status(f"Data status of this setup: {status if isinstance(status, str) else 'not chosen'}. Working copy from {st.session_state['origin']}; "
                 "changes stay in this window until you save on the last screen.")
    _sidebar(problems)
    _screen(problems, layout)


def main() -> None:
    display = style.project_display()
    style.apply(display)
    state.init()
    _apply_web_address()
    style.header()
    style.banner(display["banner"])
    _body()


def embedded(client: bool = False) -> None:
    """The same screens inside another app (the unified app, Stage B) that has already set the page up and draws its own header and illustrative label.
    It adds this app's style sheet and draws no header, banner or page settings; everything else is exactly what main() draws. `client` (the unified app's client view) leaves out the technical detail: the YAML preview, file paths and launcher names."""
    st.markdown(style.css(style.project_display()), unsafe_allow_html=True)
    state.init()
    st.session_state["client_view"] = client
    st.session_state["inside_unified_app"] = True          # tells the 'Run this setup' result not to offer the two buttons that open separate windows (the app has its own Live run page)
    _apply_web_address()
    _body()
