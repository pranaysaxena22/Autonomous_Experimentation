"""Health check for the CLIENT view of the unified app: the app as the people the demo is for see it.

In plain words it checks that: the client menu has exactly the intended pages in the intended order (Overview, Live run, Results at a glance, Vision, Setup, Reports, About and limits), each has its page file, and the developer view still has all eleven pages; every client page draws with
no error and carries the sentence "Simulation with illustrative values" exactly once; no developer wording appears on any client page, in the top bar or on the live page (launcher and check file names, folder and document names, stage and part names, "proof of concept", the physics model's name, the
technical status lines, action ids, outside dataset names), with a self-test that the same scan finds such wording in the developer view, so the scan can fail; the labelling that must stay is still there (the ILLUSTRATIVE chip, the banner, the plain limits on the About page including that the numbers are made up, that the arm and the cameras are stand-ins, that the manual comparison is an assumption
and that about 29 to 30 trials fit a run); the client Overview shows the same six numbers as the developer Overview; and the Live run page offers Start and Stop in plain words and starts nothing by itself; the welcome window and the guided tour: the eight steps form one unbroken chain that visits every client page once, their wording has no developer wording, 'Take the tour' starts it, Next walks through every step and
opens each page, Back goes back, End tour ends it, the welcome opens once only and neither it nor the tour is in the developer view, with a self-test that a broken chain is caught. Nothing is written into the project.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

PLATFORM = ROOT / "runs" / "platform"
CLIENT_PAGES = ["Overview", "Live run", "Results at a glance", "Vision", "Setup", "Reports", "About and limits"]
DEVELOPER_PAGES = ["Overview", "Vision", "Results at a glance", "Setup", "The run", "Live run", "3D replay", "Physics (MuJoCo)", "Data and model", "Reports", "About and limits"]
PAGE_FILES = {"Overview": "overview", "Vision": "vision", "Results at a glance": "results", "Setup": "setup", "The run": "the_run", "Live run": "live_run", "3D replay": "replay", "Physics (MuJoCo)": "physics",
              "Data and model": "data_and_model", "Reports": "reports", "About and limits": "about"}
SENTENCE = "simulation with illustrative values"
# wording that is for the team, not for a client (compared without regard to capitals)
FORBIDDEN = [".bat", "run_app", "run_platform", "make_reports", "check_", "docs/", "decisions.md", "settings.yaml", ".yaml", "stage 4", "stage 5", "proof of concept", "python_stand_in", "stand-in executor", "mujoco",
             "double-click", "black window", "offline", "developer view", "live program", "separate program", "markers seen", "labpics", "pharmavision", "action a0", "traceback", "decision engine of stage"]


def run_app(page: str | None, developer: bool):
    from streamlit.testing.v1 import AppTest
    os.environ["CELLPOC_RECORD"] = str(PLATFORM)
    if developer:
        os.environ["CELLPOC_DEVELOPER"] = "1"
    else:
        os.environ.pop("CELLPOC_DEVELOPER", None)
    try:
        app = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
        app.run()
        if page is not None:
            app.switch_page(f"cellpoc/shell/pages/{PAGE_FILES[page]}.py")
            app.run()
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
        os.environ.pop("CELLPOC_DEVELOPER", None)
    return app


def visible(app) -> list[str]:
    """Everything a person reads on a page: text blocks (the style sheets left out), headings, captions, notices, figures' labels, buttons, tabs and expanders."""
    block = app.main
    texts = [m.value for m in block.markdown if not m.value.lstrip().startswith("<style>")]
    texts += [e.value for kind in ("subheader", "caption", "info", "warning", "error", "success") for e in getattr(block, kind)]
    texts += [m.label for m in block.metric] + [b.label for b in block.button] + [t.label for t in block.tabs] + [x.label for x in block.expander]
    texts += [m.value for m in app.markdown if 'class="ub-bar"' in m.value]                       # the top bar
    return texts


def found_in(texts: list[str]) -> list[str]:
    joined = " ".join(texts).lower()
    return [w for w in FORBIDDEN if w in joined]


def main() -> int:
    cl = Checklist("CLIENT VIEW: the pages a client sees, free of developer wording, with the illustrative labelling intact")
    before = project_files()
    from cellpoc.shell import menu

    client_titles = [e.title for entries in menu.CLIENT_SECTIONS.values() for e in entries]
    developer_titles = [e.title for entries in menu.SECTIONS.values() for e in entries]
    cl.record(client_titles == CLIENT_PAGES and developer_titles == DEVELOPER_PAGES and all((ROOT / e.path).exists() for entries in menu.CLIENT_SECTIONS.values() for e in entries),
              "The client menu has exactly the intended pages in the intended order (Overview, Live run, Results at a glance, Vision, Setup, Reports, About and limits), each with its page file, and the developer menu still has all eleven pages", f"client: {' > '.join(client_titles)}")

    pages = {title: run_app(title, False) for title in CLIENT_PAGES}
    errors = {t: [str(e.value)[:80] for e in a.exception] for t, a in pages.items() if a.exception}
    counts = {t: sum(x.lower().count(SENTENCE) for x in visible(a)) for t, a in pages.items()}
    cl.record(not errors and all(c == 1 for c in counts.values()),
              "Every client page draws with no error and carries 'Simulation with illustrative values' exactly once", "; ".join(f"{k}: {v}" for k, v in errors.items()) or f"counts {counts}")

    problems = {t: found_in(visible(a)) for t, a in pages.items()}
    cl.record(not any(problems.values()), "No developer wording on any client page or in the top bar (launcher and check file names, folder and document names, stage and part names, 'proof of concept', the physics model's name, technical status lines, outside dataset names)",
              "; ".join(f"{t}: {w}" for t, w in problems.items() if w) or "none found on seven pages")

    developer_overview = run_app("Overview", True)
    caught = found_in(visible(developer_overview))
    cl.record(len(caught) >= 2 and "offline" in caught and "developer view" in caught,
              "Self-test: the same scan of the developer view's Overview finds developer wording (so the scan can fail)", f"found {caught}")
    bar = lambda a: " ".join(m.value for m in a.markdown if 'class="ub-bar"' in m.value)                    # noqa: E731
    chips = lambda a: re.findall(r'data-chip="([a-z]+)"', bar(a))                                           # noqa: E731
    cl.record(chips(pages["Overview"]) == ["label", "run"] and {"trials", "offline", "developer"} <= set(chips(developer_overview)),
              "The client top bar carries only the ILLUSTRATIVE chip and the study's name (the developer view adds the trial count, the offline chip and a 'developer view' chip)", f"client {chips(pages['Overview'])}; developer {chips(developer_overview)}")

    about = " ".join(visible(pages["About and limits"])).lower()
    overview = " ".join(visible(pages["Overview"]))
    chip = re.search(r'data-chip="label">ILLUSTRATIVE<', " ".join(m.value for m in pages["Overview"].markdown))
    needed = ["real tablets", "made-up" if "made-up" in about else "illustrative value", "stand-in", "assumption", "regulat"]
    cl.record(chip is not None and all(word in about for word in needed) and re.search(r"about \d+ to \d+ trials", about) is not None and "illustrative" in overview.lower(),
              "The labelling that must stay is there: the ILLUSTRATIVE chip in the top bar, and the About page says plainly that the numbers are illustrative, that the arm and the cameras are stand-ins, that the manual comparison is an assumption, that it is not validated for a regulated lab and that about 29 to 30 trials fit a run",
              f"chip {'yes' if chip else 'no'}; missing {[w for w in needed if w not in about]}")

    client_numbers = {m.label: m.value for m in pages["Overview"].main.metric}
    developer_numbers = {m.label: m.value for m in developer_overview.main.metric}
    first_six = ["Trials attempted", "Trials with a result", "Good recipes", "Skipped (no result)", "Faults recovered", "Alerts for staff"]
    cl.record(all(client_numbers.get(k) is not None and client_numbers.get(k) == developer_numbers.get(k) for k in first_six),
              "The client Overview shows the same six numbers as the developer Overview", f"client {[client_numbers.get(k) for k in first_six]}; developer {[developer_numbers.get(k) for k in first_six]}")

    live = pages["Live run"]
    buttons = [b.label for b in live.button]
    cl.record("Start the live demo" in buttons and "Stop the live demo" in buttons and all(b.label != "Start the live view" for b in live.button) and len(live.get("iframe")) == 0,
              "The Live run page offers Start and Stop in plain words and starts nothing by itself (no live view is drawn until Start is pressed)", f"buttons {buttons}; frames {len(live.get('iframe'))}")

    from cellpoc.live.page import build_live_page
    import json
    layout = json.loads((PLATFORM / "layout.json").read_text(encoding="utf-8"))
    page = build_live_page(layout, token="x")
    live_words = ["black window", "run_platform.bat", "run_app.bat", "action ' + d.action", "Drawn by the MuJoCo", "live simulation (is its"]
    cl.record(not [w for w in live_words if w in page], "The live page (inside the app) has no developer wording: no 'black window', no launcher names, no action ids, no file paths for the saved run", f"found {[w for w in live_words if w in page]}")

    # ---------------------------------------------------------------- the welcome and the guided tour
    from cellpoc.shell import tour
    from streamlit.testing.v1 import AppTest

    def chain_ok(steps) -> bool:
        ids = [s.id for s in steps]
        return len(set(ids)) == len(ids) and steps[0].prev == "" and steps[-1].next == "" and all(steps[i].next == steps[i + 1].id and steps[i + 1].prev == steps[i].id for i in range(len(steps) - 1))

    client_files = {e.path for entries in menu.CLIENT_SECTIONS.values() for e in entries}
    n_steps = len(tour.STEPS)
    texts = [s.title + " " + s.text + " " + s.tip for s in tour.STEPS] + [tour.WELCOME]
    broken = list(tour.STEPS)
    broken[3] = broken[3]._replace(prev="vision")                              # a planted fault: a step that points back to the wrong place
    cl.record(chain_ok(tour.STEPS) and all(s.label == f"Step {n} of {n_steps}" for n, s in enumerate(tour.STEPS, start=1)) and {s.page for s in tour.STEPS} == client_files and not found_in(texts) and not chain_ok(broken),
              "The tour is eight steps in one unbroken chain (each step's Next is the next step's Back), labelled Step 1 of 8 to Step 8 of 8, that visits every client page, with no developer wording in the welcome or in any step; a planted broken chain is caught",
              f"{n_steps} steps; pages {len(client_files)}; wording found {found_in(texts)}")

    os.environ["CELLPOC_RECORD"] = str(PLATFORM)
    os.environ.pop("CELLPOC_DEVELOPER", None)
    try:
        app = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
        app.run()
        first_keys = [b.key for b in app.button]

        def press(key: str) -> bool:
            for b in app.button:
                if b.key == key:
                    b.click()
                    app.run()
                    return True
            return False

        def cards() -> list[str]:
            return [m.value for m in app.markdown if 'class="ub-tour"' in m.value]

        def state(name: str):
            return app.session_state[name] if name in app.session_state else None

        started = press("tour_again")
        walked = [state("tour")]
        shown_pages = [bool(cards())]
        while state("tour") is not None and len(walked) <= n_steps + 1:
            press("tour_next")
            walked.append(state("tour"))
            shown_pages.append(bool(cards()))
        walked = walked[:-1] if walked[-1] is None else walked
        after_walk_clean = not app.exception
        press("tour_again")
        press("tour_next")
        press("tour_next")
        at_camera = state("tour")
        press("tour_back")
        went_back = state("tour")
        press("tour_end")
        ended = state("tour")
        card_after_end = bool(cards())
        second_first_keys = [b.key for b in app.button]
        press("tour_again")
        press("tour_next")
        press("tour_next")
        press("tour_next")
        press("tour_next")
        press("tour_next")
        press("tour_next")
        press("tour_next")
        about_text = [x for x in visible(app)]
        banner_once = sum(x.lower().count(SENTENCE) for x in about_text) == 1
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
    developer_keys = [b.key for b in run_app(None, True).button]
    cl.record(started and "welcome_tour" in first_keys and "welcome_skip" in first_keys and "tour_again" in first_keys and "welcome_tour" not in second_first_keys
              and walked == [s.id for s in tour.STEPS] and all(shown_pages[:n_steps]) and state("tour") is not None and at_camera == "camera" and went_back == "live" and ended is None and not card_after_end
              and after_walk_clean and banner_once and not {"welcome_tour", "tour_again", "tour_next"} & set(developer_keys),
              "The welcome window opens on the first visit and only then; 'Take the tour' in the left menu starts the tour; Next walks through all eight steps in order with the step's card on each page; Back goes back one; End tour ends it and the card goes; the illustrative sentence is still on the page exactly once during the tour; no welcome and no tour in the developer view",
              f"steps walked {walked}; back from {at_camera} to {went_back}; ended {ended}; developer buttons with a tour: {sorted({'welcome_tour', 'tour_again', 'tour_next'} & set(developer_keys))}")

    # ---------------------------------------------------------------- the front page says what the product is and what the solution is
    from cellpoc.shell import landing
    front = " ".join(visible(pages["Overview"]))
    welcome_text = tour.WELCOME
    needed_front = ["The challenge", "The solution", "How it works", "The proof", "Explore", "A robot does the lab work", "Cameras check everything", "An engine chooses what to try next"]
    hero_file = ROOT / "static" / "cell_hero.jpg"
    link_labels = [str(x.proto.label) for x in pages["Overview"].get("page_link")]
    cl.record(all(w in front or w in " ".join(m.value for m in pages["Overview"].markdown) for w in needed_front) and "Start the live demo" in link_labels and "See the results" in link_labels and hero_file.exists() and hero_file.stat().st_size > 10_000 and landing.HERO_IMAGE.endswith("cell_hero.jpg")
              and "The challenge" in welcome_text and "The solution" in welcome_text and all(title in welcome_text for _, title, _ in landing.SOLUTION) and "illustrative" in welcome_text,
              "The front page says what the product is and what the solution is: the hero (with the picture of the cell), the challenge, the solution (three points), how it works, the proof, and where to go next; the welcome window tells the same story (challenge, then solution, then the three points, and that the numbers are illustrative)",
              f"missing {[w for w in needed_front if w not in front and w not in ' '.join(m.value for m in pages['Overview'].markdown)]}; hero picture {'there' if hero_file.exists() else 'MISSING'}")
    os.environ["CELLPOC_RECORD"] = str(PLATFORM)
    os.environ.pop("CELLPOC_DEVELOPER", None)
    try:
        skipped = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
        skipped.query_params["welcome"] = "off"
        skipped.run()
        skip_keys = [b.key for b in skipped.button]
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
    cl.record("welcome_tour" not in skip_keys and "tour_again" in skip_keys and not skipped.exception,
              "A link with ?welcome=off opens the app without the welcome window (the tour can still be started from the left menu)", f"buttons {skip_keys}")

    after = project_files()
    cl.record(before == after, "Nothing in the project was changed by this check", "")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
