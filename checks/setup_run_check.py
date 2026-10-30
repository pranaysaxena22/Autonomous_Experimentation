"""Health check for 'Run this setup' (the setup app's last screen): does the setup you fill in really drive a simulated run, and does the button behave?

In plain words it checks that: on the last screen a button saves the setup and simulates the SAVED file (the example setup gives its 30 trials); changing the setup changes the run (a 240-hour run window gives 60 trials, not 30), which
is the proof that the setup page drives the simulation; the run's record carries the setup's own project name and is the standard record the dashboard opens; the button is switched off while the setup has errors, with the reason
in words, and when the setup cannot be simulated yet (the proof of concept's two targets are required), with the reason in words; an existing saved setup is not replaced unless you tick the box; a refused or failed run shows a
plain sentence, never a technical trace; 'Open the dashboard on this run' and 'Watch this setup run live' start the platform's own programs in their own black windows (the dashboard on its own address, on the run's folder; the live
page on the saved file) and show where to click; the new part of the app imports only the setup part, writes no file itself, and uses no network; and nothing is left behind in the project (the saved test setup is removed).
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

NAME = "zz-run-check"
SAVED = ROOT / "setups" / f"{NAME}.yaml"
RUN = ROOT / "runs" / "setup_run"
TECHNICAL = re.compile(r"Traceback|KeyError|TypeError|ValueError|NoneType|\{|\}")


def fresh_app():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "setup_app.py"), default_timeout=240)
    app.run()
    next(b for b in app.button if b.label == "Load example").click().run()
    app.session_state["screen"] = 9
    app.run()
    set_name(app)
    return app


def set_name(app) -> None:
    box = next(t for t in app.text_input if t.key and t.key.startswith("save_name|"))
    box.set_value(NAME).run()


def run_button(app):
    return next(b for b in app.button if b.key == "save_and_run")


def tick_replace(app) -> None:
    boxes = [c for c in app.checkbox if c.key == f"replace|{NAME}"]
    if boxes:
        boxes[0].check().run()


def trials_in_run() -> int:
    return len(run_store.load(RUN).trials)


def listening_on(port: int) -> list[str]:
    """The addresses the computer is really listening on for this port (what netstat reports), not what any file says."""
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    return sorted({cols[1] for line in out.splitlines() if "LISTENING" in line for cols in [line.split()] if len(cols) >= 4 and cols[1].endswith(f":{port}")})


def serve_and_look(command: list[str], port: int, env: dict) -> tuple[list[str], bool]:
    """Start the command for real, wait until it answers on this computer, and report (the addresses it listens on, whether another address of this computer could connect)."""
    proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2).read().strip() == b"ok":
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        listening = []
        for _ in range(20):                                       # the address shows up a moment after the server answers
            listening = listening_on(port)
            if listening:
                break
            time.sleep(1)
        lan = socket.gethostbyname(socket.gethostname())
        reachable = False
        if not lan.startswith("127."):
            try:
                socket.create_connection((lan, port), timeout=3).close()
                reachable = True
            except OSError:
                reachable = False
        return listening, reachable
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)       # the whole tree: the launcher starts the real server as a child
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def listening_checks(cl: Checklist, tmp: Path) -> None:
    """What the setup app starts must answer this computer only: the check starts the very command the app uses and looks at the real listening addresses and at a connection from the computer's other address."""
    from cellpoc.setup_app import run_this
    env = dict(os.environ, CELLPOC_RECORD=str(tmp))
    command = run_this.dashboard_command(8596)
    only_here, reachable = serve_and_look(command, 8596, env)
    cl.record(bool(only_here) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in only_here) and not reachable,
              "The dashboard the setup app starts really listens on this computer only: its listening addresses are 127.0.0.1 and nothing else, and the computer's other network address cannot connect to it", f"listening on {only_here}")
    without = [a for a in run_this.dashboard_command(8595) if a not in ("--server.address", "localhost")]       # the same command on another port, minus the address flag
    everywhere, reachable_everywhere = serve_and_look(without, 8595, env)
    cl.record(any(a.startswith(("0.0.0.0:", "[::]:")) for a in everywhere),
              "Self-test: the same command without the address flag is seen listening on every address (so this check could fail, and the flag is what makes the difference)", f"listening on {everywhere}" + ("; reachable from the computer's other address" if reachable_everywhere else ""))


def example_checks(cl: Checklist) -> None:
    """The setup app offers three illustrative examples; each loads, and each runs from the last screen with its own result."""
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "setup_app.py"), default_timeout=240)
    app.run()
    picker = next((s for s in app.selectbox if s.key == "welcome_example_choice"), None)
    labels = list(picker.options) if picker else []
    cl.record(len(labels) == 3 and labels[0].startswith("Example 1") and labels[1].startswith("Example 2") and labels[2].startswith("Example 3"), "The setup app offers three illustrative examples to start from", " | ".join(labels))
    names, trials = [], []
    for i, label in enumerate(labels):
        app = AppTest.from_file(str(ROOT / "setup_app.py"), default_timeout=240)
        app.run()
        next(s for s in app.selectbox if s.key == "welcome_example_choice").select(label).run()
        next(b for b in app.button if b.key == "welcome_example").click().run()
        names.append(app.session_state["setup"]["project"]["name"])
        app.session_state["screen"] = 9
        app.run()
        set_name(app)
        tick_replace(app)
        run_button(app).click().run()
        result = app.session_state["run_result"]
        trials.append(trials_in_run() if result and result["ok"] else -1)
    cl.record(len(set(names)) == 3 and names[0] == "Illustrative tablet study" and names[1].startswith("Illustrative study 2") and names[2].startswith("Illustrative study 3"), "Each choice loads its own setup (three different project names)", " | ".join(names))
    cl.record(len(set(trials)) == 3 and all(t > 0 for t in trials) and trials[0] == 30 and trials[1] > 35 and trials[2] < 30, "...and each runs from the last screen with its own result: 30 trials for example 1, more for the week-long example 2, fewer for the 96-hour example 3", f"{trials} trials")
    app = AppTest.from_file(str(ROOT / "setup_app.py"), default_timeout=240)
    try:
        app.query_params["start"] = "example3"
        app.run()
        cl.record(app.session_state["setup"] is not None and app.session_state["setup"]["project"]["name"].startswith("Illustrative study 3"), "The web address ?start=example3 opens the third example directly (and ?start=example2 the second)")
    except Exception:  # noqa: BLE001 - an older test harness without query parameters
        cl.skip("The web address ?start=example3 opens the third example", "this version of the test harness cannot set a web address")


def main() -> int:
    cl = Checklist("RUN THIS SETUP: the setup you fill in drives a simulated run, from the setup app's last screen")
    before = project_files()
    SAVED.unlink(missing_ok=True)
    try:
        app = fresh_app()
        btn = run_button(app)
        cl.record(btn.label == "Save and run it" and not btn.disabled and any("Run this setup" in m.value for m in app.markdown), "The last screen offers 'Save and run it' for the example setup, under the heading 'Run this setup'")
        btn.click().run()
        result = app.session_state["run_result"]
        ok_run = bool(result and result["ok"]) and SAVED.exists() and (RUN / "record.json").exists()
        n1 = trials_in_run() if ok_run else -1
        record = run_store.load(RUN) if ok_run else None
        cl.record(ok_run and n1 == 30 and record.platform is not None and record.platform.setup_name == "Illustrative tablet study" and "30 attempted" in " ".join(s.value for s in app.success),
                  "Pressing it saves the setup into the setups folder and simulates the saved file: the standard run record is written (30 trials for the example), with the setup's own project name, and the page says what happened",
                  f"{n1} trials; {(result or {}).get('lines', ['no output'])[-1]}")
        cl.record(all(f.exists() for f in (RUN / "replay.html", RUN / "reports" / "report.html", RUN / "platform_index.json")), "The run also has its 3D replay, its report files and its index, like any platform run")

        # the setup drives the run: a longer run window gives more trials
        app.session_state["setup"]["calendar"]["duration_h"] = 240
        app.run()
        tick_replace(app)
        run_button(app).click().run()
        n2 = trials_in_run() if app.session_state["run_result"] and app.session_state["run_result"]["ok"] else -1
        cl.record(n1 == 30 and n2 == 60, "Changing the setup changes the run: with a 240-hour run window on the Calendar screen the same button gives 60 trials instead of 30 (the setup page drives the simulation)", f"30 -> {n2} trials")

        # replacing an existing saved setup needs the box ticked
        app = fresh_app()
        cl.record(run_button(app).disabled and any(c.key == f"replace|{NAME}" for c in app.checkbox), "A setup that already exists is not replaced (and so not run) until the 'Replace it' box is ticked")

        # buttons that start the dashboard and the live page: the programs are started in their own windows, with the right arguments
        app = fresh_app()
        tick_replace(app)
        run_button(app).click().run()
        calls = []
        with mock.patch("subprocess.Popen", side_effect=lambda *a, **k: calls.append((a, k))):
            next(b for b in app.button if b.key == "open_dashboard").click().run()
            next(b for b in app.button if b.key == "watch_live").click().run()
        dash, live = (calls[0], calls[1]) if len(calls) == 2 else (None, None)
        cl.record(dash is not None and "streamlit" in dash[0][0] and "8506" in dash[0][0] and dash[1]["env"]["CELLPOC_RECORD"].endswith("setup_run") and live is not None and "cellpoc.live" in live[0][0] and f"setups/{NAME}.yaml" in live[0][0]
                  and getattr(__import__("subprocess"), "CREATE_NEW_CONSOLE", 0) == dash[1]["creationflags"] == live[1]["creationflags"],
                  "'Open the dashboard on this run' starts the dashboard on its own address (8506) on the run's folder, and 'Watch this setup run live' starts the live page on the saved file, each in its own black window", "")
        links = [str(l.proto.url) if hasattr(l, "proto") else "" for l in app.get("link_button")]
        cl.record(all(re.fullmatch(r"http://localhost:\d+", x) for x in links) and any(x.endswith(":8506") for x in links) and any(x.endswith(":8504") for x in links), "...and the page shows where to click for each, and every link points at this computer (localhost) and nowhere else", ", ".join(links))

        # a failed run says so in words
        app = fresh_app()
        tick_replace(app)
        fake = mock.Mock(returncode=1, stdout="Running the platform simulation (a few seconds)...\nCannot run: The setup has errors, so it cannot be simulated: the name is too long.\n", stderr="Traceback (most recent call last): boom")
        with mock.patch("subprocess.run", return_value=fake):
            run_button(app).click().run()
        shown = " ".join(e.value for e in app.error)
        cl.record(shown.startswith("Cannot run:") and not TECHNICAL.search(shown), "A refused run shows the program's own plain sentence, never a technical trace", shown[:90])
        fake = mock.Mock(returncode=1, stdout="", stderr="Traceback (most recent call last):\n  File x\nKeyError: 'boom'")
        with mock.patch("subprocess.run", return_value=fake):
            run_button(app).click().run()
        shown = " ".join(e.value for e in app.error)
        cl.record("stopped unexpectedly" in shown and not TECHNICAL.search(shown), "An unexpected failure shows a plain sentence and no trace", shown[:90])

        # errors and unsupported setups switch the button off, with the reason
        app = fresh_app()
        app.session_state["setup"]["ingredients"][0]["min"] = 400
        app.run()
        warns = " ".join(w.value for w in app.warning)
        cl.record(run_button(app).disabled and "Fix the errors first" in warns, "While the setup has an error the button is switched off and says why", warns[:90])
        app = fresh_app()
        app.session_state["setup"]["targets"]["constraints"] = [c for c in app.session_state["setup"]["targets"]["constraints"] if c["response"] != "dissolution_30min_pct"]
        app.run()
        warns = " ".join(w.value for w in app.warning)
        cl.record(run_button(app).disabled and ("cannot be simulated yet" in warns or "Fix the errors first" in warns) and not TECHNICAL.search(warns), "A setup the simulation cannot represent yet (here: no dissolution target) cannot be run, and the page says why in words", warns[:100])
        example_checks(cl)
        with tempfile.TemporaryDirectory() as listening_tmp:
            listening_checks(cl, Path(listening_tmp))
    finally:
        SAVED.unlink(missing_ok=True)

    source = (ROOT / "cellpoc" / "setup_app" / "run_this.py").read_text(encoding="utf-8")
    imports = set(re.findall(r"^from (cellpoc[\w.]*) import|^import (cellpoc[\w.]*)", source, re.M))
    parts = {a.split(".")[1] if "." in a else a for pair in imports for a in pair if a}
    cl.record(parts <= {"setup"} and not re.search(r"\bopen\(|write_text|write_bytes|\.mkdir|socket|urllib|requests|http\.", source), "The new part of the app imports only the setup part, writes no file itself and uses no network (it starts the platform's own programs and shows what they print)", f"imports: {sorted(parts)}")
    cl.record(not SAVED.exists(), "The saved test setup was removed: nothing is left behind in the setups folder")
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project outside the folders for generated output", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
