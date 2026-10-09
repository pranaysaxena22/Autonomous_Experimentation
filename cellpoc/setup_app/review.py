"""Screen 10: every message grouped by screen, saving, and the preview of what the proof of concept would use.

Saving is disabled while any error remains, and writes only into the setups folder. The preview is text on the page: it is
never written to config/settings.yaml or anywhere else.
"""
from __future__ import annotations

import streamlit as st

from cellpoc.setup import (PROJECT_ROOT, SCREENS, SETUP_FILE_SCREEN, Problem, SetupFileError, load_setup, save_setup,
                           to_poc_settings)
from cellpoc.setup.files import SETUPS_FOLDER

from . import state, style

LAST = "Review and save"


def _grouped(problems: list[Problem]) -> None:
    st.markdown("#### Everything that needs a look, by screen")
    shown_any = False
    for screen in [SETUP_FILE_SCREEN] + SCREENS[:-1]:
        here = [p for p in problems if p.screen == screen]
        if not here:
            continue
        shown_any = True
        errors, warnings = state.counts(here, screen)
        left, right = st.columns([5, 1])
        with left:
            st.markdown(f"**{screen}**: {state.count_text(errors, warnings)}" + (f", {sum(p.level == 'note' for p in here)} note(s)" if any(p.level == "note" for p in here) else ""))
        with right:
            if screen in SCREENS:
                st.button(f"Go to screen {SCREENS.index(screen) + 1}", key=f"goto_{screen}", on_click=state.go, args=(SCREENS.index(screen),))
        for p in here:
            style.message(p.level, p.message)
    if not shown_any:
        st.markdown("No messages: nothing needs a look.")


def _save(problems: list[Problem], setup: dict) -> None:
    st.markdown("#### Save")
    errors = sum(p.level == "error" for p in problems)
    name = st.text_input("Save as (a file name)", value=state.default_name(setup), key=f"save_name|{st.session_state['load_id']}",
                         help="Lowercase letters, digits, '-' and '_'. The file is saved in the setups folder and nowhere else.")
    target = PROJECT_ROOT / SETUPS_FOLDER / f"{name}.yaml"
    replace_ok = True
    if state.SAVED_NAME.match(name) and target.exists():
        replace_ok = st.checkbox(f"A setup called {name} already exists. Replace it.", key=f"replace|{name}")
    if errors:
        st.markdown(f"**Saving is switched off** while {errors} error{'s' if errors != 1 else ''} remain. Fix them (the list above says where). Warnings do not stop you saving.")
    if st.button("Save setup", key="save", disabled=bool(errors) or not replace_ok):
        try:
            path = save_setup(setup, name, problems=problems)
            block = (load_setup(path).setup or {}).get("saved", {})
            st.session_state["saved"] = (f"{SETUPS_FOLDER}/{path.name}", "\n".join(f"{k}: {v}" for k, v in block.items()))
        except SetupFileError as error:
            st.session_state["saved"] = None
            style.message("error", str(error))
    if st.session_state.get("saved"):
        where, details = st.session_state["saved"]
        st.markdown(f"**Saved to {where}.** What was recorded about the save (no personal names):")
        st.code(details, language="yaml")


def _preview(problems: list[Problem], setup: dict) -> None:
    conversion = to_poc_settings(setup, problems)
    with st.expander("Preview: what the proof of concept would use (illustrative; not saved)"):
        st.caption("A preview only. It is shown here and never written to config/settings.yaml or to any file.")
        for note in conversion.notes:
            style.message("warning" if note.level == "blocking" else "note", f"{note.label}: {note.text}")
        if conversion.ok:
            st.code(conversion.yaml_text(), language="yaml")


def review(problems: list[Problem], setup: dict) -> None:
    total_errors = sum(p.level == "error" for p in problems)
    total_warnings = sum(p.level == "warning" for p in problems)
    st.markdown(f"**In total: {state.count_text(total_errors, total_warnings)}.** "
                + ("Saving is switched off until the errors are fixed." if total_errors else "The setup can be saved."))
    _grouped(problems)
    _save(problems, setup)
    _preview(problems, setup)
