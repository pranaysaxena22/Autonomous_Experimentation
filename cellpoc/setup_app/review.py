"""Screen 10: every message grouped by screen, saving, and the preview of what the proof of concept would use.

Saving is disabled while any error remains, and writes only into the setups folder. The preview is text on the page: it is
never written to config/settings.yaml or anywhere else.
"""
from __future__ import annotations

import streamlit as st

from cellpoc.setup import (PROJECT_ROOT, SCREENS, SETUP_FILE_SCREEN, Problem, SetupFileError, load_setup, save_setup,
                           to_poc_settings)
from cellpoc.setup.files import SETUPS_FOLDER

from . import run_this, state, style

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


def _do_save(name: str, setup: dict, problems: list[Problem]) -> str | None:
    """Save the setup into the setups folder; returns the path relative to the project (for the run), or None when saving was refused (the reason is shown)."""
    try:
        path = save_setup(setup, name, problems=problems)
        block = (load_setup(path).setup or {}).get("saved", {})
        st.session_state["saved"] = (f"{SETUPS_FOLDER}/{path.name}", "\n".join(f"{k}: {v}" for k, v in block.items()))
        return f"{SETUPS_FOLDER}/{path.name}"
    except SetupFileError as error:
        st.session_state["saved"] = None
        style.message("error", str(error))
        return None


def _client() -> bool:
    """True inside the unified app's client view, which leaves out the technical detail (the stand-alone setup app and the developer view keep it)."""
    return bool(st.session_state.get("client_view"))


def _save(problems: list[Problem], setup: dict) -> tuple[str, int, bool]:
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
        _do_save(name, setup, problems)
    if st.session_state.get("saved"):
        where, details = st.session_state["saved"]
        if _client():
            st.markdown("**Saved.**")
        else:
            st.markdown(f"**Saved to {where}.** What was recorded about the save (no personal names):")
            st.code(details, language="yaml")
    return name, errors, replace_ok


def _run(problems: list[Problem], setup: dict, name: str, errors: int, replace_ok: bool) -> None:
    """The 'Run this setup' part: only offered when the setup has no errors and the converter can represent it; it saves the setup (the same save as above) and simulates the saved file."""
    conversion = to_poc_settings(setup, problems)
    reasons = [f"This setup cannot be simulated yet: {note.text}" for note in conversion.notes if note.level == "blocking"]
    if errors:
        reasons = ["Fix the errors first: a setup with errors cannot be saved or run."] + reasons
    run_this.intro(not errors and conversion.ok, reasons)
    if st.button("Save and run it", key="save_and_run", disabled=bool(errors) or not conversion.ok or not replace_ok):
        saved = _do_save(name, setup, problems)
        if saved:
            with st.spinner("Simulating the run (a few seconds)..."):
                ok, lines = run_this.simulate(saved)
            st.session_state.update(run_result={"ok": ok, "lines": lines, "file": saved}, dashboard_started=False, live_started=False)
    run_this.show_result()


def _preview(problems: list[Problem], setup: dict) -> None:
    if _client():
        return
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
    name, errors, replace_ok = _save(problems, setup)
    _run(problems, setup, name, errors, replace_ok)
    _preview(problems, setup)
