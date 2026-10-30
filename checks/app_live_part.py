"""Stage C of the unified app (the live view inside it, started and stopped by a supervisor), as a part of check_app.bat.

In plain words it checks, against the REAL live program started for real on spare ports, that: the supervisor starts it, finds it listening on 127.0.0.1 only (read from the operating system, with the computer's other network address refused), starts nothing
a second time, refuses a port held by something else and leaves that program alone, and stops it so that nothing is left listening or running; that a deliberately wrong program which listens on every address (0.0.0.0) is first shown to be reachable from the computer's
other network address when started without the supervisor, and is then detected, killed and refused by the supervisor, with nothing left running; that a program which starts on 127.0.0.1 and later moves to every address is caught by the supervisor's next status
refresh; that when the program that owns the supervisor is killed without warning the live program dies with it (no orphan); that the Live run page of the app starts nothing by itself, shows each state truthfully, starts and stops the real program from its buttons and
puts the live view in a frame at the constant loopback address; that the legitimate control flow still works end to end against the program the app started; and, in real Chrome, on the ACTUAL unified app with the ACTUAL Streamlit frame, that the live page inside it
presses its own Start button and the run starts (the token and the page's real origin accepted).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (2026-10-24) The unified app opens in its CLIENT view by default; these checks are about the developer view (every page, the technical detail, which is unchanged), so they ask for it. The client view has its own check (checks/client_view_check.py).
os.environ["CELLPOC_DEVELOPER"] = "1"

PLATFORM = ROOT / "runs" / "platform"
LIVE_PAGE = "cellpoc/shell/pages/live_run.py"
PORTS = {"real": 8571, "held": 8572, "bad": 8573, "late": 8574, "orphan": 8575, "page": 8576, "chrome_live": 8577, "chrome_app": 8578, "connected": 8579, "chrome_live2": 8585, "chrome_app2": 8586}
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SENTENCE = "simulation with illustrative values"

BAD_PROGRAM = "import http.server, sys; p = int(sys.argv[1]); s = http.server.ThreadingHTTPServer(('0.0.0.0', p), http.server.SimpleHTTPRequestHandler); print('ready', flush=True); s.serve_forever()"
LATE_PROGRAM = ("import socket, sys, time; p = int(sys.argv[1]); a = socket.socket(); a.bind(('127.0.0.1', p)); a.listen(); print('ready', flush=True); time.sleep(4); a.close(); "
                "b = socket.socket(); b.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); b.bind(('0.0.0.0', p)); b.listen(); time.sleep(120)")


def bad_command(port: int) -> list[str]:
    return [sys.executable, "-c", BAD_PROGRAM, str(port)]


def late_command(port: int) -> list[str]:
    return [sys.executable, "-c", LATE_PROGRAM, str(port)]


def http_get(port: int, path: str = "/") -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=20) as r:
        return r.read()


def control(port: int, token: str, cmd: str, value=None) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/control", data=json.dumps({"cmd": cmd, "value": value}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}", "X-Live-Token": token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def page_token(port: int) -> str:
    found = re.search(r'<meta name="live-token" content="([^"]*)">', http_get(port).decode("utf-8"))
    return found.group(1) if found else ""


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def run(cl) -> None:
    from checks.launchers_check import kill_tree, listening_on, look
    from cellpoc.live_supervisor import Supervisor
    from cellpoc.live_supervisor import supervisor as sv
    from streamlit.testing.v1 import AppTest

    def addresses(port: int) -> list[str]:
        return listening_on(port)                  # the checker's own read of the operating system, not the supervisor's

    lan_is_loopback = socket.gethostbyname(socket.gethostname()).startswith("127.")

    # ---------------------------------------------------------------- the real live program, started and stopped by the supervisor
    port = PORTS["real"]
    s = Supervisor(port)
    try:
        t0 = time.time()
        st = s.start()
        seen, reachable = look(port) if st.state == "running" else ([], False)
        pid = s.proc.pid if s.proc else 0
        health = http_get(port, "/health") if st.state == "running" else b""
        cl.record(st.state == "running" and bool(seen) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in seen) and not reachable and health == b"ok" and st.address == f"http://127.0.0.1:{port}/",
                  "The supervisor starts the real live program: the operating system reports it listening on 127.0.0.1 only, the computer's other network address cannot connect to it, and the page answers through 127.0.0.1",
                  f"{st.state} in {time.time() - t0:.1f} s; listening on {seen}")
        before = sorted(addresses(port))
        again = s.start()
        cl.record(again.state == "running" and sorted(addresses(port)) == before and s.proc.pid == pid, "Starting it again while it runs starts nothing new (the same program, the same single listener)", f"{again.state}")
        stopped = s.stop()
        time.sleep(1)
        cl.record(stopped.state == "stopped" and not addresses(port) and not alive(pid), "Stop ends it and confirms nothing is left: the port no longer listens and the program is gone", f"{stopped.state}; listening {addresses(port)}")
        cl.record("nothing to stop" in s.stop().text and s.status().state == "stopped", "Stopping when nothing runs does nothing and says so", s.stop().text)
        second = s.start()
        cl.record(second.state == "running", "...and it can be started again after a stop", second.state)
    finally:
        s.stop()

    # ---------------------------------------------------------------- a port held by something else is refused and that program is left alone
    port = PORTS["held"]
    holder = socket.socket()
    holder.bind(("127.0.0.1", port))
    holder.listen()
    try:
        s = Supervisor(port)
        st = s.start()
        cl.record(st.state == "refused" and "did not start" in st.text and s.proc is None and bool(addresses(port)), "A port held by a program the app did not start is refused with a plain sentence, no program is started, and the other program is left alone (still listening)", st.text[:100])
    finally:
        holder.close()

    # ---------------------------------------------------------------- the planted wrong programs: the self-test that nothing the app starts can end up on 0.0.0.0
    port = PORTS["bad"]
    direct = subprocess.Popen(bad_command(port), cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    try:
        exposed, reachable = [], False
        for _ in range(40):
            exposed, reachable = look(port)
            if exposed:
                break
            time.sleep(0.5)
    finally:
        kill_tree(direct)
        time.sleep(1)
    cl.record(any(a.startswith(("0.0.0.0:", "[::]:")) for a in exposed) and (reachable or lan_is_loopback),
              "Self-test, step 1: the deliberately wrong program, started WITHOUT the supervisor's address check, listens on every address (0.0.0.0) and the computer's other network address can connect to it (the exposure is real)", f"listening on {exposed}; outside connection {'succeeded' if reachable else 'not possible on this computer'}")
    s = Supervisor(port, command_for=bad_command)
    st = s.start()
    time.sleep(1)
    cl.record(st.state == "refused" and "other than this computer" in st.text and not addresses(port) and s.proc is not None and not alive(s.proc.pid),
              "Self-test, step 2: the same wrong program started BY the supervisor is detected, killed and refused (a plain sentence naming the address); the port no longer listens and the program is gone", st.text[:110])
    port = PORTS["late"]
    s = Supervisor(port, command_for=late_command)
    try:
        st = s.start()
        first = st.state
        time.sleep(6)                                             # the program now closes its 127.0.0.1 listener and opens one on every address
        st2 = s.status(force=True)
        time.sleep(1)
        cl.record(first == "running" and st2.state == "refused" and not addresses(port) and not alive(s.proc.pid),
                  "Self-test, step 3: a program that starts on 127.0.0.1 and LATER moves to every address is caught by the supervisor's next status refresh (the address read is repeated while it runs), killed and refused", f"at start: {first}; after the change: {st2.state}")
    finally:
        s.stop()

    # ---------------------------------------------------------------- no orphan, even when the owner is killed without warning
    port = PORTS["orphan"]
    owner_code = (f"import sys, time\nsys.path.insert(0, r'{ROOT}')\nfrom cellpoc.live_supervisor import Supervisor\ns = Supervisor({port})\nst = s.start()\nprint('STATE', st.state, 'LIVEPID', s.proc.pid, flush=True)\ntime.sleep(300)\n")
    owner = subprocess.Popen([sys.executable, "-c", owner_code], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    line = ""
    for _ in range(60):
        line = owner.stdout.readline()
        if "STATE" in line:
            break
    running_before = bool(addresses(port))
    subprocess.run(["taskkill", "/PID", str(owner.pid), "/F"], capture_output=True)           # no /T, no warning: the owner gets no chance to clean up
    gone = False
    for _ in range(30):
        if not addresses(port):
            gone = True
            break
        time.sleep(0.5)
    cl.record("running" in line and running_before and gone,
              "No orphan: when the program that owns the supervisor is killed without any warning (no chance to clean up), Windows kills the live program with it (the safety container) and its port closes", f"{line.strip()[:60]}; listening before the kill: {running_before}; closed after: {gone}")

    # ---------------------------------------------------------------- the Live run page of the app
    port = PORTS["page"]
    page_supervisor = Supervisor(port)
    os.environ["CELLPOC_RECORD"] = str(PLATFORM)
    try:
        with mock.patch.object(sv, "_shared", page_supervisor):
            app = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
            app.run()
            app.switch_page(LIVE_PAGE)
            app.run()
            buttons = {b.key: b for b in app.button}
            idle_ok = not app.exception and not buttons["live_start"].disabled and buttons["live_stop"].disabled and not app.get("iframe") and not addresses(port) and page_supervisor.proc is None
            sentence_once = sum(t.lower().count(SENTENCE) for t in [m.value for m in app.main.markdown if not m.value.lstrip().startswith("<style>")] + [c.value for c in app.caption]) == 1
            cl.record(idle_ok and sentence_once, "The Live run page starts nothing by itself: visiting it draws a 'not running' status with Start enabled and Stop disabled, no frame, no program and no listener; and the illustrative sentence appears once", f"exception {bool(app.exception)}; listening {addresses(port)}")
            buttons["live_start"].click().run()
            app.run()
            frames = [e.proto.src for e in app.get("iframe")]
            running = not app.exception and frames == [f"http://127.0.0.1:{port}/?embedded=1"] and bool(addresses(port)) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in addresses(port))
            cl.record(running, "Pressing Start on the page starts the real program and the page then shows it running on this computer only, with the live view in a frame at the constant loopback address (plus the look-only ?embedded=1 that hides its title band) and nothing else", f"frames {frames}; listening {addresses(port)}")
            # the legitimate path, end to end, against the program the app started: read the page's token as the page does, send the headers the page sends, control the run
            token = page_token(port)
            flow = [control(port, token, "start")["status"], control(port, token, "pause")["status"], control(port, token, "speed", 600)["speed"], control(port, token, "restart")["status"], control(port, token, "setup", "example:3")["setup_id"], control(port, token, "start")["status"]]
            cl.record(flow == ["running", "paused", 600.0, "ready", "example:3", "running"], "End to end through the app: against the live program the app started, the page's own flow still works with the headers the page sends (start, pause, change speed, restart, choose a setup, start)", f"{flow}")
            try:
                control(port, "wrong-token", "pause")
                refused = False
            except urllib.error.HTTPError as exc:
                refused = exc.code == 403
            cl.record(refused and json.loads(http_get(port, "/state"))["status"] == "running", "...and a control without the page's token is refused by that same program and changes nothing", "")
            buttons = {b.key: b for b in app.button}
            buttons["live_stop"].click().run()
            app.run()
            cl.record(not app.exception and not app.get("iframe") and not addresses(port) and page_supervisor.proc is not None and not alive(page_supervisor.proc.pid) and buttons["live_start"] is not None,
                      "Pressing Stop on the page ends the program: the frame is gone, nothing listens and nothing runs", f"listening {addresses(port)}")
    finally:
        page_supervisor.stop()
        os.environ.pop("CELLPOC_RECORD", None)

    # ---------------------------------------------------------------- the connected loop's live view (the 8511 app): its own port, the connected scenario, side by side with the other
    from cellpoc.live.embedded_main import parse
    from cellpoc.shell import live_host
    from cellpoc import run_store
    try:
        Supervisor(PORTS["connected"], connected="not_a_scenario")
        refused_name = False
    except ValueError:
        refused_name = True
    cl.record(refused_name and parse(["--port", "8600", "--connected", "not_a_scenario"]) is None and parse(["--port", "8600", "--connected", "baseline"]) == (8600, "baseline", False)
              and sv.live_command(8600) == sv.live_command(8600, "not_a_scenario") and sv.live_command(8600, "baseline")[-2:] == ["--connected", "baseline"] and not addresses(PORTS["connected"]),
              "A scenario name that is not one of the four known names is refused before anything starts (by the supervisor and by the live program's own argument check), and the command carries --connected only for a known name", f"nothing listening on {PORTS['connected']}: {not addresses(PORTS['connected'])}")
    plain_sv = Supervisor(PORTS["real"])
    connected_sv = Supervisor(PORTS["connected"], connected="baseline")
    try:
        plain_state = plain_sv.start()
        t0 = time.time()
        conn_state = connected_sv.start()
        took = time.time() - t0
        seen = addresses(PORTS["connected"])
        state = json.loads(http_get(PORTS["connected"], "/state")) if conn_state.state == "running" else {}
        cl.record(conn_state.state == "running" and bool(seen) and all(a.startswith(("127.0.0.1:", "[::1]:")) for a in seen) and state.get("setup_id") == "connected:baseline" and "connected" in state.get("setup_label", "").lower(),
                  "The connected loop's live view starts for real from the supervisor (it reads the data and judges the models first) on 127.0.0.1 only, and the page's current choice is the connected baseline scenario", f"{conn_state.state} in {took:.0f} s; listening on {seen}; choice {state.get('setup_id')}")
        both = bool(addresses(PORTS["real"])) and bool(addresses(PORTS["connected"])) and plain_state.state == "running"
        connected_sv.stop()
        cl.record(both and not addresses(PORTS["connected"]) and bool(addresses(PORTS["real"])) and plain_sv.status().state == "running",
                  "Two apps' live views run side by side, each on its own port (the example on one, the connected loop on the other); stopping one leaves the other running", f"both listening: {both}; after stopping the connected one: other {addresses(PORTS['real'])}")
    finally:
        plain_sv.stop()
        connected_sv.stop()
    ports_ok = []
    for app_port, expected in ((8510, 8514), (8511, 8515), (8501, 8514)):
        with mock.patch.object(sv, "_shared", None), mock.patch.object(live_host.st, "get_option", lambda name, p=app_port: p):
            ports_ok.append(live_host.supervisor_for(run_store.load(PLATFORM)).port == expected)
    with mock.patch.object(sv, "_shared", None), mock.patch.object(live_host.st, "get_option", lambda name: 8511):
        connected_page = live_host.supervisor_for(run_store.load(ROOT / "runs" / "connected_run"))
        connected_ok = connected_page.connected == "baseline" and connected_page.port == 8515
    with mock.patch.object(sv, "_shared", None), mock.patch.object(live_host.st, "get_option", lambda name: 8510):
        platform_page = live_host.supervisor_for(run_store.load(PLATFORM))
    cl.record(all(ports_ok) and connected_ok and platform_page.connected is None,
              "Each app picks its own live port (the 8510 app 8514, the 8511 app 8515) and only an app opened on a connected run asks for the connected scenario (read from the record's run id); a platform run asks for none", f"ports {ports_ok}; connected app: {connected_page.connected} on {connected_page.port}; platform app: {platform_page.connected}")

    # ---------------------------------------------------------------- real Chrome, the ACTUAL unified app and the ACTUAL Streamlit frame
    if not CHROME.exists():
        cl.skip("The live page inside the actual unified app in real Chrome", "Google Chrome was not found here; the by-eye check is to open the Live run page, press Start the live view and then Start the run")
        return
    from checks.launchers_check import kill_tree, listening_on
    chrome_end_to_end(cl, "the ACTUAL unified app", PLATFORM, PORTS["chrome_app"], PORTS["chrome_live"], None, 90)
    chrome_end_to_end(cl, "the ACTUAL unified app on the connected run (the 8511 app)", ROOT / "runs" / "connected_run", PORTS["chrome_app2"], PORTS["chrome_live2"], "baseline", 300)


def chrome_end_to_end(cl, what: str, record_dir: Path, app_port: int, live_port: int, connected: str | None, wait: int) -> None:
    """A real browser left open on the Live run page of the real app (real time, no fast-forward) until the live view loads in the Streamlit frame, presses its own Start button and the run starts."""
    from checks.launchers_check import kill_tree, listening_on
    wrapper = ROOT / f"zz_live_app_for_check_{app_port}.py"             # next to unified_app.py (the menu's page files are found relative to it); removed again below
    wrapper.write_text(
        f"import sys\nsys.path.insert(0, r'{ROOT}')\nfrom cellpoc.live_supervisor import supervisor as sv\n\n\n"
        "class CheckSupervisor(sv.Supervisor):\n    def status(self, force=False):\n        s = super().status(force)\n        if s.address:\n            s.address += '?autostart=1'      # the check only: lets the page press its own Start button\n        return s\n\n\n"
        f"if sv._shared is None:\n    sv._shared = CheckSupervisor({live_port}, command_for=lambda p: sv.live_command(p, {connected!r}) + ['--tests-autostart'], connected={connected!r})\n    sv._shared.start()\nfrom cellpoc.shell.app import main\nmain(developer=True)\n", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(wrapper), "--server.port", str(app_port), "--server.address", "localhost", "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                              cwd=ROOT, env=dict(os.environ, CELLPOC_RECORD=str(record_dir)), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status, choice, waited = None, None, 0
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(f"http://localhost:{app_port}/_stcore/health", timeout=2).read().strip() == b"ok":
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        profile = tempfile.mkdtemp(prefix="app_live_chrome_")
        browser = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}", "--window-size=1500,2400", f"http://localhost:{app_port}/live_run"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for waited in range(1, wait + 1):
                time.sleep(1)
                try:
                    state = json.loads(http_get(live_port, "/state"))
                    status, choice = state["status"], state.get("setup_id")
                except Exception:  # noqa: BLE001
                    status = None
                if status == "running":
                    break
        finally:
            kill_tree(browser)
        cl.record(status == "running" and (connected is None or choice == f"connected:{connected}"),
                  f"In real Chrome, on {what} and the ACTUAL Streamlit frame (Streamlit's own sandbox), the live view the app started loads inside the Live run page, its page presses its own Start button and the run STARTS (the page's token and real origin accepted)" + (f", and it is the connected '{connected}' run" if connected else "") + ": the legitimate feature works end to end",
                  f"the run is '{status}' (choice {choice}) after {waited} second(s) of a real browser on the page")
    finally:
        kill_tree(server)
        wrapper.unlink(missing_ok=True)
        time.sleep(2)
    cl.record(not listening_on(app_port) and not listening_on(live_port), "...and when that app is stopped nothing it started is left listening", f"app {listening_on(app_port)}; live {listening_on(live_port)}")
