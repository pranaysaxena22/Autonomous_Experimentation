"""Health check for the operations console (the page at /console of the live program): the app a client is shown.

In plain words it checks that: the console is served only to this computer (a request with another Host is refused) with a secret in it that its own controls need (a control with a wrong secret is refused); its own page and script (not the 3D library inside it) name no outside web address, use no network
feature but plain requests to the program that served it (state, control, the two camera checks) and no randomness; every element the script looks for is in the page and no element name is used twice; every element the tour points at exists; the words it says about the product (the challenge, the solution, what it shows and what it does not)
are the same words as the rest of the app says; no developer wording (launcher and check file names, document and stage names, the proof of concept) is anywhere on it, with a self-test that the scan can fail; and, in real Chrome on a run part-way through: the overview, operator and lab manager views draw with the run's
own numbers, the camera check shows RIGHT BOTTLE for the first bottle and DEFECTIVE TABLET when a defective tablet is armed, the welcome opens on a first visit and not with ?welcome=off, and the tour opens at the step asked for. The older live page at / is still served. Nothing is written into the project.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.dashboard import client_about  # noqa: E402
from cellpoc.live import LiveServer, narration  # noqa: E402
from cellpoc.live import page as live_page  # noqa: E402
from cellpoc.live.pace import Pacer  # noqa: E402
from cellpoc.live.run import LiveRun  # noqa: E402
from cellpoc.shell import landing  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.live_check import http  # noqa: E402
from checks.models_check import project_files  # noqa: E402

LIVE = ROOT / "cellpoc" / "live"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
FORBIDDEN = [".bat", "run_app", "run_platform", "run_console", "make_reports", "check_", "docs/", "decisions.md", "settings.yaml", ".yaml", "stage 4", "stage 5", "proof of concept", "python_stand_in", "stand-in executor",
             "double-click", "black window", "traceback", "labpics", "pharmavision"]


def developer_words(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FORBIDDEN if w in low]


def real_page(run_to: float, query: str, want: str) -> str | None:
    """The console, drawn by real Chrome on a run that stands at `run_to` simulated seconds; the page's finished structure, or None if Chrome never produced one that has `want` in it (Chrome sometimes has to be asked again)."""
    run = LiveRun(pacer=Pacer(300), save_to=None)
    server = LiveServer(0, make_run=lambda: run, save_to=None)
    server.start_in_thread()
    try:
        if run_to > 0:
            run.fast_forward(run_to, 300)
        url = f"http://127.0.0.1:{server.port}/console" + ("?" + query if query else "")
        tmp = tempfile.mkdtemp(prefix="cc_")
        try:
            for budget in (14000, 10000, 18000, 12000, 16000):
                try:
                    done = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}\\p{budget}", f"--virtual-time-budget={budget}", "--dump-dom", url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=75)
                except subprocess.TimeoutExpired:
                    continue
                if want in done.stdout:
                    return done.stdout
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return None
    finally:
        server.shutdown()


def chrome_file(path: Path, query: str, want: str) -> str | None:
    """A page saved as a file (the recorded replay opens this way, with no program behind it), drawn by real Chrome; its finished structure, or None if Chrome never produced one with `want` in it."""
    tmp = tempfile.mkdtemp(prefix="cr_")
    try:
        for budget in (14000, 10000, 18000, 12000, 16000):
            try:
                done = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}\\p{budget}", f"--virtual-time-budget={budget}", "--dump-dom", path.as_uri() + "?" + query],
                                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=75)
            except subprocess.TimeoutExpired:
                continue
            if want in done.stdout:
                return done.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


def shown(dom: str | None) -> bool:
    """Whether the results table the page itself drew has the test result (the recording's own text sits in the page's script all the time, so that cannot be searched)."""
    return bool(dom) and re.search(r'<td class="num">71\.5</td>', dom) is not None


def text_of(dom: str, ident: str) -> str:
    m = re.search(rf'id="{ident}"[^>]*>(.*?)</(?:div|span|b|button|h2|p|ul|small)>', dom, re.S)
    return re.sub(r"<[^>]+>", " ", m.group(1)).strip() if m else ""


def main() -> int:
    cl = Checklist("OPERATIONS CONSOLE: the page a client is shown (three views, a camera verdict, a welcome and a tour), served to this computer only")
    before = project_files()
    template = (LIVE / "console_template.html").read_text(encoding="utf-8")
    script = (LIVE / "console_part3.js").read_text(encoding="utf-8")
    shim = (LIVE / "replay_shim.js").read_text(encoding="utf-8")

    # ---------------------------------------------------------------- the page itself
    ids = re.findall(r'\bid="([A-Za-z0-9_]+)"', template)
    made_by_script = set(re.findall(r'\bid="([A-Za-z0-9_]+)"', script))             # the welcome, the explanation and the tour build their own buttons
    used = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", script)) | {"stage"}
    tour_ids = {i for i in re.findall(r"id: '([A-Za-z0-9_]*)'", script) if i}
    missing = sorted((used | tour_ids) - set(ids) - made_by_script)
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    cl.record(not missing and not duplicates and len(tour_ids) >= 10,
              "Every element the console's script looks for is in the page, no element name is used twice, and every element the tour points at exists", f"missing {missing}; duplicated {duplicates}; {len(used)} looked for, {len(tour_ids)} on the tour")
    fetches = re.findall(r"fetch\(\s*('[^']*'|\"[^\"]*\")", script)
    banned = re.findall(r"https?://|WebSocket|XMLHttpRequest|import\(|Math\.random|navigator\.sendBeacon|eval\(|\.innerHTML\s*=\s*location", template + script + shim)
    cl.record(bool(fetches) and all(re.match(r"'(state\?|control|vision_check\?|tablet_check\?)", f) for f in fetches) and not banned and script.count("fetch('control'") == 1 and "'X-Live-Token': TOKEN" in script,
              "The console talks only to the program that served it (state, control with its secret, the two camera checks, the cell's picture), names no outside web address and uses no randomness, no web socket and no code built from text", f"{len(fetches)} requests; found {banned}")
    cl.record("speechSynthesis" in script and "v.localService" in script and "pickVoice" in script and "console-voice" in script and "Mute voice" in script,
              "The narrator's voice uses only the speech voices installed on this computer (nothing is sent to an online voice) and can be muted, the choice being remembered in this browser", "found" if "v.localService" in script else "not found")
    spoken = narration.lines({"headline": "H", "attempts_text": "A"})
    cl.record(len(spoken) == 16 and narration.hash_text("abc") == "1a47e90b" and len({narration.hash_text(s) for s in spoken}) == len(spoken) and "function hashText" in script,
              "The narrator's 16 sentences are read out of the page's own script, each has its own fingerprint, and the fingerprint arithmetic gives the known test value (so a recording is found by the sentence it was made from)", f"{len(spoken)} sentences")
    cl.record(not developer_words(template + script + shim), "No developer wording is anywhere in the console's page or script (launcher and check file names, document and stage names, the proof of concept, technical status lines)", f"found {developer_words(template + script + shim)}")
    planted = developer_words("press run_app.bat, then read docs/decisions.md (Stage 4)")
    cl.record(len(planted) >= 4 and not developer_words("Press play to run the demo."), "Self-test: the same scan finds developer wording in a sentence that has some, and finds none in a plain one (so the scan can fail)", f"found {planted}")

    # ---------------------------------------------------------------- the words are the app's own words
    shows_ok = all(line in script for line in client_about.CLIENT_SHOWS + client_about.CLIENT_DOES_NOT_SHOW)
    solution_ok = all(title in script and text in script for _, title, text in landing.SOLUTION)
    challenge_ok = all(text in script for _, _, text in landing.CHALLENGE)
    cl.record(shows_ok and solution_ok and challenge_ok,
              "What the console says about the product is what the rest of the app says: every line of 'what this shows and does not show' (the client About page), the three points of the solution and the three of the challenge (the front page) are in it word for word",
              f"limits {shows_ok}; solution {solution_ok}; challenge {challenge_ok}")

    # ---------------------------------------------------------------- the server side
    run = LiveRun(pacer=Pacer(300), save_to=None)
    server = LiveServer(0, make_run=lambda: run, save_to=None)
    server.start_in_thread()
    try:
        code, body = http(server.port, "/console")
        page = body.decode("utf-8") if code == 200 else ""
        foreign = http(server.port, "/console", headers={"Host": "evil.example"})[0]
        token = re.search(r'name="live-token" content="([^"]+)"', page)
        good_post = http(server.port, "/control", method="POST", body=json.dumps({"cmd": "speed", "value": 600}).encode(), headers={"Origin": f"http://127.0.0.1:{server.port}", "X-Live-Token": token.group(1) if token else "", "Content-Type": "application/json"})[0]
        bad_post = http(server.port, "/control", method="POST", body=json.dumps({"cmd": "speed", "value": 300}).encode(), headers={"Origin": f"http://127.0.0.1:{server.port}", "X-Live-Token": "wrong", "Content-Type": "application/json"})[0]
        old = http(server.port, "/")
        with_clips = live_page.build_console_page(run.layout, audio={"abcd1234": "QUJD"})
        without = live_page.build_console_page(run.layout, audio={})
        cl.record('window.NARRATION_AUDIO={"abcd1234":"QUJD"};' in with_clips and "window.NARRATION_AUDIO={};" in without,
                  "The page carries the narrator's recordings when there are some, and builds without them when there are none (the computer's own voice is then used)", "found" if 'window.NARRATION_AUDIO={"abcd1234":"QUJD"};' in with_clips else "not found")
        cl.record(code == 200 and token is not None and token.group(1) == server.token and foreign == 403 and good_post == 200 and bad_post == 403 and old[0] == 200 and b"Start the run" in old[1],
                  "The console at /console is served to this computer only (another Host is refused), carries the secret its own controls need (with it a control is accepted, with a wrong one it is refused), and the older live page at / is still served",
                  f"console {code}; foreign host {foreign}; with the secret {good_post}; wrong secret {bad_post}; live page {old[0]}")
    finally:
        server.shutdown()

    # ---------------------------------------------------------------- in real Chrome
    if CHROME.exists():
        first = real_page(330, "tab=operator&welcome=off", 'id="camBan"')
        if first and "RIGHT BOTTLE" in first:
            started = re.search(r'id="kStarted">(\d+)<', first)
            cl.record(started is not None and started.group(1) == "1" and "Fri 09 Oct" in text_of(first, "clockT") and "view-operator" in first and "Camera check: bottle" in first and "Trial 1" in first and "DRUG" in first and 'class="stp on"' in first,
                      "In real Chrome, on a run at its first ingredient bottle: the operator view draws with the run's own clock and trial count, the five-step pipeline lights the current step, and the camera check says RIGHT BOTTLE with the bottle's name and barcode",
                      f"trials started {started.group(1) if started else None}; clock '{text_of(first, 'clockT')}'")
        else:
            cl.record(False, "In real Chrome, on a run at its first ingredient bottle: the operator view draws and the camera check says RIGHT BOTTLE", "Chrome did not produce the page")
        bad = real_page(6330, "tab=operator&welcome=off&demo=defective", "DEFECTIVE TABLET")
        cl.record(bad is not None and 'class="ban bad"' in bad and "discard bin" in bad and "fl-bad" in bad,
                  "In real Chrome, with a defective tablet armed (the page's 'Inject event' scenario): the camera check says DEFECTIVE TABLET in red, says the tablet would go to the discard bin, and the red flashing frame is on", "found" if bad else "Chrome did not produce the page or the check")
        manager = real_page(40000, "tab=manager&welcome=off", "Not good")
        cl.record(manager is not None and "<svg" in manager and "Dissolution at 30 min" in manager and "Hardness (kP)" in manager and re.search(r'id="aRec"[^>]*>\d+<', manager) is not None and "<table>" in manager,
                  "In real Chrome, part-way through a run: the lab manager view draws the results table and the three charts (good recipes so far, dissolution, hardness) from the results the run has published", "found" if manager else "Chrome did not produce the page")
        welcome = real_page(0, "", "Welcome to the Autonomous Formulation Cell")
        quiet = real_page(0, "welcome=off", 'id="kStarted"')
        cl.record(welcome is not None and 'class="modal open"' in welcome and "The challenge" in welcome and "The solution" in welcome and quiet is not None and 'class="modal open"' not in quiet,
                  "In real Chrome, a first visit opens the welcome window (the challenge, the solution, the three points), and ?welcome=off opens the console without it", f"welcome {'open' if welcome and 'modal open' in welcome else 'not open'}; with welcome=off {'open' if quiet and 'modal open' in quiet else 'not open'}")
        tour = real_page(0, "welcome=off&tour=1&step=3", "step 4 of 14")
        cl.record(tour is not None and 'class="tour open"' in tour and "Choose the speed" in tour,
                  "In real Chrome, the tour opens at the step it is asked for (step 4 of 14, 'Choose the speed') over the real console", "found" if tour else "Chrome did not produce the page")
        guided = real_page(330, "welcome=off&guided=1&gstep=1", "step 2 of 9")
        cl.record(guided is not None and 'class="tour open demo"' in guided and "The camera checks the bottle" in guided and "RIGHT BOTTLE" in guided and "Resume narration" in guided,
                  "In real Chrome, the guided demo opens at the step it is asked for (step 2 of 9, paused after the first bottle check) with its narration over the real console showing RIGHT BOTTLE", "found" if guided else "Chrome did not produce the page")
        dark = real_page(0, "welcome=off&theme=dark", 'data-theme="dark"')
        light = real_page(0, "welcome=off&theme=light", 'data-theme="light"')
        cl.record(dark is not None and 'data-theme="dark"' in dark and ">Light</button>" in dark and light is not None and 'data-theme="light"' in light and ">Dark</button>" in light,
                  "In real Chrome, the console opens in the dark look or the light look as asked (?theme=), and the Theme button offers the other one", f"dark {'found' if dark else 'no page'}; light {'found' if light else 'no page'}")
        tiny = {"label": "ILLUSTRATIVE", "duration_s": 20000, "clock_start": "2026-10-09 18:00", "setup_id": "s", "setups": [{"id": "s", "label": "Test"}], "layout_id": run.layout.get("layout_id"), "setup_label": "Test",
                "timelines": [], "timeline_times": [], "events": [{"minute": 100, "when": "Fri 09 Oct 19:40", "kind": "measurement", "trial": 1, "message": "Trial 1: test finished", "published_at_sim_s": 6000}],
                "results": [{"trial": 1, "when": "Fri 09 Oct 19:40", "minute": 100, "published_at_sim_s": 6000, "dissolution_pct": 71.5, "hardness_kp": 8.2, "verdict": "Good", "good_so_far": 1}], "alerts": [],
                "summary": {"headline": "H", "attempts_text": "A"}, "vision": {}, "rest": "", "frames": {"0": ""}}
        replay_html = live_page.build_console_page(run.layout, token="", replay_script="window.REPLAY_DATA=" + json.dumps(tiny) + ";\n" + shim, audio={})
        folder = Path(tempfile.mkdtemp(prefix="cp_"))
        try:
            file = folder / "replay.html"
            file.write_text(replay_html, encoding="utf-8")
            late = chrome_file(file, "welcome=off&tab=manager&at=7000", 'id="kStarted"')
            early = chrome_file(file, "welcome=off&tab=manager&at=1000", 'id="kStarted"')
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        cl.record(late is not None and "Fri 09 Oct 19:56" in text_of(late, "clockT") and shown(late) and "recorded replay" in late and early is not None and "Fri 09 Oct 18:16" in text_of(early, "clockT") and not shown(early),
                  "A recorded replay opened as a plain file in real Chrome (no program behind it) shows the recording's own clock and its result once that moment has been reached, and does not show the result before its moment",
                  f"at 7000 s clock '{text_of(late, 'clockT') if late else None}', result shown {shown(late)}; at 1000 s clock '{text_of(early, 'clockT') if early else None}', result shown {shown(early)}")
    else:
        cl.skip("The console in real Chrome (the three views, the camera verdicts, the welcome and the tour)", "Google Chrome was not found here; the by-eye check is to double-click run_console.bat and look")

    after = project_files()
    cl.record(before == after, "Nothing in the project was changed by this check", "")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
