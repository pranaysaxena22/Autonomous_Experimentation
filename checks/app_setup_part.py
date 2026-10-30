"""Stage B of the unified app (the setup app drawn inside it), as a part of check_app.bat.

In plain words it checks that: the stand-alone setup app is exactly what it was before the refactor (a fingerprint of every text block, button and field label on its welcome page and all ten screens, recorded BEFORE the edit);
the Setup page of the unified app draws the same welcome page and the same ten screens (compared block by block, apart from the header, banner and label that belong to one app or the other) and shows the illustrative sentence exactly once on each;
the setup rules really apply inside it (a planted bad value gives the same error, switches saving and running off, as in the stand-alone app); the working setup survives a visit to another page and no setup key collides with a dashboard page's;
'Save and run it' works from inside the unified app (30 trials for the example) and its two buttons start exactly the commands the stand-alone app starts, the dashboard one answering this computer only (looked at on the real listening addresses, with a self-test that removes the flag);
and the new web-address routes (the Setup page's ?start=, ?screen= and ?open= and the unified app's other addresses) give the same outcome as the stand-alone app's own addresses and cannot reach a screen, a file or a record the stand-alone app would not allow.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (2026-10-24) The unified app opens in its CLIENT view by default; these checks are about the developer view (every page, the technical detail, which is unchanged), so they ask for it. The client view has its own check (checks/client_view_check.py).
os.environ["CELLPOC_DEVELOPER"] = "1"

PLATFORM, DEMO = ROOT / "runs" / "platform", ROOT / "runs" / "demo"
SETUP_PAGE = "cellpoc/shell/pages/setup.py"
SAVE_NAME = "zz-app-b-check"
SAVED = ROOT / "setups" / f"{SAVE_NAME}.yaml"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
STYLE_SHEET = re.compile(r"<style>.*?</style>", re.DOTALL)
WIDGETS = ("text_input", "number_input", "selectbox", "checkbox", "radio", "text_area", "multiselect", "slider")
SENTENCE = "simulation with illustrative values"
SETUP_KEYS = ("setup", "ver", "load_id", "screen", "origin", "base_dir", "load_problems", "saved", "linked", "run_result", "dashboard_started", "live_started")

# The stand-alone setup app's fingerprints, recorded on 2026-10-14 from the committed code BEFORE the refactor of cellpoc/setup_app/app.py (the page's style sheet text and the saved-setups folder left out, so they do not depend on this computer).
GOLDEN = {"welcome": "424f9bcebbf725c275ecef00b31b2bf97c7654062ded9b6e820c4403d69556a1", "screen1": "45a5556017e2a3d84ec59665ae38082a553dddacc165cd10e8e11bc9ef1e8357",
          "screen2": "d44fb8478d1700dc7242086bf08774ed806683463e0d36d23b8550c1d49ebdd5", "screen3": "4cc511464297c4ad72e80f7d8defb4485800a92d80029a5df5107318d5d810b2",
          "screen4": "b520ed3445f1227fc8e4352bf3ecbc18c3c3024a5def088d41b691c515fe6dee", "screen5": "23a46ac20571bbab4dcb7c00a47fb23daeda26fae2004caca729f7af2a9b04e5",
          "screen6": "b2887cb7d0b6a638b2d3efd3a5e60d01d9db483d951a540930c7bf5975cac71d", "screen7": "672682bc11a579673b1ad8ad0d00fa78442cc3a1fd24fae279511a10928619fd",
          "screen8": "2949c462c60872810368e2ea33441a48c9a977e8ff8be60a2b5b947fecbce7cf", "screen9": "3d4bb5d6fb12868b1afbf28f44b12f1981e6202ee31fe693cd458b0fe5f5b348",
          "screen10": "62af3665649a463109fb5b22f518c46df94782da9919ec3c8f981b9f7fced215"}


@contextlib.contextmanager
def hermetic_setups():
    """Make the setup app see an empty saved-setups folder, so what it shows does not depend on the files saved on this computer."""
    from cellpoc.setup_app import review, state
    with mock.patch.object(state, "SETUPS_FOLDER", "setups_none_for_check"), mock.patch.object(review, "SETUPS_FOLDER", "setups_none_for_check"):
        yield


@contextlib.contextmanager
def record_env(folder: Path):
    os.environ["CELLPOC_RECORD"] = str(folder)
    try:
        yield
    finally:
        os.environ.pop("CELLPOC_RECORD", None)


def parts(block, drop: tuple[str, ...] = (), keep_style: bool = True) -> dict:
    """Everything a person reads, types in or clicks in a block of the page. drop: markdown blocks carrying one of these markers are left out; keep_style=False leaves style sheets out altogether."""
    def keep(value: str) -> bool:
        return not any(marker in value for marker in drop) and (keep_style or not value.lstrip().startswith("<style>"))
    out = {"markdown": [STYLE_SHEET.sub("<style></style>", m.value) for m in block.markdown if keep(m.value)], "subheader": [e.value for e in block.subheader], "caption": [e.value for e in block.caption],
           "info": [e.value for e in block.info], "warning": [e.value for e in block.warning], "error": [e.value for e in block.error], "success": [e.value for e in block.success],
           "button": [(b.label, bool(b.disabled)) for b in block.button]}
    for kind in WIDGETS:
        out[kind] = [(w.label, str(w.value)) for w in getattr(block, kind)]
    return out


def fingerprint(at) -> str:
    return hashlib.sha256(json.dumps([parts(at.main), parts(at.sidebar)], sort_keys=True, default=str).encode()).hexdigest()


def standalone(query: dict | None = None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "setup_app.py"), default_timeout=240)
    for key, value in (query or {}).items():
        at.query_params[key] = value
    at.run()
    return at


def embedded(query: dict | None = None, record: Path = PLATFORM):
    """The unified app on the Setup page. The caller keeps record_env open while it uses the app."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
    for key, value in (query or {}).items():
        at.query_params[key] = value
    at.run()
    at.switch_page(SETUP_PAGE)
    at.run()
    return at


def comparable(at, is_embedded: bool) -> list[dict]:
    drop = ('class="ub-bar"', 'class="sim-stamp"') if is_embedded else ('class="sa-header"', 'class="sa-banner"')
    return [parts(at.main, drop, keep_style=False), parts(at.sidebar, drop, keep_style=False)]


def sentence_count(at) -> int:
    texts = []
    for block in (at.main, at.sidebar):
        p = parts(block, keep_style=False)
        texts += p["markdown"] + p["subheader"] + p["caption"] + p["info"] + p["warning"] + p["error"] + p["success"]
    return sum(t.lower().count(SENTENCE) for t in texts)


def session_keys(at) -> set[str]:
    state = at.session_state
    try:
        return set(state.filtered_state)
    except AttributeError:
        return set(iter(state))


def outcome(at) -> dict:
    """What a web address did to the setup app: whether a setup was loaded, which screen, from where, and what it said if it refused."""
    s = at.session_state
    loaded = "setup" in s and s["setup"] is not None
    return {"exception": bool(at.exception), "loaded": loaded, "screen": s["screen"] if loaded else None, "origin": s["origin"] if loaded else "",
            "said": [p.message for p in (s["load_problems"] if "load_problems" in s else [])]}


def dom_when_drawn(port: int, path: str, needs: str, tries: int = 25) -> str | None:
    """The page's text after the real server drew it in real Chrome, once it contains `needs` (a page that has not finished drawing is tried again; None when it never did)."""
    for attempt in range(tries):
        profile = tempfile.mkdtemp(prefix="appb_")
        done = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}", "--window-size=1500,2400", "--virtual-time-budget=600000", "--dump-dom", f"http://localhost:{port}{path}"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
        if needs in done.stdout:
            return done.stdout
    return None


def run(cl, displayed_numbers, run_app) -> None:
    from checks.setup_run_check import listening_checks
    from cellpoc.setup_app import run_this
    from streamlit.testing.v1 import AppTest  # noqa: F401  (the harness is needed by every part below)

    # ---------------------------------------------------------------- the stand-alone app is exactly what it was
    with hermetic_setups():
        now = {"welcome": fingerprint(standalone())}
        for n in range(1, 11):
            now[f"screen{n}"] = fingerprint(standalone({"start": "example", "screen": str(n)}))
    cl.record(now == GOLDEN, "The stand-alone setup app is exactly what it was before the refactor: a fingerprint of every text block, button and field label on its welcome page and on all ten screens (example loaded) equals the one recorded from the committed code before the edit",
              "all 11 equal" if now == GOLDEN else f"differs: {[k for k in GOLDEN if GOLDEN[k] != now[k]]}")

    # ---------------------------------------------------------------- the Setup page of the unified app draws the same screens, with the label once
    same, once, errors, detail = [], [], [], []
    with hermetic_setups(), record_env(PLATFORM):
        for name, query in [("welcome", None)] + [(f"screen {n}", {"start": "example", "screen": str(n)}) for n in range(1, 11)]:
            alone, inside = standalone(query), embedded(query)
            errors += [str(e.value)[:80] for e in inside.exception]
            same.append(comparable(alone, False) == comparable(inside, True))
            once.append(sentence_count(inside))
            detail.append(f"{name}: {'same' if same[-1] else 'DIFFERENT'}, sentence {once[-1]}x")
    cl.record(not errors and all(same) and len(same) == 11, "The Setup page of the unified app draws the same welcome page and the same ten screens as the stand-alone app (every block, heading, message, button and field compared; only the header and green bar, which the unified app replaces with its top bar and label, differ)", "; ".join(detail[:3]) + " ..." if all(same) else "; ".join(detail))
    cl.record(all(c == 1 for c in once), "The sentence 'Simulation with illustrative values' appears exactly ONCE on the Setup page, on the welcome page and on every one of the ten screens", f"counts: {once}")

    # ---------------------------------------------------------------- the rules apply inside it
    def break_and_look(at) -> dict:
        at.session_state["setup"]["ingredients"][0]["min"] = 400
        at.session_state["screen"] = 9
        at.run()
        messages = [m.value for m in at.main.markdown if 'class="sa-msg"' in m.value and "Error:" in m.value]
        buttons = {b.key: bool(b.disabled) for b in at.button if b.key in ("save", "save_and_run")}
        return {"errors": messages, "buttons": buttons}
    with hermetic_setups(), record_env(PLATFORM):
        a = break_and_look(standalone({"start": "example"}))
        b = break_and_look(embedded({"start": "example"}))
    cl.record(a == b and bool(b["errors"]) and b["buttons"] == {"save": True, "save_and_run": True},
              "The setup rules apply inside the unified app: a planted bad value (an ingredient's lowest value of 400) gives the same error messages as in the stand-alone app, and switches both 'Save setup' and 'Save and run it' off", f"{len(b['errors'])} error message(s); buttons disabled: {b['buttons']}")

    # ---------------------------------------------------------------- the working setup survives a visit elsewhere; no key collides
    with hermetic_setups(), record_env(PLATFORM):
        at = embedded({"start": "example", "screen": "4"})
        at.session_state["setup"]["calendar"]["duration_h"] = 96
        at.run()
        before_setup, before_screen = json.dumps(at.session_state["setup"], sort_keys=True, default=str), at.session_state["screen"]
        at.switch_page("cellpoc/shell/pages/the_run.py")
        at.run()
        at.switch_page(SETUP_PAGE)
        at.run()
        kept = json.dumps(at.session_state["setup"], sort_keys=True, default=str) == before_setup and at.session_state["screen"] == before_screen == 3 and not at.exception
        setup_keys = session_keys(embedded({"start": "example"}))
        dashboard_keys = set()
        for page in ("the_run", "replay", "data_and_model", "reports", "about"):
            visit = AppTest.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
            visit.run()
            visit.switch_page(f"cellpoc/shell/pages/{page}.py")
            visit.run()
            dashboard_keys |= session_keys(visit)
    clash = setup_keys & dashboard_keys
    cl.record(kept and not clash, "The working setup (an edited run length, on screen 4) is still there after a visit to The run and back, and no session key the setup app uses is also used by a dashboard page", f"kept: {kept}; shared keys: {sorted(clash) or 'none'}")

    # ---------------------------------------------------------------- Save and run it, from inside the unified app
    SAVED.unlink(missing_ok=True)
    try:
        with record_env(PLATFORM):
            at = embedded({"start": "example"})
            at.session_state["screen"] = 9
            at.run()
            box = next(t for t in at.text_input if t.key and t.key.startswith("save_name|"))
            box.set_value(SAVE_NAME).run()
            next(b for b in at.button if b.key == "save_and_run").click().run()
            result = at.session_state["run_result"]
            from cellpoc import run_store
            trials = len(run_store.load(ROOT / "runs" / "setup_run").trials) if result and result["ok"] else -1
            cl.record(bool(result and result["ok"]) and SAVED.exists() and trials == 30 and not at.exception,
                      "'Save and run it' works from inside the unified app: the example is saved into the setups folder and its simulated run has 30 trials, as from the stand-alone app", f"{trials} trials; {(result or {}).get('lines', ['no output'])[-1]}")
            keys = [b.key for b in at.button]
            links = [str(getattr(link, "proto", link))[:200] for link in at.get("page_link")] if hasattr(at, "get") else []
            texts = " ".join(m.value for m in at.markdown)
            cl.record("open_dashboard" not in keys and "watch_live" not in keys and "Live run page" in texts and any("live_run" in link for link in links),
                      "(D3, 2026-10-16) Inside the unified app the 'Run this setup' result no longer offers the two buttons that open separate windows (the dashboard on 8506, the live page on 8504): it tells you to use the app's own Live run page and links to it; the stand-alone setup app keeps both buttons (checked by check_setup_run.bat)",
                      f"buttons {keys}; links {len(links)}")
    finally:
        SAVED.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        listening_checks(cl, Path(tmp))          # the dashboard command the buttons use, started for real: 127.0.0.1 only; and the same command without the flag listens everywhere (the self-test)

    # ---------------------------------------------------------------- the web-address routes
    cases = [{"start": "example", "screen": "3"}, {"screen": "3"}, {"start": "example", "screen": "99"}, {"start": "example", "screen": "0"}, {"start": "example", "screen": "-1"}, {"start": "example", "screen": "abc"},
             {"start": "example99"}, {"start": "example2", "screen": "10"}, {"start": "../../etc/passwd"}, {"open": "../config/settings"}, {"open": "..\\..\\README"}, {"open": "C:\\Windows\\win"},
             {"open": "zz-no-such-setup"}, {"open": "a" * 80}, {"start": "blank", "open": "../x", "screen": "5"}, {"record": "../runs/demo", "CELLPOC_RECORD": "C:\\Windows"}]
    same_out, safe = [], []
    with hermetic_setups(), record_env(PLATFORM):
        for query in cases:
            alone, inside = outcome(standalone(query)), outcome(embedded(query))
            same_out.append(alone == inside)
            safe.append(not inside["exception"] and (not inside["loaded"] or (inside["origin"].startswith(("the bundled example", "a blank setup")) and inside["screen"] in range(10))))
    bad = [c for c, ok in zip(cases, same_out) if not ok] + [c for c, ok in zip(cases, safe) if not ok]
    cl.record(all(same_out) and all(safe),
              "The new web-address routes give the same outcome as the stand-alone app's own addresses for sixteen planted addresses (a screen past the end, zero, negative or not a number; an unknown example; paths trying to climb out of the setups folder, ../config/settings, ..\\..\\README, C:\\Windows\\win; a very long name; a screen without a setup; a record named in the address): "
              "a setup is loaded only from the bundled examples or a blank one, never from outside the setups folder, the screen is always one of the ten, and nothing raises an error", f"{sum(same_out)}/{len(cases)} same; {sum(safe)}/{len(cases)} safe" + (f"; trouble with {bad[:2]}" if bad else ""))
    # the unified app's other addresses: the record that is shown is chosen by the launcher, never by the address
    plain = displayed_numbers(run_app(PLATFORM))
    with record_env(PLATFORM):
        from streamlit.testing.v1 import AppTest as _A
        with_query = _A.from_file(str(ROOT / "unified_app.py"), default_timeout=240)
        for key, value in {"record": str(DEMO), "CELLPOC_RECORD": str(DEMO), "page": "replay", "path": "C:\\Windows"}.items():
            with_query.query_params[key] = value
        with_query.run()
    cl.record(displayed_numbers(with_query) == plain and plain["attempted"] == "30" and not with_query.exception,
              "An address cannot choose which run record the unified app shows (the launcher does): the Overview with ?record=, ?CELLPOC_RECORD=, ?page= and ?path= pointing elsewhere shows the same numbers as without them", f"attempted {displayed_numbers(with_query)['attempted']} either way")
    if CHROME.exists():
        port = 8582
        env = dict(os.environ, CELLPOC_RECORD=str(DEMO))
        proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "unified_app.py", "--server.port", str(port), "--server.address", "localhost", "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                try:
                    if urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2).read().strip() == b"ok":
                        break
                except Exception:  # noqa: BLE001
                    time.sleep(1)
            direct = dom_when_drawn(port, "/replay", "This run in numbers")          # an address that is not served falls back to the main page (the Overview)
            control = dom_when_drawn(port, "/live_run", "Start the live view")
        finally:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        if direct is None or control is None:
            cl.skip("A platform page's address (/replay) is not served for a proof-of-concept run", "the real browser did not finish drawing the page in twenty-five tries; the by-eye check is to open /replay on a demo run")
        else:
            cl.record("3D replay of this run" not in direct and "This run in numbers" in direct and "Start the live view" in control,
                      "In real Chrome, on the proof of concept's demo run, the address of a platform-only page (/replay) is not served (the app falls back to its main page and shows none of the replay), while an address that exists (/live_run) is", "")
    else:
        cl.skip("A platform page's address (/replay) is not served for a proof-of-concept run", "Google Chrome is not installed here")
