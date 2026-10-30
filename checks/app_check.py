"""Health check for the unified app, Stage A: one app with a left menu that shows the dashboard's pages, an Overview page, and the dark Deloitte look.

In plain words it checks that: the menu has the approved pages in the approved order and every page draws without an error, for a platform run, for the proof of concept's demo run (which has no platform pages) and with no run record at all (a plain message);
the pages it hosts say exactly what the dashboard's pages say (every text block, heading, caption, figure, button and table is compared with the same page of the dashboard); the sentence "Simulation with illustrative values" appears exactly ONCE on every page (and a
counter that finds it twice on every page of the old dashboard proves the counting can fail); the Overview's headline numbers and the top bar's trial count equal numbers worked out separately from the raw run record (recounted from its trials and alerts, the rate worked out
from the run's hours and the manual baseline read from the settings file), with planted wrong numbers (a record whose summary lies, and a page that shows swapped figures) proving the comparison can fail; the unified app uses only brand colours and names no outside web address;
the real launcher run_app.bat, run for real in both variants, leaves the app listening on this computer only, with a self-test that removes the flag and sees every address; and the architecture guard (with the unified app's own entries and planted violations) passes.
Stages B and C add their own parts (checks/app_setup_part.py: the setup app inside the unified app; checks/app_live_part.py: the live view inside it, started and stopped by the supervisor, kept on 127.0.0.1 and left no orphan).
Nothing is written into the project, and nothing uses the network except the local servers on this computer.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (2026-10-24) The unified app opens in its CLIENT view by default; these checks are about the developer view (every page, the technical detail, which is unchanged), so they ask for it. The client view has its own check (checks/client_view_check.py).
os.environ["CELLPOC_DEVELOPER"] = "1"

from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.launchers_check import kill_tree, listening_on, look, wait_until_up  # noqa: E402
from checks.models_check import project_files  # noqa: E402

PLATFORM, CONNECTED, DEMO = ROOT / "runs" / "platform", ROOT / "runs" / "connected_run", ROOT / "runs" / "demo"
APP_BAT = ROOT / "run_app.bat"
PORT_REAL, PORT_CONNECTED, PORT_FLAGLESS = 8584, 8585, 8583

# The approved menu, written out here on purpose (not read from the app) so the app's own list is compared with the decision.
# (2026-10-16, at the owner's requests: "Physics (MuJoCo)" added after "3D replay" to see the MuJoCo model in the app, not in a separate window; "Results at a glance" added after the Overview, a charts page made for a client demo; "Vision" added after the Overview (a picture of a bench in, levels and solutions out) at the lead's request; the sections renamed "See the cell" and "Evidence".)
APPROVED = ["Overview", "Vision", "Results at a glance", "Setup", "The run", "Live run", "3D replay", "Physics (MuJoCo)", "Data and model", "Reports", "About and limits"]
PAGE_FILES = {"Overview": "overview", "Vision": "vision", "Results at a glance": "results", "Setup": "setup", "The run": "the_run", "Live run": "live_run", "3D replay": "replay", "Physics (MuJoCo)": "physics", "Data and model": "data_and_model", "Reports": "reports", "About and limits": "about"}
PLATFORM_ONLY = {"Results at a glance", "3D replay", "Physics (MuJoCo)", "Data and model", "Reports"}
# the dashboard tab each hosted page must match (tab index on a platform run): The run's five tabs are 0 to 4, "What this shows" is 5, then the three platform tabs
HOSTED = {"3D replay": 6, "Data and model": 7, "Reports": 8, "About and limits": 5}
SENTENCE = "simulation with illustrative values"
BRAND = {"#86BC25", "#000000", "#86EB22", "#00A3E0", "#282728", "#FFFFFF", "#A0DCFF", "#005587", "#E6E6E6", "#E2E2E2", "#F5F5F5", "#555555", "#B7E320", "#63C631", "#3FC3EC", "#E8A317", "#DA291C"}
METRICS = {"attempted": "Trials attempted", "with_result": "Trials with a result", "good": "Good recipes", "skipped": "Skipped (no result)", "recovered": "Faults recovered",
           "alerts": "Alerts for staff", "per_week": "Trials with a result per week", "manual": "Manual baseline per week", "times": "Times the manual rate"}


# ---------------------------------------------------------------- running the app in the test harness

def run_app(folder: Path | None, page: str | None = None):
    """The unified app on a record (or on a missing one), optionally switched to one menu page."""
    from streamlit.testing.v1 import AppTest
    os.environ["CELLPOC_RECORD"] = str(folder) if folder is not None else str(ROOT / "runs" / "no_such_record")
    try:
        app = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=180)
        app.run()
        if page is not None:
            app.switch_page(f"cellpoc/shell/pages/{PAGE_FILES[page]}.py")
            app.run()
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
    return app


def run_dashboard(folder: Path):
    from streamlit.testing.v1 import AppTest
    os.environ["CELLPOC_RECORD"] = str(folder)
    try:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
        app.run()
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
    return app


def content(block) -> dict:
    """Everything a person reads or clicks in a block of the page, in order. The unified app's own chrome (the style sheets and the top bar) is left out."""
    markdown = [m.value for m in block.markdown if not m.value.lstrip().startswith("<style>") and 'class="ub-bar"' not in m.value]
    return {"markdown": markdown, "subheader": [e.value for e in block.subheader], "caption": [e.value for e in block.caption], "info": [e.value for e in block.info], "warning": [e.value for e in block.warning],
            "metric": [(m.label, m.value) for m in block.metric], "button": [b.label for b in block.button], "dataframe": len(block.dataframe)}


def all_text(block) -> list[str]:
    c = content(block)
    return c["markdown"] + c["subheader"] + c["caption"] + c["info"] + c["warning"]


def sentence_count(texts: list[str]) -> int:
    return sum(t.lower().count(SENTENCE) for t in texts)


# ---------------------------------------------------------------- the independent read of the record

def find_key(node, key):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def independent_numbers(record_json: Path) -> dict[str, str]:
    """The Overview's numbers worked out again from the raw record file (read as plain JSON, not through the program's own reader) and the settings file: recounted, not copied from the stored summary."""
    d = json.loads(record_json.read_text(encoding="utf-8"))
    trials, alerts = d["trials"], d["alerts"]
    with_result = sum(1 for t in trials if t["status"] == "Completed")
    hours = d["meta"]["duration_minutes"] / 60
    baseline = float(find_key(yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")), "manual_baseline_trials_per_week"))
    rate = with_result * 168 / hours
    return {"attempted": str(len(trials)), "with_result": str(with_result), "good": str(sum(1 for t in trials if t["outcome"] == "Good")), "skipped": str(sum(1 for t in trials if t["status"] == "Skipped")),
            "recovered": str(sum(1 for a in alerts if a["severity"] == "Recovered")), "alerts": str(sum(1 for a in alerts if a["needs_human"])),
            "per_week": f"{rate:.1f}", "manual": f"{baseline:g}", "times": f"{rate / baseline:.1f}x", "chip": str(len(trials))}


def displayed_numbers(app) -> dict[str, str]:
    """What the unified app's Overview and top bar show, read from the rendered page."""
    shown = {m.label: m.value for m in app.main.metric}
    found = {key: shown.get(label, "(not shown)") for key, label in METRICS.items()}
    chip = re.search(r'data-chip="trials">(\d+) trials attempted<', "\n".join(m.value for m in app.main.markdown))
    found["chip"] = chip.group(1) if chip else "(not shown)"
    return found


def differences(shown: dict[str, str], truth: dict[str, str]) -> list[str]:
    return [k for k in truth if shown.get(k) != truth[k]]


def tampered_copy(folder: Path, into: Path) -> Path:
    """A copy of a run record whose stored summary tells lies the trials do not support: one more good recipe, one more attempted, a made-up weekly rate."""
    into.mkdir(parents=True, exist_ok=True)
    d = json.loads((folder / "record.json").read_text(encoding="utf-8"))
    d["summary"]["trials_good"] += 1
    d["summary"]["trials_attempted"] += 1
    d["summary"]["trials_per_week"] = 99.9
    (into / "record.json").write_text(json.dumps(d), encoding="utf-8")
    return into


# ---------------------------------------------------------------- the launcher

def bat_commands(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if "-m streamlit run" in line and not line.strip().lower().startswith("rem")]


def main() -> int:
    cl = Checklist("UNIFIED APP, STAGE A: one menu, the dashboard's pages inside it, an Overview whose numbers are right, one illustrative label per page, on this computer only")
    before = project_files()

    # ---------------------------------------------------------------- the menu and every page draws
    from cellpoc.shell import menu
    titles = [e.title for entries in menu.SECTIONS.values() for e in entries]
    files_exist = all((ROOT / e.path).exists() for entries in menu.SECTIONS.values() for e in entries)
    cl.record(titles == APPROVED and files_exist and (ROOT / "unified_app.py").exists(), "The menu has exactly the approved pages in the approved order (Overview, Vision, Results at a glance, Setup, The run, Live run, 3D replay, Physics (MuJoCo), Data and model, Reports, About and limits), and each has its page file",
              " > ".join(titles))
    platform_app = run_app(PLATFORM)
    first = displayed_numbers(platform_app)
    drawn = {}
    for title in APPROVED:
        app = platform_app if title == "Overview" else run_app(PLATFORM, title)
        drawn[title] = app
    errors = {t: [str(e.value)[:80] for e in a.exception] for t, a in drawn.items() if a.exception}
    cl.record(not errors and all(len(a.main.markdown) > 3 for a in drawn.values()) and len(drawn["The run"].tabs) == 5,
              "With a platform run every menu page draws with no error (The run with its five tabs)", "; ".join(f"{k}: {v}" for k, v in errors.items()) or f"{len(drawn)} pages drawn")

    demo_pages = {t: run_app(DEMO, t) for t in APPROVED if t not in PLATFORM_ONLY}
    demo_steps = re.findall(r'class="ub-num">(\d+)<', "\n".join(m.value for m in demo_pages["Overview"].main.markdown))
    platform_steps = re.findall(r'class="ub-num">(\d+)<', "\n".join(m.value for m in platform_app.main.markdown))
    demo_errors = [t for t, a in demo_pages.items() if a.exception]
    cl.record(not demo_errors and len(demo_steps) == 4 and len(platform_steps) == 9,
              "With the proof of concept's demo run (no platform section) the pages that exist draw with no error and the Overview's demo-order list offers 4 pages (Vision, Setup, The run, Live run) against 9 for a platform run: the platform pages are not offered where they do not exist",
              f"demo list {len(demo_steps)}, platform list {len(platform_steps)}; errors {demo_errors}")
    missing = run_app(None, None)
    cl.record(not missing.exception and any("no run record" in w.value.lower() or "double-click run_app.bat" in w.value for w in missing.warning),
              "With no run record at all the app says so in plain words (and names run_app.bat) instead of failing", "; ".join(w.value[:90] for w in missing.warning))

    # ---------------------------------------------------------------- the Physics (MuJoCo) page (2026-10-16)
    import shutil
    from cellpoc.dashboard import physics_view as physics_page
    from cellpoc.physics import view as physics_files
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "run"
        shutil.copytree(PLATFORM, copy, ignore=shutil.ignore_patterns("physics_*", "replay.html", "reports"))
        bare = run_app(copy, "Physics (MuJoCo)")                                          # no view drawn yet: a plain message, no crash
        physics_files.build(copy, size=(320, 180), stride=12, log=lambda *_: None)          # a small, quick drawing for the test
        drawn_view = run_app(copy, "Physics (MuJoCo)")
        view_text = " ".join(all_text(drawn_view.main))
        view_captions = [c.value for c in drawn_view.main.caption if c.value.startswith("Trial ")]
        view_files = [n for n in physics_files.VIEW_FILES if (copy / n).exists() and (copy / n).stat().st_size > 5000]
    cl.record(not bare.exception and any("MuJoCo view has not been drawn" in w.value and "run_app.bat" in w.value for w in bare.warning) and not drawn_view.exception and len(view_files) == 2 and len(view_captions) == 2
              and "28 of 28 reached" in view_text and sentence_count(all_text(drawn_view.main)) == 1 and physics_page.PICTURES == physics_files.VIEW_FILES and physics_page.SUMMARY == physics_files.SUMMARY_FILE,
              "The Physics (MuJoCo) page: before the view is drawn it says so in plain words and names run_app.bat; once drawn (two trials, one with a jam) it shows both animated pictures with their descriptions and the reach and collision checks ('28 of 28 reached'), the illustrative sentence once, and the file names the page reads are the ones the builder writes",
              f"pictures {len(view_files)}; captions {len(view_captions)}; warnings before: {[w.value[:50] for w in bare.warning]}")

    # ---------------------------------------------------------------- the replay's own title band (D1, 2026-10-16)
    from unittest import mock
    from cellpoc.dashboard import platform_replay
    replay_file = (PLATFORM / "replay.html").read_text(encoding="utf-8")
    seen = {"app": [], "old": []}
    with mock.patch.object(platform_replay.components, "html", side_effect=lambda page, **k: seen["app"].append((page, k))):
        run_app(PLATFORM, "3D replay")
    with mock.patch.object(platform_replay.components, "html", side_effect=lambda page, **k: seen["old"].append((page, k))):
        run_dashboard(PLATFORM)
    in_app, old = (seen["app"][0] if seen["app"] else ("", {})), (seen["old"][0] if seen["old"] else ("", {}))
    cl.record(platform_replay.HIDE_BAND in in_app[0] and in_app[0].replace(platform_replay.HIDE_BAND, "", 1) == replay_file and platform_replay.HIDE_BAND not in old[0] and old[0] == replay_file and old[1].get("height") == 1100 and in_app[1].get("height") == 1040,
              "The 3D replay inside the unified app has its own title band hidden by exactly one added style rule (remove the rule and the file is byte for byte the saved replay), while the old dashboard shows the replay exactly as saved at its old height",
              f"in the app: {len(in_app[0])} characters; old dashboard: {len(old[0])}; saved file {len(replay_file)}")

    # ---------------------------------------------------------------- the demo start page and the client script match the app (D5, 2026-10-16)
    start_page = (ROOT / "docs" / "demo_start.html").read_text(encoding="utf-8")
    client_script = (ROOT / "docs" / "guides" / "client_demo_script.md").read_text(encoding="utf-8")
    ports = set(re.findall(r"localhost:(\d+)", start_page + client_script))
    routes = set(re.findall(r"localhost:8510/(\w*)", start_page))
    known_routes = set(PAGE_FILES.values()) | {""}
    named = [title for title in APPROVED if title not in ("The run", "Data and model", "About and limits") and title not in client_script]
    cl.record(ports <= {"8510", "8511"} and routes and routes <= known_routes and "run_app.bat" in start_page and "run_app.bat" in client_script and not named,
              "The demo start page and the client demo script match the unified app: they name only its two addresses (8510 and 8511), every page address on the start page is a real page of the menu, both tell you to start with run_app.bat, and the script names every page it shows (Overview, Results at a glance, Setup, Live run, 3D replay, Physics (MuJoCo), Reports)",
              f"ports {sorted(ports)}; routes {sorted(routes)}; not named in the script: {named}")

    # ---------------------------------------------------------------- the hosted pages say what the dashboard says
    dash = run_dashboard(PLATFORM)
    same, detail = [], []
    for k in range(5):
        a, b = content(drawn["The run"].tabs[k]), content(dash.tabs[k])
        same.append(a == b)
        detail.append(f"tab {k}: {len(a['markdown'])} blocks")
    for title, k in HOSTED.items():
        a, b = content(drawn[title].main), content(dash.tabs[k])
        same.append(a == b)
        detail.append(f"{title}: {len(a['markdown'])} blocks")
    cl.record(all(same) and len(same) == 9, "Every page the unified app hosts says exactly what the same page of the dashboard says (all text blocks, headings, captions, figures, buttons and tables compared, nine pages in all, on the platform run)", "; ".join(detail))

    # ---------------------------------------------------------------- the illustrative sentence, once on every page
    counts = {t: sentence_count(all_text(a.main)) for t, a in drawn.items() if t != "The run"}
    run_tabs = [sentence_count(all_text(drawn["The run"].tabs[k])) for k in range(5)]
    outside_tabs = sentence_count(all_text(drawn["The run"].main)) - sum(run_tabs)
    cl.record(all(c == 1 for c in counts.values()) and run_tabs == [1] * 5 and outside_tabs == 0,
              "The sentence 'Simulation with illustrative values' appears exactly ONCE on every page of the unified app (on The run, once in each of its five tabs and not outside them)", f"{counts}; The run tabs {run_tabs}; outside the tabs {outside_tabs}")
    old = [sentence_count(all_text(dash.main)) - sum(sentence_count(all_text(dash.tabs[j])) for j in range(9)) + sentence_count(all_text(dash.tabs[k])) for k in range(9)]
    cl.record(all(c == 2 for c in old) and sentence_count(["x", SENTENCE, "Simulation with illustrative values"]) == 2,
              "Self-test: the same counter finds the sentence TWICE on every one of the old dashboard's nine pages (its green bar and its page line, kept on purpose there) and twice in a planted doubled list, so a page that showed it twice would be caught", f"old dashboard per page: {old}")

    # ---------------------------------------------------------------- the numbers are right
    truth = independent_numbers(PLATFORM / "record.json")
    wrong = differences(first, truth)
    demo_wrong = differences(displayed_numbers(demo_pages["Overview"]), independent_numbers(DEMO / "record.json"))
    cl.record(not wrong and not demo_wrong,
              "The Overview's nine headline numbers and the top bar's trial count equal numbers worked out separately from the raw record file (trials and alerts recounted, the weekly rate from the run's hours, the manual baseline from the settings file), on the platform run and on the demo run",
              f"platform: {', '.join(f'{k}={first[k]}' for k in ('attempted', 'with_result', 'good', 'skipped', 'per_week', 'times'))}; wrong: {wrong or 'none'}; demo wrong: {demo_wrong or 'none'}")
    with tempfile.TemporaryDirectory() as tmp:
        lying = displayed_numbers(run_app(tampered_copy(PLATFORM, Path(tmp) / "lying"), None))
    caught = differences(lying, truth)
    swapped = dict(first, good=first["skipped"], skipped=first["good"])
    cl.record(sorted(caught) == sorted(["attempted", "good", "per_week", "chip"]) and sorted(differences(swapped, truth)) == ["good", "skipped"] and not differences(first, truth),
              "Self-test: a record whose summary lies (one more good recipe, one more attempted, a made-up weekly rate) is caught on exactly those figures and on the top bar's count, a page showing swapped figures is caught, and the honest page is not flagged, so this comparison can fail",
              f"lying record caught: {sorted(caught)}; swapped caught: {sorted(differences(swapped, truth))}")

    # ---------------------------------------------------------------- the look: palette, no outside address
    colours = {}
    for path in sorted((ROOT / "cellpoc" / "shell").rglob("*.py")):
        for code in re.findall(r"#[0-9A-Fa-f]{6}\b", path.read_text(encoding="utf-8")):
            colours.setdefault(code.upper(), path.name)
    off = {c: f for c, f in colours.items() if c not in BRAND}
    outside = [m for app in drawn.values() for t in all_text(app.main) for m in re.findall(r"https?://(?!localhost|127\.0\.0\.1)\S+", t)]
    cl.record(not off and {"#86BC25", "#282728", "#000000", "#86EB22"} <= set(colours) and not outside,
              "The unified app uses only Deloitte brand colours (Deloitte Green, Black, Dark Gray, Neon Green on dark, white and the light grays) and no page of it names an outside web address", f"{len(colours)} colours checked; off palette: {off or 'none'}; outside addresses: {outside[:2] or 'none'}")

    # ---------------------------------------------------------------- the real launcher: this computer only
    text = APP_BAT.read_text(encoding="utf-8")
    commands = bat_commands(text)
    cl.record(len(commands) == 1 and "--server.address localhost" in commands[0] and "%PORT%" in commands[0] and "unified_app.py" in commands[0] and "8510" in text and "8511" in text and "CELLPOC_PORT" in text,
              "run_app.bat starts the app with ONE command, shared by its two variants (8510 platform run, 8511 loop connected), and it carries --server.address localhost", commands[0][:100] if commands else "no command found")
    for port, args, label in ((PORT_REAL, [], "run_app.bat"), (PORT_CONNECTED, ["connected"], "'run_app.bat connected' (the loop connected)")):
        proc = subprocess.Popen(["cmd", "/c", str(APP_BAT), *args], cwd=ROOT, env=dict(os.environ, CELLPOC_PORT=str(port)), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            up = wait_until_up(port, 400 if args else 180)
            only_here, reachable = look(port) if up else ([], False)
            cl.record(up and bool(only_here) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in only_here) and not reachable,
                      f"Run for real, {label} leaves the unified app listening on this computer only: 127.0.0.1 and no other address, and the computer's other network address cannot connect", f"listening on {only_here}; up: {up}")
        finally:
            kill_tree(proc)
    command = commands[0].replace("%PORT%", str(PORT_FLAGLESS)).replace("--server.address localhost", "")
    pieces = [p.strip('"') for p in shlex.split(command, posix=False)]
    pieces[0] = str(ROOT / ".venv" / "Scripts" / "python.exe")
    flagless = subprocess.Popen(pieces + ["--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=ROOT, env=dict(os.environ, CELLPOC_RECORD=str(PLATFORM)),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = wait_until_up(PORT_FLAGLESS, 60)
        everywhere, reachable = look(PORT_FLAGLESS) if up else ([], False)
        lan_is_loopback = socket.gethostbyname(socket.gethostname()).startswith("127.")
        cl.record(up and any(a.startswith(("0.0.0.0:", "[::]:")) for a in everywhere) and (reachable or lan_is_loopback),
                  "Self-test: the same command with the flag taken out is seen listening on every address (0.0.0.0) and, without it, the computer's other network address can connect, so this check can fail and the flag is what makes the difference",
                  f"listening on {everywhere}; outside connection {'succeeded' if reachable else 'not possible on this computer'}")
    finally:
        kill_tree(flagless)
    time.sleep(2)
    cl.record(not (listening_on(PORT_REAL) or listening_on(PORT_CONNECTED) or listening_on(PORT_FLAGLESS)), "The servers this check started are stopped again: nothing is left listening on its ports")

    # ---------------------------------------------------------------- Stage B: the setup app drawn inside the unified app
    from checks import app_setup_part
    app_setup_part.run(cl, displayed_numbers, run_app)

    # ---------------------------------------------------------------- Stage C: the live view inside the unified app, started and stopped by the supervisor
    from checks import app_live_part
    app_live_part.run(cl)

    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project outside the folders for generated output", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
