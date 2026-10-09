"""Tests of the setup app, driven by Streamlit's own test harness (no browser, no network).

What this can check: that every screen draws without an error, that messages appear as labelled text next to their field and again
on the Review screen, that Save is switched off while errors remain and writes only into setups/, that the preview never writes
config/settings.yaml, that nothing is fetched from the internet, and that damaged setups never crash a screen.
What it cannot check: how the page LOOKS (colours, spacing, fonts actually shown, whether text is cut off, how it feels on a
small window). The by-eye checklist in docs/setup_app.md covers that, and screenshots can be taken with tools/take_setup_screenshots.py.
"""
from __future__ import annotations

import ast
import hashlib
import random
import re
import shutil
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from cellpoc.setup import PROJECT_ROOT, SCREENS, load_setup, save_setup, validate
from cellpoc.setup_app import style
from checks import setup_cases, setup_mutation
from checks.common import Checklist

APP = PROJECT_ROOT / "setup_app.py"
APP_PACKAGE = PROJECT_ROOT / "cellpoc" / "setup_app"
SETTINGS = PROJECT_ROOT / "config" / "settings.yaml"
LABEL = re.compile(r"<b>(Error|Warning|Note):</b>")


def new_app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=90).run()


def ordered(node) -> list:
    """Every element on the page in the order it is drawn."""
    found = []
    for child in node.children.values():
        found.append(child)
        if isinstance(child, Block):
            found.extend(ordered(child))
    return found


def messages(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown if 'class="sa-msg"' in m.value]


def goto(at: AppTest, screen: int) -> AppTest:
    return at.button(key=f"nav_{screen}").click().run()


def project_snapshot() -> dict[str, tuple[int, int]]:
    """Name, size and modified time of every file in the project that is not a cache, the environment or git's own folder."""
    skip = {".venv", ".git", "__pycache__", "runs", "chrome_profile"}
    found = {}
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and not (skip & set(path.relative_to(PROJECT_ROOT).parts)):
            stat = path.stat()
            found[path.relative_to(PROJECT_ROOT).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return found


def exceptions(at: AppTest) -> list[str]:
    return [str(e.value)[:150] for e in at.exception]


def run(cl: Checklist) -> None:
    # ---------- starting
    at = new_app()
    welcome_buttons = {b.key for b in at.button}
    cl.record(not at.exception and {"start_blank", "load_example", "welcome_blank", "welcome_example"} <= welcome_buttons,
              "The app opens with no setup loaded and offers both 'Start blank' and 'Load example'", "; ".join(exceptions(at)))
    banner_text = style.project_display()["banner"]
    cl.record(any("sa-banner" in m.value and banner_text in m.value for m in at.markdown) and re.search("illustrative|synthetic", banner_text, re.I) is not None,
              "The 'illustrative' banner is on the opening page", banner_text)

    # ---------- example loaded: every screen
    at.button(key="load_example").click().run()
    problems_seen, banner_ok, progress_ok, nav_ok, crashed = [], [], [], [], []
    for number in range(len(SCREENS)):
        goto(at, number)
        crashed += exceptions(at)
        banner_ok.append(any("sa-banner" in m.value and banner_text in m.value for m in at.markdown))
        progress_ok.append(any(f"Screen {number + 1} of {len(SCREENS)}: {SCREENS[number]}" in str(p.text) for p in at.get("progress")) if at.get("progress") else False)
        labels = [b.label for b in at.sidebar.button if b.key == f"nav_{number}"]
        nav_ok.append(bool(labels) and f"{number + 1}. {SCREENS[number]}: " in labels[0] and "(you are here)" in labels[0])
    cl.record(not crashed, "With the example loaded, all ten screens draw without an error", "; ".join(crashed[:2]))
    cl.record(all(banner_ok), "The 'illustrative' banner is on every one of the ten screens", f"{sum(banner_ok)} of 10")
    cl.record(all(progress_ok) and all(nav_ok), "Every screen shows where you are (Screen n of 10) and the side list marks the current screen in words",
              f"{sum(progress_ok)} of 10 headings, {sum(nav_ok)} of 10 side entries")

    # ---------- counts on each screen
    goto(at, 0)
    counts_text = [b.label for b in at.sidebar.button if b.key.startswith("nav_")]
    cl.record(len(counts_text) == 10 and all(("no errors or warnings" in t or "error" in t or "warning" in t) for t in counts_text) and "1 warning" in counts_text[4],
              "Each screen's entry in the side list states its count of errors and warnings in words (the example has 1 warning, on Equipment)", counts_text[4] if len(counts_text) > 4 else "")

    # ---------- break a field: message beside the field, label as text, again on Review
    goto(at, 1)
    ver = at.session_state["ver"]
    low_key = f"w{ver}|ingredients[0].min"
    at.number_input(key=low_key).set_value(40.0).run()
    flat = ordered(at.main)
    index = next((i for i, e in enumerate(flat) if getattr(e, "key", None) == f"w{at.session_state['ver']}|ingredients[0].min"), None)
    beside = flat[index + 1].value if index is not None and index + 1 < len(flat) and hasattr(flat[index + 1], "value") else ""
    cl.record('class="sa-msg"' in beside and LABEL.search(beside) is not None and "must be below" in beside and "Error:" in beside,
              "Breaking a value (a lowest value above its highest) shows an 'Error:' message in words, directly under that field", re.sub(r"<[^>]+>", "", beside)[:140])
    nav = [b.label for b in at.sidebar.button if b.key == "nav_1"][0]
    cl.record("error" in nav, "The screen's count in the side list changes in words when a field is broken", nav)
    goto(at, 9)
    review_text = " ".join(m.value for m in at.markdown)
    cl.record("Ingredients" in review_text and "Lowest value" in review_text and "must be below" in review_text,
              "The Review screen lists the same message again, grouped under its screen and naming the field", "")
    save = at.button(key="save")
    cl.record(save.disabled, "'Save setup' is switched off while any error remains, and the screen says so in words",
              "Saving is switched off" if "Saving is switched off" in review_text else "text missing")

    # ---------- fix it, save, only setups/ is written, settings.yaml untouched
    goto(at, 1)
    at.number_input(key=f"w{at.session_state['ver']}|ingredients[0].min").set_value(10.0).run()
    goto(at, 9)
    name = "zz-apptest-" + uuid.uuid4().hex[:8]
    before_snapshot = project_snapshot()
    settings_before = hashlib.sha256(SETTINGS.read_bytes()).hexdigest()
    at.text_input(key=f"save_name|{at.session_state['load_id']}").set_value(name).run()
    enabled = not at.button(key="save").disabled
    at.button(key="save").click().run()
    after_snapshot = project_snapshot()
    new_files = sorted(set(after_snapshot) - set(before_snapshot))
    changed = sorted(k for k in before_snapshot if before_snapshot[k] != after_snapshot.get(k))
    cl.record(enabled and new_files == [f"setups/{name}.yaml"] and not changed,
              "With no errors, Save writes exactly one new file, inside setups/, and changes no other file in the project", f"new: {new_files}; changed: {changed}")
    cl.record(hashlib.sha256(SETTINGS.read_bytes()).hexdigest() == settings_before, "config/settings.yaml is unchanged after saving", "")
    code_blocks = " ".join(c.value for c in at.code)
    cl.record("PREVIEW ONLY" in code_blocks and "design_space:" in code_blocks and "saved_at:" in code_blocks,
              "The Review screen shows the proof-of-concept preview (labelled PREVIEW ONLY) and what was recorded about the save", "")
    cl.record(not any(p.level == "error" for p in validate(load_setup(PROJECT_ROOT / "setups" / f"{name}.yaml").setup, base_dir=PROJECT_ROOT / "setups")),
              "The file that was saved reads back and passes the checks", "")

    # ---------- open the saved file again; refuse a newer format
    at2 = new_app()
    options = at2.selectbox(key="open_choice").options if at2.selectbox else []
    at2.selectbox(key="open_choice").select(name).run()
    at2.button(key="open_saved").click().run()
    loaded_ok = at2.session_state["setup"] is not None and at2.session_state["origin"] == f"setups/{name}.yaml"
    cl.record(name in options and loaded_ok, "A saved setup appears in 'Open a saved setup' and opens", f"{len(options)} saved setup(s) listed")
    newer = PROJECT_ROOT / "setups" / f"{name}-newer.yaml"
    newer.write_bytes((PROJECT_ROOT / "setups" / f"{name}.yaml").read_bytes().replace(b"format_version: 1", b"format_version: 2"))
    at3 = new_app()
    at3.selectbox(key="open_choice").select(f"{name}-newer").run()
    at3.button(key="open_saved").click().run()
    shown = " ".join(m.value for m in at3.markdown)
    cl.record(at3.session_state["setup"] is None and "newer format" in shown and not at3.exception,
              "A setup saved in a newer format than the program knows is refused on opening, with the plain message", "")
    for path in (PROJECT_ROOT / "setups").glob(f"{name}*.yaml"):
        path.unlink()
    folder = PROJECT_ROOT / "setups"
    try:
        if folder.is_dir() and not any(folder.iterdir()) and "setups" not in {p.split("/")[0] for p in before_snapshot}:
            shutil.rmtree(folder)
    except OSError:
        pass            # OneDrive can hold a folder for a moment; an empty setups/ folder is harmless (and ignored by git)

    # ---------- blank start
    at = new_app()
    at.button(key="start_blank").click().run()
    blank_errors = []
    for number in range(len(SCREENS)):
        goto(at, number)
        blank_errors += exceptions(at)
    goto(at, 9)
    total = " ".join(m.value for m in at.markdown)
    cl.record(not blank_errors and at.button(key="save").disabled and "In total:" in total and "errors" in total,
              "'Start blank' draws all ten screens, lists what is still to do on Review, and Save is switched off", "; ".join(blank_errors[:2]))
    all_labelled = all(LABEL.search(m) for m in messages(at))
    cl.record(bool(messages(at)) and all_labelled, "Every message on the page carries its label as a word (Error, Warning or Note), not only a colour", f"{len(messages(at))} messages checked")

    # ---------- web addresses
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.query_params["start"], at.query_params["screen"] = "example", "5"
    at.run()
    cl.record(at.session_state["screen"] == 4 and at.session_state["origin"] == "the bundled example" and not at.exception,
              "A web address such as ?start=example&screen=5 opens that screen with that setup", "")

    # ---------- what the person typed is escaped
    at = new_app()
    at.button(key="load_example").click().run()
    goto(at, 0)
    at.text_input(key=f"w{at.session_state['ver']}|display.accent_colour").set_value("<b>x</b>").run()
    text = " ".join(messages(at))
    cl.record("&lt;b&gt;x&lt;/b&gt;" in text and "<b>x</b>" not in text, "Text a person types (here an HTML tag) is shown as plain text in messages, never run", "")

    # ---------- structural edits
    goto(at, 1)
    before = len(at.session_state["setup"]["ingredients"])
    at.button(key=f"w{at.session_state['ver']}|ingredients|add").click().run()
    added = len(at.session_state["setup"]["ingredients"]) == before + 1 and not at.exception
    removed_first = at.button(key=f"w{at.session_state['ver']}|ingredients[{before}]|remove")
    removed_first.click().run()
    cl.record(added and len(at.session_state["setup"]["ingredients"]) == before and not at.exception,
              "Adding an ingredient adds a row of fields with its own messages; removing it takes it away again", "")
    goto(at, 3)
    goal_key = f"w{at.session_state['ver']}|targets.constraints[0].goal"
    at.selectbox(key=goal_key).select("between").run()
    constraint = at.session_state["setup"]["targets"]["constraints"][0]
    cl.record("low" in constraint and "high" in constraint and "value" not in constraint and not at.exception,
              "Changing a target's goal to 'between' swaps its number boxes (lowest and highest instead of one limit)", "")

    # ---------- offline, own fonts and colours
    sources = {p: p.read_text(encoding="utf-8") for p in list(APP_PACKAGE.glob("*.py")) + [APP]}
    online = [f"{p.name}: {m}" for p, t in sources.items() for m in re.findall(r"https?://[^\s'\"<>)]+|@import|<script|googleapis|cdn\.", t)]
    cl.record(not online, "The app's code contains no web address, script tag, web font or CDN: it works offline", "; ".join(online[:3]) if online else f"{len(sources)} files read")
    pages = " ".join(m.value for m in at.markdown)
    cl.record(not re.search(r"https?://", pages) and "url('app/static/OpenSans.ttf')" in pages, "The page's own text and styles name no web address; the font is the bundled Open Sans file", "")
    shown = style.project_display()
    cl.record(shown["accent_colour"] in pages and shown["font"] in pages,
              "The accent colour and font on the page are the project settings' (config/settings.yaml)", f"{shown['accent_colour']}, {shown['font']}")
    other = style.css({"banner": "x", "accent_colour": "#123456", "font": "Test Font"})
    cl.record("#123456" in other and "Test Font" in other, "Self-test: changing the display settings changes the page's colour and font", "")

    # ---------- no calculations
    banned = {"numpy", "scipy", "pandas", "sklearn", "statsmodels", "random", "statistics", "itertools", "datetime"}
    heavy = []
    for path, text in sources.items():
        for node in ast.walk(ast.parse(text)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else ([node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            heavy += [f"{path.name}: {n}" for n in names if n.split(".")[0] in banned]
    cl.record(not heavy, "The app imports no calculation libraries (no numpy, scipy, pandas, statistics, random): it validates, saves and previews only", "; ".join(heavy[:3]))

    # ---------- damaged setups never crash a screen
    rng = random.Random(4242)
    crashes, drawn = [], 0
    for index in range(25):
        broken = setup_cases.fresh()
        steps = [setup_mutation.mutate_once(broken, rng) for _ in range(rng.choice([1, 2, 3]))]
        harness = new_app()
        harness.session_state["setup"] = broken
        harness.session_state["origin"] = "a damaged setup"
        harness.session_state["base_dir"] = setup_cases.EXAMPLES
        for number in range(len(SCREENS)):
            harness.session_state["screen"] = number
            harness.run()
            drawn += 1
            if harness.exception:
                crashes.append(f"#{index} screen {number + 1} after {'; '.join(steps)} -> {exceptions(harness)[0]}")
                break
    cl.record(not crashes, f"25 damaged setups (fields deleted, values swapped, junk written) are drawn on all ten screens without an error ({drawn} screens drawn)",
              "; ".join(crashes[:2]))
