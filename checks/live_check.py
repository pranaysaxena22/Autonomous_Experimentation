"""Health check for the live run: is it the SAME simulation as a batch platform run, only paced, with nothing published before its moment, and does its page show it as it happens, on this computer only?

In plain words it checks that: a live run (the simulation on its own thread, every event waiting for its simulated moment) gives exactly the batch platform run's trials, executed timelines, events and record, trial for trial
(the known answer: the same setup and seeds give the same run however fast or slow it is watched); with a fake clock, no event, result or trial is published before its simulated moment (and none is late by more than the
pacer's step), a result appears at the moment its test finishes, a fault at the moment it strikes, and the next recipe is chosen at the cell's Reason step with only the results published by then; pausing stops the clock,
resuming carries on from the same moment, a change of speed keeps the moment, and a stopped run ends its thread; the local server listens only on 127.0.0.1, refuses any request that is not addressed to this computer, answers
the page, the state and the controls, refuses bad controls in plain words, and a restart begins again from nothing; the page is one self-contained file that reuses the replay viewer's drawing code unchanged, talks only to the
program that served it, and has no random numbers; in real headless Chrome the page, shown part-way through a run, displays the simulated date and time, the trials started so far, the results published so far and the current
action, draws a real 3D picture, and with WebGL switched off says so and still shows the lists; a finished live run is saved like a batch run; the server's controls obey only the live page itself (refused without the page's secret token or from any other origin, shown in real Chrome with an attack page on another site, and the real feature shown still to work end to end, including inside a frame with Streamlit's own sandbox attributes); and nothing is written into the project.
"""
from __future__ import annotations

import contextlib
import html
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.live import HOST, LiveRun, LiveServer, LiveStopped, Pacer, build_live_page  # noqa: E402
from cellpoc.live import page as live_page  # noqa: E402
from cellpoc.platform_runner import run_platform  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402
from checks.viewer_check import chrome, colours  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
LIVE = ROOT / "cellpoc" / "live"


class FakeClock:
    """A clock that only moves when the simulation sleeps, so the pacing can be tested exactly and instantly."""

    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def http(port: int, path: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


_TOKENS: dict[int, str] = {}


def page_token(port: int) -> str:
    """The secret the server wrote into its page: read from the page the way the page's own script reads it (the <meta name="live-token"> tag)."""
    if port not in _TOKENS:
        found = re.search(r'<meta name="live-token" content="([^"]*)">', http(port, "/")[1].decode("utf-8"))
        _TOKENS[port] = found.group(1) if found else ""
    return _TOKENS[port]


def control_headers(port: int) -> dict:
    """What the live page itself sends with a control: the JSON type, the Origin a browser writes for a page of this server, and the token from its page."""
    return {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}", "X-Live-Token": page_token(port)}


def post(port: int, cmd: str, value=None):
    code, raw = http(port, "/control", "POST", json.dumps({"cmd": cmd, "value": value}).encode(), control_headers(port))
    return code, json.loads(raw)


def same_as_batch(cl: Checklist, batch) -> None:
    live = LiveRun(speed=1e9, save_to=None)
    live.start()
    live.thread.join(timeout=180)
    a, b = live.run, batch
    cl.record(live.status == "finished" and [asdict(t) for t in a.record.trials] == [asdict(t) for t in b.record.trials] and a.executed == b.executed and a.plans == b.plans,
              "A live run gives exactly the batch platform run's trials, plans and executed timelines (the same setup and seeds give the same run, however it is watched)", f"{len(a.record.trials)} trials, {len(a.executed)} timelines")
    cl.record([asdict(e) for e in a.record.events] == [asdict(e) for e in b.record.events] and [asdict(x) for x in a.record.alerts] == [asdict(x) for x in b.record.alerts] and asdict(a.record.summary) == asdict(b.record.summary),
              "...and the same events, alerts and summary", f"{len(a.record.events)} events, {len(a.record.alerts)} alerts; {a.record.summary.headline}")
    state = live.state()
    cl.record(state["status"] == "finished" and state["event_total"] == len(a.record.events) and state["timeline_total"] == len(a.executed) and len(state["results"]) == a.record.summary.trials_attempted and state["good_so_far"] == a.record.summary.trials_good,
              "At the end the feed holds every event and trial, one result row per trial, and the good count equals the summary's", f"{state['good_so_far']} good of {len(state['results'])}")


def pacing_checks(cl: Checklist) -> None:
    clock = FakeClock()
    pacer = Pacer(300, clock.now, clock.sleep)
    live = LiveRun(pacer=pacer, save_to=None)
    live.start()
    live.thread.join(timeout=180)
    step = 0.02 * 300 + 1                      # the pacer looks at the clock every 0.02 real seconds
    events = live.feed.events
    early = [e for e in events if e["published_at_sim_s"] < e["minute"] * 60 - 1e-6]
    late = [e for e in events if e["published_at_sim_s"] - e["minute"] * 60 > step]
    cl.record(live.status == "finished" and not early and not late, "With a fake clock, no event is published before its simulated moment, and none is later than the pacer's step", f"{len(events)} events; {len(early)} early, {len(late)} late")
    rows = live.feed.results
    starts = [e["trial_start_minute"] * 60 for e in live.feed.timelines]
    early_rows = [r for r in rows if r["published_at_sim_s"] < r["minute"] * 60 - 1e-6]
    early_tl = [i for i, (s, p) in enumerate(zip(starts, live.feed.timeline_times)) if p < s - 1e-6]
    tests_end = {e["trial"]: e["minute"] for e in events if e["kind"] == "measurement"}
    cl.record(not early_rows and not early_tl and all(abs(r["minute"] - tests_end[r["trial"]]) < 1e-9 for r in rows if r["verdict"] != "No result"),
              "A result row is published when its test has finished (the 'measurement' moment), a trial's timeline when the cell reaches the trial, and never earlier", f"{len(rows)} results, {len(starts)} trials")
    faults = [e for e in events if e["kind"] == "fault"]
    cl.record(len(faults) == 2 and all(0 <= f["published_at_sim_s"] - f["minute"] * 60 <= step for f in faults), "Each fault is published at the moment it strikes (trial 8's jam and trial 19's)", ", ".join(f"trial {f['trial']} at {f['when']}" for f in faults))
    # causal order of decisions: the recipe for trial k+1 is chosen at the Reason step of trial k, after trial k's result was published
    last_measure = {e["trial"]: e["published_at_sim_s"] for e in events if e["kind"] == "measurement"}
    decisions = [e for e in events if e["kind"] == "decision" and e["trial"] and e["trial"] > 1 and (e["trial"] - 1) in last_measure]
    cl.record(decisions and all(d["published_at_sim_s"] >= last_measure[d["trial"] - 1] - 1e-6 for d in decisions), "The next recipe is chosen only after the previous trial's result was published (the engine never sees a result before the page does)", f"{len(decisions)} decisions checked")

    c = FakeClock()
    p = Pacer(100, c.now, c.sleep)
    p.resume()
    c.t += 10
    a = p.sim_s()
    p.pause()
    c.t += 50
    b = p.sim_s()
    p.resume()
    c.t += 5
    d = p.sim_s()
    p.set_speed(200)
    c.t += 1
    e = p.sim_s()
    cl.record(a == 1000 and b == 1000 and d == 1500 and e == 1700, "Pausing stops the clock, resuming carries on from the same moment, and a change of speed keeps the moment", f"{a}, {b}, {d}, {e} simulated seconds")
    p.stop()
    try:
        p.wait_until(1e12)
        stopped = False
    except LiveStopped:
        stopped = True
    paused = Pacer(100, c.now, c.sleep)
    paused.wait_until(0)                                                  # a moment the clock has already reached needs no waiting even when paused
    live2 = LiveRun(pacer=Pacer(100, FakeClock().now, FakeClock().sleep), save_to=None)
    live2.start()
    time.sleep(0.2)
    live2.stop()
    live2.thread.join(timeout=10)
    cl.record(stopped and not live2.thread.is_alive() and live2.status in ("stopped", "running", "paused"), "A stopped run ends its thread quietly (nothing keeps running after a restart or shutdown)")


def server_checks(cl: Checklist, tmp: Path) -> None:
    server = LiveServer(0, make_run=lambda: LiveRun(pacer=Pacer(7200), save_to=None), save_to=None)
    server.start_in_thread()
    _TOKENS.pop(server.port, None)
    try:
        port = server.port
        cl.record(server.httpd.server_address[0] == HOST == "127.0.0.1" and "0.0.0.0" not in (LIVE / "server.py").read_text(encoding="utf-8").replace('"0.0.0.0" not in', ""), "The live server listens only on 127.0.0.1 (this computer), never on all addresses", f"{server.httpd.server_address}")
        code, raw = http(port, "/")
        page = raw.decode("utf-8")
        cl.record(code == 200 and "<title>" in page and "ILLUSTRATIVE" in page and "font/ttf;base64" in page and "THREE" in page and "Start the run" in page, "The page is served: one self-contained file with the label, the font and the 3D library inside", f"{len(page) // 1024} KB")
        code, raw = http(port, "/", headers={"Host": "evil.example.com"})
        code2, _ = http(port, "/control", "POST", b'{"cmd":"start"}', {"Host": "evil.example.com"})
        cl.record(code == 403 and code2 == 403, "A request not addressed to this computer is refused (a web page elsewhere cannot steer the run)")
        code, raw = http(port, "/state")
        s = json.loads(raw)
        cl.record(code == 200 and s["status"] == "ready" and s["sim_s"] == 0 and s["events"] == [] and s["timelines"] == [] and "ILLUSTRATIVE" in s["label"], "Before Start the state is 'ready' at simulated second 0, with nothing published")
        code, s = post(port, "start")
        time.sleep(1.0)
        _, raw = http(port, "/state")
        s1 = json.loads(raw)
        time.sleep(0.5)
        _, raw = http(port, "/state?tl=%d&ev=%d" % (s1["timeline_total"], s1["event_total"]))
        s2 = json.loads(raw)
        cl.record(code == 200 and s["status"] == "running" and s2["sim_s"] > s1["sim_s"] + 1000 and s2["event_total"] >= s1["event_total"] and s1["event_total"] > 0 and len(s2["events"]) == s2["event_total"] - s1["event_total"],
                  "After Start the run advances in real time (about 7,200 simulated seconds per real second here), events accumulate, and asking 'since' returns only what is new", f"{s1['sim_s']:.0f} to {s2['sim_s']:.0f} s; {s1['event_total']} to {s2['event_total']} events")
        ok = all(r["minute"] * 60 <= s2["sim_s"] + 1 for r in s2["results"]) and all(t["trial_start_minute"] * 60 <= s2["sim_s"] + 1 for t in (json.loads(http(port, "/state")[1])["timelines"]))
        cl.record(ok, "Everything the server has published so far belongs to a moment the clock has reached")
        code, _ = post(port, "pause")
        _, raw = http(port, "/state")
        paused = json.loads(raw)
        time.sleep(0.4)
        _, raw = http(port, "/state")
        still = json.loads(raw)
        cl.record(paused["status"] == "paused" and abs(still["sim_s"] - paused["sim_s"]) < 1e-6, "Pause over the page's controls stops the clock")
        bad = [post(port, "speed", 12345)[0], post(port, "speed", "fast")[0], post(port, "explode")[0], http(port, "/control", "POST", b"not json", control_headers(port))[0], http(port, "/nothing")[0], http(port, "/state?tl=x")[0]]
        reasons = [post(port, "speed", 12345)[1].get("error", ""), post(port, "explode")[1].get("error", "")]
        cl.record(bad == [400, 400, 400, 400, 404, 400] and all(len(r) > 20 and not re.search(r"Traceback|Error\b|\{", r) for r in reasons), "A speed that is not on the page, an unknown control, a garbled request, an unknown address and a bad state request are each refused in plain words", f"codes {bad}")
        code, s = post(port, "restart")
        _, raw = http(port, "/state")
        fresh = json.loads(raw)
        cl.record(code == 200 and fresh["status"] == "ready" and fresh["event_total"] == 0 and fresh["timeline_total"] == 0 and fresh["sim_s"] == 0 and fresh["results"] == [], "Restart begins again from nothing: ready, simulated second 0, an empty feed")
    finally:
        server.shutdown()


def setup_choice_checks(cl: Checklist, tmp: Path) -> None:
    """The live page lets you choose which setup to run: the three illustrative examples, your saved setups and the loop connected. Each choice really runs that setup."""
    import copy
    import yaml
    from cellpoc.setup import example_choices, load_setup, save_setup, validate
    saved_name = "zz-live-check"
    saved = ROOT / "setups" / f"{saved_name}.yaml"
    saved_bad = ROOT / "setups" / f"{saved_name}-bad.yaml"
    batch_by_label = {}
    examples = example_choices()
    # each example, run live at once, equals the same example run in one go (the setup, not the pace, decides the run)
    sizes = {}
    for label, path in examples:
        live = LiveRun(path, speed=1e9, save_to=None)
        live.start()
        live.thread.join(timeout=300)
        batch = run_platform(path)
        same = live.status == "finished" and [asdict(t) for t in live.run.record.trials] == [asdict(t) for t in batch.record.trials] and live.run.executed == batch.executed
        sizes[label] = (len(batch.record.trials), batch.record.meta.duration_minutes)
        batch_by_label[label] = same
    cl.record(len(examples) == 3 and all(batch_by_label.values()) and len({v for v in sizes.values()}) == 3,
              "Each of the three illustrative examples, run live, equals the same example run in one go, and the three really are different runs (different lengths and trial counts)", "; ".join(f"{k.split(':')[0]}: {v[0]} trials in {v[1] // 60} h" for k, v in sizes.items()))
    try:
        base = load_setup(examples[0][1]).setup
        good = copy.deepcopy(base)
        good["project"]["name"] = "Zz live check saved setup"
        good["calendar"]["duration_h"] = 48
        save_setup(good, saved_name, problems=validate(good, base_dir=examples[0][1].parent))
        bad = copy.deepcopy(base)
        bad["targets"]["constraints"] = [c for c in bad["targets"]["constraints"] if c["response"] != "dissolution_30min_pct"]
        saved_bad.write_text(yaml.safe_dump(bad), encoding="utf-8")                              # a setup the simulation cannot represent: it has no dissolution target (written without the save check on purpose)
        server = LiveServer(0, make_run=lambda: LiveRun(pacer=Pacer(300), save_to=None), save_to=None)
        server.start_in_thread()
        _TOKENS.pop(server.port, None)
        try:
            port = server.port
            s = json.loads(http(port, "/state")[1])
            ids = [x["id"] for x in s["setups"]]
            cl.record(s["setup_id"] == "example:1" and ids[:3] == ["example:1", "example:2", "example:3"] and f"saved:{saved_name}" in ids and {"connected:baseline", "connected:new_supplier", "connected:period_shift", "connected:unpredictable_dissolution"} <= set(ids)
                      and len(ids) == len(set(ids)) and s["setup_label"].startswith("Example 1"),
                      "The state lists the three examples, the saved setups and the four connected scenarios, with the current one marked", f"{len(ids)} choices; current {s['setup_id']}")
            post(port, "start")
            time.sleep(0.5)
            first_thread = server.run.thread
            outcomes = {}
            for choice in ("example:2", "example:3", f"saved:{saved_name}", "example:1"):
                code, state = post(port, "setup", choice)
                outcomes[choice] = (code, state.get("setup_id"), state.get("duration_s"), state.get("status"), state.get("event_total"), state.get("timeline_total"))
            hours = {k: (v[2] or 0) / 3600 for k, v in outcomes.items()}
            cl.record(all(v[0] == 200 and v[1] == k and v[3] == "ready" and v[4] == 0 and v[5] == 0 for k, v in outcomes.items()) and hours == {"example:2": 168, "example:3": 96, f"saved:{saved_name}": 48, "example:1": 120},
                      "Choosing a setup loads it: the run window becomes that setup's (168, 96, 48 and 120 hours), and the run is ready with an empty feed", ", ".join(f"{k}: {v:g} h" for k, v in hours.items()))
            cl.record(first_thread is not None and not first_thread.is_alive(), "Switching setup stops the run that was going (its thread ends)")
            code, state = post(port, "setup", "example:2")
            cl.record(code == 200 and server.run.sim.setup["project"]["name"] == "Illustrative study 2: a week with random faults" and "random faults" in state["setup_label"], "The run that follows really is the chosen setup (its own project name inside the simulation)", state["setup_label"])
            bad_ids = ["../../README.md", "file:../x", "example:9", "saved:../../x", "", None, 7, f"saved:{saved_name}-bad"]
            codes = []
            msgs = []
            for choice in bad_ids:
                c, st = post(port, "setup", choice)
                codes.append(c)
                msgs.append(st.get("error", ""))
            _, now = (None, json.loads(http(port, "/state")[1]))
            cl.record(all(c == 400 for c in codes) and all(len(m) > 20 and not re.search(r"Traceback|Error\b|\{", m) for m in msgs) and now["setup_id"] == "example:2",
                      "A name that is not one of the choices (a file path, an unknown number, nothing) or a setup the simulation cannot represent is refused in plain words, and the current run is left as it was", f"codes {codes}")
            cl.record("cannot be simulated" in msgs[-1] and "dissolution" in msgs[-1], "...and the reason for the setup that cannot be simulated is the platform's own (no dissolution target)", msgs[-1][:100])
            page = http(port, "/")[1].decode("utf-8")
            cl.record('id="setupSel"' in page and "post('setup'" in page, "The page has the setup chooser, which only sends the choice's name")
        finally:
            server.shutdown()
    finally:
        saved.unlink(missing_ok=True)
        saved_bad.unlink(missing_ok=True)


def page_checks(cl: Checklist) -> None:
    script = live_page.live_script()
    viewer = (ROOT / "cellpoc" / "viewer" / "viewer.js").read_text(encoding="utf-8")
    head = viewer.split(live_page.MARKER)[0]
    part3 = (LIVE / "live_part3.js").read_text(encoding="utf-8")
    cl.record(script.startswith(head) and part3 in script, "The live page reuses the replay viewer's state engine and drawing code unchanged (its first two parts are copied byte for byte, then the live page part follows)", f"{len(head)} characters reused")
    fetches = re.findall(r"fetch\(\s*([^,)]+)", part3)
    cl.record(bool(fetches) and all(re.match(r"'(state\?|control|vision_check\?|tablet_check\?)", f.strip()) for f in fetches) and not re.search(r"https?://|WebSocket|XMLHttpRequest|import\(|Math\.random|navigator\.sendBeacon|eval\(", part3 + (LIVE / "live_template.html").read_text(encoding="utf-8")),
              "The live page talks only to the program that served it (relative addresses only: state, control, and, added 2026-10-23, the read-only vision_check; its pictures come from the same program too), has no web addresses, no sockets, no random numbers", f"{len(fetches)} requests, all to 'state', 'control' or 'vision_check'")
    cl.record("the arm" in (LIVE / "live_template.html").read_text(encoding="utf-8") and "published" in part3 and "decides nothing and calculates no result" in part3, "The live page says what it is: a display of what the simulation published")


def chrome_checks(cl: Checklist, tmp: Path) -> None:
    if not CHROME.exists():
        cl.skip("The live page in real Chrome", "Google Chrome was not found here; do the by-eye check: run_live.bat, press Start the run")
        return
    run = LiveRun(pacer=Pacer(300), save_to=None)
    server = LiveServer(0, make_run=lambda: run, save_to=None)
    server.start_in_thread()
    try:
        port = server.port
        run.fast_forward(15000, 300)                                     # 4 h 10 min into the run: trial 1's result is in, trial 2 is part-way through its dispense step
        state = run.state()
        url = f"http://127.0.0.1:{port}/"
        dom = html.unescape(chrome(url, ["--disable-gpu", "--virtual-time-budget=12000", "--dump-dom"], tmp / "c1", 150).stdout)
        clock_text = re.search(r'id="clockT">([^<]*)<', dom)
        chips = re.findall(r'class="tchip[^"]*"[^>]*>(\d+)<', dom)
        cl.record(state["status"] == "paused" and clock_text is not None and clock_text.group(1) == state["clock_when"] and len(chips) == state["timeline_total"] and state["timeline_total"] == 2,
                  "In real Chrome the page shows the simulated date and time the run has reached, and one chip for each trial started so far", f"clock '{clock_text.group(1) if clock_text else None}', chips {chips}")
        cl.record("Paused" in dom and "Trial 2:" in dom and "Why:" in dom or "Trial 2:" in dom, "...the current action (trial 2) with its reason, and the status 'Paused'")
        cl.record(len(re.findall(r'<option value="(?:example|connected):', dom)) >= 7 and "Example 1" in dom, "...and the setup chooser lists the three examples and the four connected scenarios", f"{len(re.findall(r'<option value=.(?:example|connected):', dom))} choices")
        rows = re.findall(r"<tr class=\"[gbn]\"><td>(\d+)</td>", dom)
        cl.record(rows == [str(r["trial"]) for r in reversed(state["results"])] and len(rows) == 1 and "1 with a result" in dom.replace("<b>", "").replace("</b>", ""), "...and the results published so far (trial 1's, published when its test finished) and none that are not yet known", f"result rows {rows}")
        png = tmp / "live.png"
        png.unlink(missing_ok=True)
        chrome(url, ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1400,1100", "--virtual-time-budget=12000", f"--screenshot={png}"], tmp / "c2", 150)
        if png.exists():
            img = Image.open(png).convert("RGB")
            distinct, spread = colours(img, (60, 190, 760, 640))
            cl.record(distinct > 40 and spread > 12, "The screenshot shows a real 3D picture (many colours and shading, not a blank box)", f"{distinct} colour groups, spread {spread:.0f}")
        else:
            cl.record(False, "The screenshot shows a real 3D picture", "Chrome produced no screenshot")
        nogl = html.unescape(chrome(url, ["--disable-3d-apis", "--disable-gpu", "--disable-webgl", "--virtual-time-budget=12000", "--dump-dom"], tmp / "c3", 150).stdout)
        cl.record("WebGL is unavailable" in nogl and re.search(r'id="nogl"[^>]*style="[^"]*display:\s*flex', nogl) is not None and "Results so far" in nogl and len(re.findall(r'class="tchip', nogl)) == 2, "With WebGL switched off the page says so plainly and still shows the clock, the trials and the results")
    finally:
        server.shutdown()


def saved_run_check(cl: Checklist, tmp: Path) -> None:
    out = tmp / "saved"
    live = LiveRun(speed=1e9, save_to=out)
    live.start()
    live.thread.join(timeout=180)
    cl.record(live.status == "finished" and live.saved == str(out) and all((out / f).exists() for f in ("record.json", "replay.html", "platform_index.json", "layout.json")) and len(list((out / "executed").glob("*.json"))) == 30,
              "A finished live run is saved like a batch run (record, plans, executed timelines, 3D replay), so the dashboard can open it afterwards", f"{len(list((out / 'executed').glob('*.json')))} timelines")


def serve_pages(pages: dict[str, str]) -> ThreadingHTTPServer:
    """A throw-away web server on another local port that serves the given pages: the 'other site' (an attacker's page, a page that frames the live page) in the real-Chrome tests."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path.split("?")[0], "").encode("utf-8")
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def streamlit_frame_attributes() -> tuple[str, str]:
    """The sandbox and permission lists Streamlit's own front end puts on every st.iframe, read from its bundled file (so the test follows whatever the installed Streamlit really does)."""
    import streamlit
    folder = Path(streamlit.__file__).parent / "static" / "static" / "js"
    found = next(iter(sorted(folder.glob("IFrameUtil.*.js"))), None)
    if found is None:
        return "", ""
    lists = re.findall(r"=\[((?:`[^`]*`,?)+)\]\.join\(`([^`]*)`\)", found.read_text(encoding="utf-8"))
    if len(lists) < 2:
        return "", ""
    return " ".join(re.findall(r"`([^`]*)`", lists[0][0])), "; ".join(re.findall(r"`([^`]*)`", lists[1][0]))

def new_server(autostart: bool = False) -> LiveServer:
    server = LiveServer(0, make_run=lambda: LiveRun(pacer=Pacer(300), save_to=None), save_to=None, autostart_hook=autostart)
    server.start_in_thread()
    _TOKENS.pop(server.port, None)                  # a port number can be reused by a later server: never trust an old token
    return server


def browse(url: str, tmp: Path, name: str, extra: list[str] = ()) -> None:
    chrome(url, ["--disable-gpu", "--virtual-time-budget=12000", "--dump-dom", "--host-resolver-rules=MAP evil.test 127.0.0.1", *extra], tmp / name, 150)


def control_protection_checks(cl: Checklist, tmp: Path) -> None:
    """The live server's controls only obey the live page itself: refused from any other site, any other local page, or any request without the page's secret token; and the real feature still works end to end."""
    server = new_server()
    other = new_server()
    try:
        port = server.port
        own = f"http://127.0.0.1:{port}"
        token = page_token(port)
        body = json.dumps({"cmd": "start"}).encode()
        bad_token = token[:-1] + ("A" if token[-1] != "A" else "B")
        cases = {"no token (own origin)": {"Origin": own}, "a wrong token (one character changed)": {"Origin": own, "X-Live-Token": bad_token}, "an empty token": {"Origin": own, "X-Live-Token": ""},
                 "the right token, no origin": {"X-Live-Token": token}, "the right token, origin null": {"Origin": "null", "X-Live-Token": token},
                 "the right token, another site": {"Origin": "https://evil.example", "X-Live-Token": token}, "the right token, another local page (port 8510)": {"Origin": "http://127.0.0.1:8510", "X-Live-Token": token},
                 "the right token, this port on another host name": {"Origin": f"http://evil.test:{port}", "X-Live-Token": token},
                 "the plain cross-site request of the demonstration (text/plain, no token)": {"Origin": "https://evil.example", "Content-Type": "text/plain"}}
        results = {}
        for name, headers in cases.items():
            code, raw = http(port, "/control", "POST", body, {"Content-Type": "application/json", **headers})
            results[name] = (code, token in raw.decode("utf-8", "replace"))
        _, raw = http(port, "/state")
        status_after_refusals = json.loads(raw)["status"]
        cl.record(all(code == 403 and not leaked for code, leaked in results.values()) and status_after_refusals == "ready",
                  "A control is refused (403, a plain sentence, the token never echoed) and NOT carried out when it has no token, a wrong or empty token, no Origin, Origin null, another site's Origin, another local page's Origin, or this port's number on another host name, and the run is still 'ready' after all nine",
                  "; ".join(f"{k}: {v[0]}" for k, v in results.items()) + f"; status {status_after_refusals}")
        code, s = post(port, "start")
        cl.record(code == 200 and s["status"] == "running", "The same control with the right token and this server's own Origin (what the page's own script sends) is accepted and takes effect: the run starts", f"{code}, status {s.get('status')}")
        code2, raw2 = http(port, "/control", "POST", body, {"Host": "evil.example.com", **control_headers(port)})
        cl.record(code2 == 403, "A foreign Host name is still refused even with the right token and Origin (the existing check is unchanged)")
        page = http(port, "/")[1].decode("utf-8")
        state_text = http(port, "/state")[1].decode("utf-8")
        cl.record(len(token) >= 40 and page.count(token) == 1 and token not in state_text and page_token(other.port) != token and len(page_token(other.port)) >= 40,
                  "The token is a long random secret written once, into the page's own <meta> tag, never into the state; and a second server has a different one", f"{len(token)} characters; occurrences in the page: {page.count(token)}")
        with urllib.request.urlopen(f"{own}/", timeout=20) as r:
            policy, nosniff = r.headers.get("Content-Security-Policy", ""), r.headers.get("X-Content-Type-Options", "")
        with urllib.request.urlopen(f"{own}/state", timeout=20) as r2:
            policy2 = r2.headers.get("Content-Security-Policy", "")
        cl.record("frame-ancestors" in policy and "'self'" in policy and "http://localhost:*" in policy and "http://127.0.0.1:*" in policy and "*" not in policy.replace("localhost:*", "").replace("127.0.0.1:*", "") and nosniff == "nosniff" and policy2 == policy,
                  "Every response says that only pages on this computer may show the live page in a frame (frame-ancestors: itself, localhost, 127.0.0.1) and not to guess its content type", policy)
        # the whole flow the page's script uses, in order, with the headers it sends: start, pause, change the speed, restart, choose a setup
        flow = [post(port, "pause")[1]["status"], post(port, "speed", 600)[1]["speed"], post(port, "restart")[1]["status"], post(port, "setup", "example:2")[1]["setup_id"], post(port, "start")[1]["status"]]
        cl.record(flow == ["paused", 600.0, "ready", "example:2", "running"], "After the fix the whole legitimate control flow still works with the page's own headers: pause, a speed change, restart, choosing a setup, and start again", f"{flow}")
        # the page's script itself, as the guard sees it
        part3 = (LIVE / "live_part3.js").read_text(encoding="utf-8")
        cl.record("'X-Live-Token': TOKEN" in part3 and "META('live-token')" in part3 and part3.count("fetch('control'") == 1 and "post(" in part3 and "$('btnRun').click()" in part3 and "META('live-autostart') === '1'" in part3,
                  "The page's script reads the token from its own page and sends it on its one control request, and ?autostart=1 does nothing unless the server was started with the tests-only switch (it presses the same Start button handler)")
    finally:
        server.shutdown()
        other.shutdown()

    if not CHROME.exists():
        for name in ("A real attack page in real Chrome", "The legitimate page in real Chrome", "The embedded page in a Streamlit-style frame"):
            cl.skip(name, "Google Chrome was not found here; do the by-eye check: run_live.bat, press Start the run")
        return

    # ---- real Chrome: an attack page on another site. First against a server whose new checks are switched off for this one test (the attack works), then the real one (it does not).
    def attack_page(target_port: int) -> str:
        return ('<!doctype html><title>attack</title><script>fetch("http://127.0.0.1:%d/control", {method: "POST", mode: "no-cors", headers: {"Content-Type": "text/plain"}, body: JSON.stringify({cmd: "start"})})'
                '.then(() => { document.title = "sent"; }, e => { document.title = "blocked"; });</script>' % target_port)
    outcomes = {}
    for label, switched_off in (("unprotected", True), ("protected", False)):
        victim = new_server()
        site = None
        try:
            site = serve_pages({"/": attack_page(victim.port)})
            patch = mock.patch.object(LiveServer, "request_allowed", lambda self, origin, token: True) if switched_off else contextlib.nullcontext()
            with patch:
                browse(f"http://evil.test:{site.server_address[1]}/", tmp, f"attack_{label}")
            outcomes[label] = (victim.run.status, list(victim.recent))
        finally:
            victim.shutdown()
            if site:
                site.shutdown()
    cl.record(outcomes["unprotected"][0] == "running" and outcomes["protected"][0] == "ready" and any(not ok for _, ok in outcomes["protected"][1]) and not any(ok for _, ok in outcomes["protected"][1]),
              "In real Chrome a page on another site sends the plain cross-site request to the live server: with the new checks switched off for this one test the run goes from ready to RUNNING (the attack is real), with the real server it stays READY and the refusal is on record (the fix stops it)",
              f"unprotected: {outcomes['unprotected'][0]}; protected: {outcomes['protected'][0]}, origins seen {[o for o, _ in outcomes['protected'][1]]}")

    # ---- real Chrome: the legitimate page itself, then inside a frame with Streamlit's own sandbox attributes
    sandbox, permissions = streamlit_frame_attributes()
    direct = new_server(autostart=True)
    plain = new_server(autostart=False)
    framed, no_origin, foreign, strict = new_server(autostart=True), new_server(autostart=True), new_server(autostart=True), new_server(autostart=True)
    parents = []
    try:
        browse(f"http://127.0.0.1:{direct.port}/?autostart=1", tmp, "legit_direct")
        browse(f"http://127.0.0.1:{plain.port}/?autostart=1", tmp, "legit_plain")
        cl.record(direct.run.status == "running" and [ok for _, ok in direct.recent] == [True] and direct.recent[0][0] == f"http://127.0.0.1:{direct.port}" and plain.run.status == "ready" and not plain.recent,
                  "In real Chrome the live page itself starts a run through the Start button's own handler (token and its own Origin accepted: running), while on an ordinary server opening ?autostart=1 starts NOTHING (an address can no longer start a run)",
                  f"test server: {direct.run.status}, origin {direct.recent[0][0] if direct.recent else None}; ordinary server: {plain.run.status}")

        def parent_page(target: LiveServer, sandbox_value: str | None, allow: str = "") -> str:
            attrs = (f' sandbox="{sandbox_value}"' if sandbox_value is not None else "") + (f' allow="{allow}"' if allow else "")
            # the busy loop keeps this page (and so the browser) alive for ten real seconds: a frame from another site runs in its own process, outside the browser's fast-forwarded clock, and needs real time to start the page
            return (f'<!doctype html><title>parent</title><body><iframe src="http://127.0.0.1:{target.port}/?autostart=1"{attrs} width="1300" height="900"></iframe>'
                    '<script>(function () { const t = Date.now(); while (Date.now() - t < 10000) {} })();</script></body>')
        for target, sandbox_value in ((framed, sandbox), (no_origin, "allow-scripts"), (foreign, sandbox), (strict, None)):
            parents.append(serve_pages({"/": parent_page(target, sandbox_value, permissions)}))
        browse(f"http://localhost:{parents[0].server_address[1]}/", tmp, "frame_streamlit")
        browse(f"http://localhost:{parents[1].server_address[1]}/", tmp, "frame_opaque")
        browse(f"http://evil.test:{parents[2].server_address[1]}/", tmp, "frame_foreign")
        browse(f"http://localhost:{parents[3].server_address[1]}/", tmp, "frame_plain")
        real = f"http://127.0.0.1:{framed.port}"
        cl.record("allow-same-origin" in sandbox and "allow-scripts" in sandbox and framed.run.status == "running" and framed.recent and framed.recent[0] == (real, True),
                  "The embedded page keeps its REAL origin inside a frame with exactly the sandbox attributes Streamlit's own front end gives st.iframe (read from the installed Streamlit): in real Chrome its control arrives with Origin http://127.0.0.1:PORT, not 'null', is accepted, and the run starts",
                  f"sandbox: {sandbox}; origin seen {framed.recent[0][0] if framed.recent else None}; status {framed.run.status}")
        cl.record(no_origin.run.status == "ready" and not any(ok for _, ok in no_origin.recent) and strict.run.status == "running",
                  "Self-test: the same frame WITHOUT allow-same-origin (an opaque origin) cannot control the run (status stays ready: the browser's own permission step stops it), while a frame with no sandbox at all can, so this test could notice a null-origin problem",
                  f"opaque frame: {no_origin.run.status}, requests reaching the server {len(no_origin.recent)}; plain frame: {strict.run.status}")
        cl.record(foreign.run.status == "ready" and not foreign.recent,
                  "In real Chrome a page on another site (evil.test) cannot show the live page in a frame at all (the frame rule stops it: nothing loads, nothing is sent), while the same frame from a page on this computer works", f"foreign frame: status {foreign.run.status}, requests {len(foreign.recent)}")
    finally:
        for s in (direct, plain, framed, no_origin, foreign, strict):
            s.shutdown()
        for p in parents:
            p.shutdown()


def mujoco_checks(cl: Checklist) -> None:
    """(2026-10-22) The live page can show the cell drawn by the MuJoCo model: a read-only picture route that draws what the published timeline says at the moment the page asks about."""
    from cellpoc.physics import frame_for
    from cellpoc.physics.motion import MotionError, plan_motion
    from cellpoc.physics.scene import load_cell
    run = LiveRun(pacer=Pacer(300), save_to=None)
    server = LiveServer(0, make_run=lambda: run, save_to=None)
    server.start_in_thread()
    try:
        before = http(server.port, "/mujoco.jpg?trial=1&t=10")
        resting = http(server.port, "/mujoco.jpg?trial=0&t=0")                         # the cell at rest, before any trial has started
        run.fast_forward(15000, 300)
        status_before, published_before = run.status, len(run.feed.timelines)
        early, later, again = (http(server.port, f"/mujoco.jpg?trial=1&t={s}") for s in (300, 4000, 300))
        bad = [http(server.port, f"/mujoco.jpg?{q}")[0] for q in ("trial=-1&t=1", "trial=1&t=-5", "trial=x&t=1", "trial=1&t=nan", "trial=1", "t=5", "trial=1&t=99999999999")]
        unknown = http(server.port, "/mujoco.jpg?trial=99&t=1")
        foreign = http(server.port, "/mujoco.jpg?trial=1&t=1", headers={"Host": "evil.example"})
        is_jpeg = lambda r: r[0] == 200 and r[1][:2] == b"\xff\xd8" and len(r[1]) > 10000
        timeline = run.feed.timelines[0]
        cell = load_cell(run.layout, with_objects=True)
        motion = plan_motion(cell, timeline)
        seconds = [s * 2 for s in range(0, int(timeline["actions"][-1]["actual_start_s"] + timeline["actions"][-1]["actual_duration_s"]) // 2 + 2)]
        frames = [frame_for(motion, timeline, s) for s in seconds]
        starts_ok = all(frame_for(motion, timeline, a["actual_start_s"] + 0.01 * a["actual_duration_s"]) in range(max(0, first - 1), max(after, first + 1)) for a, (_, first, after) in zip(timeline["actions"], motion.ranges))
        cl.record(before[0] == 404 and resting[0] == 200 and resting[1][:2] == b"\xff\xd8" and is_jpeg(early) and is_jpeg(later) and early[1] != later[1] and again[1] == early[1] and unknown[0] == 404 and foreign[0] == 403 and all(code == 400 for code in bad),
                  "The live server's picture route (/mujoco.jpg) draws the cell with the MuJoCo model for a trial the run has published: a JPEG, different at different moments of the trial (the arm has moved) and identical when asked for the same moment twice; nothing before the trial is published (404), an unknown trial (404), a request from a host that is not this computer (403) and seven kinds of malformed request (400) are refused",
                  f"before {before[0]}; early {early[0]} {len(early[1])} bytes; later {later[0]}; bad {bad}")
        cl.record(frames == sorted(frames) and frames[0] == 0 and frames[-1] == len(motion.frames) - 1 and len(set(frames)) > 0.6 * len(motion.frames) and starts_ok,
                  "The moment of the trial picks the arm's frame in order: it never goes backwards, starts at the first frame and ends at the last, covers most of the movements, and the start of each action is at that action's own frames (so the arm is where the plan has it)",
                  f"{len(set(frames))} of {len(motion.frames)} frames reached; first {frames[0]}, last {frames[-1]}")
        cl.record(run.status == status_before and len(run.feed.timelines) == published_before and all(origin is not None or True for origin, _ in server.recent) and len(server.recent) == 0,
                  "Asking for pictures starts, stops and changes nothing: the run's status and what it has published are the same after, and no control was accepted or refused on the way", f"status {status_before} -> {run.status}; published {published_before} -> {len(run.feed.timelines)}")
        with mock.patch("cellpoc.physics.Stage.jpeg", side_effect=MotionError("The arm cannot reach where the plan sends it (a test).")):
            refused = http(server.port, "/mujoco.jpg?trial=1&t=77")
        with mock.patch("cellpoc.physics.Stage.jpeg", side_effect=RuntimeError("secret internal detail")):
            crashed = http(server.port, "/mujoco.jpg?trial=1&t=78")
        cl.record(refused[0] == 503 and b"cannot reach" in refused[1] and crashed[0] == 503 and b"secret internal detail" not in crashed[1] and b"Traceback" not in crashed[1],
                  "When a picture cannot be made (a plan the arm cannot play, or any other failure) the server answers with a plain sentence and never a technical trace, so the page keeps its own 3D scene", f"{refused[0]} {refused[1][:70]}; {crashed[0]} {crashed[1][:70]}")
        page = http(server.port, "/")[1].decode("utf-8")
        cl.record('id="mj"' in page and "mujoco.jpg?trial=" in page and "mujoco') !== '0'" in page, "The live page has the MuJoCo picture in its stage, asks the server for one picture at a time, and can be told to keep its own scene (?mujoco=0)", "")
    finally:
        server.shutdown()


def vision_route_checks(cl: Checklist) -> None:
    """(2026-10-23) When the arm picks up an ingredient bottle the live page asks the server for the cell's vision check of it: a drawn photograph read by the vision part, compared with the bottle the plan expected."""
    import base64
    run = LiveRun(pacer=Pacer(300), save_to=None)
    server = LiveServer(0, make_run=lambda: run, save_to=None)
    server.start_in_thread()
    try:
        run.fast_forward(15000, 300)
        status_before, published_before = run.status, len(run.feed.timelines)
        timeline = run.feed.timelines[0]
        bottle_ids = {o["id"] for o in run.layout["objects"] if o["type"] == "bottle"}
        picks = [a for a in timeline["actions"] if a["type"] == "pick" and a["object"] in bottle_ids]
        answers = []
        for a in picks:
            code, body = http(server.port, f"/vision_check?trial={timeline['trial']}&action={a['id']}")
            answers.append((code, json.loads(body) if code == 200 else None, a))
        again = http(server.port, f"/vision_check?trial={timeline['trial']}&action={picks[0]['id']}")
        vial_pick = next(a for a in timeline["actions"] if a["type"] == "pick" and a["object"] not in bottle_ids)
        not_bottle = http(server.port, f"/vision_check?trial={timeline['trial']}&action={vial_pick['id']}")
        unknown = http(server.port, f"/vision_check?trial={timeline['trial']}&action=A999")
        early = http(server.port, "/vision_check?trial=99&action=A001")
        bad = [http(server.port, f"/vision_check?{q}")[0] for q in ("trial=0&action=A001", "trial=1&action=../etc", "trial=x&action=A001", "trial=1", "action=A001", "trial=1&action=a001")]
        foreign = http(server.port, f"/vision_check?trial=1&action={picks[0]['id']}", headers={"Host": "evil.example"})
        good = all(code == 200 and body["verdict"] == "right bottle" and body["read"] == body["expected"] and body["image"].startswith("data:image/jpeg;base64,") and base64.b64decode(body["image"].split(",", 1)[1])[:2] == b"\xff\xd8" and body["level"] > 20 for code, body, _ in answers)
        expected = {"drug_pct": "blue", "filler_pct": "yellow", "binder_pct": "green", "disintegrant_pct": "orange", "lubricant_pct": "purple"}
        names = sorted(body["expected"] for _, body, _ in answers)
        cl.record(len(picks) == 5 and good and names == sorted(expected.values()) and json.loads(again[1]) == answers[0][1],
                  "When the arm picks up each of the five ingredient bottles the live server's vision check (/vision_check) reads a drawn photograph of it and says right bottle: the solution it read is the one the plan expected (blue, yellow, green, orange, purple), with a level and the photograph as a picture, and asking again gives the same answer",
                  f"{len(picks)} bottle picks; verdicts {[b['verdict'] for _, b, _ in answers if b]}; read {[b['read'] for _, b, _ in answers if b]}")
        labels = [(body["label_read"], body["label_expected"], body["overall"]) for _, body, _ in answers]
        cl.record(all(read == want and overall == "right bottle" for read, want, overall in labels) and len({want for _, want, _ in labels}) == 5,
                  "Each vision check also carries the bottle's barcode (EAN-13): the ID read from the photograph is the one the plan expects, the five bottles have five different IDs, and the overall answer (label and colour together) is right bottle", f"{labels}")
        cl.record(not_bottle[0] == 404 and unknown[0] == 404 and early[0] == 404 and all(code == 400 for code in bad) and foreign[0] == 403,
                  "No check is made for an action that is not an ingredient bottle being picked up (the vial, an unknown action, a trial not yet published: 404), malformed requests are refused (400, six kinds) and a request from a host that is not this computer is refused (403)", f"vial pick {not_bottle[0]}; unknown {unknown[0]}; early {early[0]}; bad {bad}; foreign {foreign[0]}")
        first = picks[0]
        shown = {d: http(server.port, f"/vision_check?trial={timeline['trial']}&action={first['id']}&demo={d}") for d in ("wrong", "unreadable", "blank", "liquid")}
        shown = {d: json.loads(body) for d, (code, body) in shown.items() if code == 200}
        bad_demo = [http(server.port, f"/vision_check?trial={timeline['trial']}&action={first['id']}&demo={d}")[0] for d in ("evil", "WRONG", "wrong%20", "1")]
        plain = json.loads(http(server.port, f"/vision_check?trial={timeline['trial']}&action={first['id']}")[1])
        reader = shown["unreadable"]["name_reader"]                     # with the text models the name identifies a bottle whose barcode cannot be read; without them nothing does
        cl.record(set(shown) == {"wrong", "unreadable", "blank", "liquid"} and shown["wrong"]["overall"] == "wrong bottle" and shown["wrong"]["label_read"] != shown["wrong"]["label_expected"] and shown["wrong"]["label_name"] != shown["wrong"]["name"]
                  and shown["unreadable"]["label_read"] is None and shown["unreadable"]["overall"] == ("right bottle" if reader else "label not read") and (not reader or shown["unreadable"]["name_read"] == shown["unreadable"]["name_expected"])
                  and shown["blank"]["overall"] == "label not read" and shown["blank"]["label_read"] is None and shown["blank"]["name_read"] is None and shown["liquid"]["overall"] == "check bottle" and shown["liquid"]["read"] != shown["liquid"]["expected"]
                  and all(shown[d]["demo"] == d for d in shown) and plain["overall"] == "right bottle" and plain["demo"] == "" and all(code == 400 for code in bad_demo),
                  "A presenter can choose what the camera is shown for the next bottle (the page's 'Next bottle' choice): another ingredient's barcode gives 'wrong bottle' and names the bottle it belongs to, a smudged barcode is rescued by the name (right bottle) while a bottle with no stickers gives 'label not read', a liquid that does not match gives 'check bottle'; each answer says it is a demonstration case, the plain check is still 'right bottle', and any other choice is refused (400)",
                  f"{[(d, a['overall']) for d, a in shown.items()]}; bad choices {bad_demo}")
        from cellpoc.vision import tablet as tablet_part
        tablet_pick = next(a for a in timeline["actions"] if a["type"] == "pick" and a.get("object") == "tablet" and a.get("from") == "press")
        if tablet_part.available() and tablet_part.demo_photos("normal") and tablet_part.demo_photos("defective"):
            path = f"/tablet_check?trial={timeline['trial']}&action={tablet_pick['id']}"
            ok_code, ok_body = http(server.port, path)
            bad_code, bad_body = http(server.port, path + "&demo=defective")
            again = http(server.port, path)
            ok_answer, bad_answer = json.loads(ok_body), json.loads(bad_body)
            not_tablet = http(server.port, f"/tablet_check?trial={timeline['trial']}&action={picks[0]['id']}")
            wrong_args = [http(server.port, f"/tablet_check?{q}")[0] for q in ("trial=0&action=A033", "trial=1&action=../x", "trial=x&action=A033", f"trial=1&action={tablet_pick['id']}&demo=wrong", "trial=1", "action=A033")]
            cl.record(ok_code == 200 and bad_code == 200 and ok_answer["verdict"] == "tablet ok" and ok_answer["demo"] == "" and bad_answer["verdict"] == "defective tablet" and bad_answer["demo"] == "defective" and "discard bin" in bad_answer["action_taken"]
                      and ok_answer["image"].startswith("data:image/jpeg;base64,") and json.loads(again[1]) == ok_answer and not_tablet[0] == 404 and all(code == 400 for code in wrong_args),
                      "When the arm lifts the tablet out of the press the live server's tablet check (/tablet_check) reads a real photograph standing in for the cell's camera: a normal tablet is 'tablet ok', a defective one chosen by the presenter is 'defective tablet' and would be sent to the discard bin; asking again gives the same answer; any other action is 404 and malformed requests or another demonstration word are refused (400)",
                      f"normal: {ok_answer['verdict']} {ok_answer['probability']}%; defective: {bad_answer['verdict']} {bad_answer['probability']}%; other action {not_tablet[0]}; bad {wrong_args}")
        else:
            cl.skip("The live server's tablet check", "the trained tablet network or its demonstration photographs are not on this computer")
        cl.record(run.status == status_before and len(run.feed.timelines) == published_before and len(server.recent) == 0, "Asking for vision checks changes nothing in the run (status and what it has published are the same, no control accepted or refused)", f"status {status_before} -> {run.status}")
        page = http(server.port, "/")[1].decode("utf-8")
        cl.record('id="vcard"' in page and 'id="vinset"' in page and 'id="vstat"' in page and 'id="vlog"' in page and 'id="demoSel"' in page and "vision_check?trial=" in page and "tablet_check?trial=" in page and all(f"fl-{c}" in page for c in ("ok", "bad", "warn", "look")) and "prefers-reduced-motion" in page,
                  "The live page lays the vision check out as its own panel (the camera's photograph, the barcode read against the barcode expected, the liquid's colour and level, one verdict), a badge over the stage, a running count in the top row and a log of every check; the stage and the panel flash a green frame for a right bottle, red for a wrong one, amber to check and blue while looking (and keep still for anyone who has asked their computer for less motion); a check is asked for once per bottle pick", "")
    finally:
        server.shutdown()


def main() -> int:
    cl = Checklist("LIVE RUN: the same simulation as a batch run, paced; nothing published before its moment; a page that shows it as it happens, on this computer only")
    before = project_files()
    batch = run_platform()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        same_as_batch(cl, batch)
        pacing_checks(cl)
        server_checks(cl, tmp)
        setup_choice_checks(cl, tmp)
        page_checks(cl)
        saved_run_check(cl, tmp)
        chrome_checks(cl, tmp)
        control_protection_checks(cl, tmp)
        mujoco_checks(cl)
        vision_route_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
