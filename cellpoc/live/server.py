"""The live page's small local web server. It listens ONLY on this computer (127.0.0.1), serves the live page, answers /state with what the simulation has published, and takes a few controls (start, pause,
speed, restart) by POST. Requests whose Host header is not this computer's own are refused (so a web page elsewhere cannot steer it). A control (POST) is also refused unless it comes from this server's own page: its Origin must be this
server's own address and it must carry the secret token the server wrote into that page (a web page on any other site can do neither), and every response says that only pages on this computer may put this page in a frame. It uses only Python's built-in
web server: nothing is fetched from the internet and nothing leaves this computer."""
from __future__ import annotations

import collections
import hmac
import base64
import json
import math
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..connected import ConnectedError
from ..platform_runner import PlatformRunError
from . import choices as setup_choices
from .page import build_console_page, build_live_page
from .run import LIVE_FOLDER, LiveRun

HOST = "127.0.0.1"
PORT = 8504
SPEEDS = (60, 120, 300, 600, 1800, 3600, 7200)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
FRAME_RULE = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:*"          # only pages on this computer may show the live page in a frame


class LiveServer:
    """Holds the current live run and the page; `serve_forever` blocks, `start_in_thread` is for tests."""

    def __init__(self, port: int = PORT, setup_path: Path | str | None = None, make_run=None, save_to=LIVE_FOLDER, connected: str | None = None, autostart_hook: bool = False):
        """`save_to` is where a finished run is saved (None: nowhere). `make_run`, for tests, builds the first run; any other setup is built from the choices the page offers.
        `autostart_hook` is for tests only: it lets the page start the run by itself when opened with ?autostart=1 (the page does the same thing its Start button does). A normal server leaves it off, so opening an address never starts a run."""
        self.token = secrets.token_urlsafe(32)                      # the secret this server writes into its own page; new on every start
        self.autostart_hook = bool(autostart_hook)
        self.recent = collections.deque(maxlen=50)                  # (the Origin a control came with, whether it was accepted): what tests read; no secret is kept
        self.save_to = save_to
        self.current_id = setup_choices.id_for(setup_path, connected)
        self._first = make_run
        self._start = lambda: LiveRun(setup_path, save_to=save_to, connected=connected)
        self.run = (make_run or self._start)()
        self._stage = None                                          # the MuJoCo picture of the cell (drawn on request; made the first time a picture is asked for)
        try:                                                        # the invisible window MuJoCo draws into has to be made here, on the main thread; if this computer cannot draw, the page keeps its own 3D scene
            from ..physics import prepare_drawing
            prepare_drawing()
        except Exception:  # noqa: BLE001 - not an error for the live run: only the MuJoCo picture is unavailable
            pass
        self._stage_layout_id = None
        self._stage_lock = threading.Lock()
        self._vision_cache: dict = {}                                # the cell's vision checks already made: (trial, action id) -> the answer
        self._vision_lock = threading.Lock()
        self._page_layout_id = None
        self.page = ""
        self.console = ""
        self._refresh_page()
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):          # the black window stays quiet
                pass

            def _local(self) -> bool:
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") else "[::1]"
                return host in LOCAL_HOSTS

            def _send(self, code: int, body: bytes, kind: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Security-Policy", FRAME_RULE)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Type", kind + ("; charset=utf-8" if kind.startswith("text") or kind == "application/json" else ""))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, data: dict) -> None:
                self._send(code, json.dumps(data, separators=(",", ":")).encode("utf-8"))

            def do_GET(self):
                if not self._local():
                    return self._json(403, {"error": "This page only answers to this computer."})
                url = urlparse(self.path)
                if url.path in ("/", "/index.html"):
                    outer._refresh_page()
                    return self._send(200, outer.page.encode("utf-8"), "text/html")
                if url.path == "/console":                         # the operations console: the same run, shown as three views with a welcome and a tour
                    outer._refresh_page()
                    return self._send(200, outer.console.encode("utf-8"), "text/html")
                if url.path == "/state":
                    q = parse_qs(url.query)
                    try:
                        tl, ev = max(0, int(q.get("tl", ["0"])[0])), max(0, int(q.get("ev", ["0"])[0]))
                    except ValueError:
                        return self._json(400, {"error": "The request for the state was not understood."})
                    return self._json(200, outer.state(tl, ev))
                if url.path == "/health":
                    return self._send(200, b"ok", "text/plain")
                if url.path == "/vision_check":                    # read-only: the cell's camera check of the ingredient bottle the arm picks up in this action (a drawn photograph, read by the vision part)
                    q = parse_qs(url.query)
                    try:
                        trial, action = int(q.get("trial", [""])[0]), q.get("action", [""])[0]
                    except ValueError:
                        return self._json(400, {"error": "The request for the check was not understood."})
                    demo = q.get("demo", [""])[0]                      # a demonstration case the presenter chose: only what the camera is shown changes, never the run
                    if trial < 1 or not re.fullmatch(r"[A-Z]\d{3}", action) or demo not in ("", "wrong", "unreadable", "blank", "liquid"):
                        return self._json(400, {"error": "The request for the check was not understood."})
                    answer, problem = outer.vision_check(trial, action, demo)
                    if answer is None:
                        return self._json(404 if problem == "none" else 503, {"error": "There is no bottle check for that action." if problem == "none" else problem})
                    return self._json(200, answer)
                if url.path == "/tablet_check":                    # read-only: the cell's camera check of the tablet the arm has just lifted out of the press (a real photograph standing in for the camera, read by the trained network)
                    q = parse_qs(url.query)
                    try:
                        trial, action = int(q.get("trial", [""])[0]), q.get("action", [""])[0]
                    except ValueError:
                        return self._json(400, {"error": "The request for the check was not understood."})
                    demo = q.get("demo", [""])[0]
                    if trial < 1 or not re.fullmatch(r"[A-Z]\d{3}", action) or demo not in ("", "defective"):
                        return self._json(400, {"error": "The request for the check was not understood."})
                    answer, problem = outer.tablet_check(trial, action, demo)
                    if answer is None:
                        return self._json(404 if problem == "none" else 503, {"error": "There is no tablet check for that action." if problem == "none" else problem})
                    return self._json(200, answer)
                if url.path == "/mujoco.jpg":                      # read-only: a picture of the cell as the published timeline has it this many seconds into a trial; it starts, stops and changes nothing
                    q = parse_qs(url.query)
                    try:
                        trial, seconds = int(q.get("trial", [""])[0]), float(q.get("t", [""])[0])
                    except ValueError:
                        return self._json(400, {"error": "The request for the picture was not understood."})
                    if trial < 0 or not math.isfinite(seconds) or seconds < 0 or seconds > 10_000_000:
                        return self._json(400, {"error": "The request for the picture was not understood."})
                    picture, problem = outer.picture(trial, seconds)             # trial 0 is the cell at rest, before any trial has started
                    if picture is None:
                        return self._json(404 if problem == "none" else 503, {"error": "That trial has not been published yet." if problem == "none" else problem})
                    return self._send(200, picture, "image/jpeg")
                self._json(404, {"error": "There is nothing at this address."})

            def do_POST(self):
                if not self._local():
                    return self._json(403, {"error": "This page only answers to this computer."})
                if urlparse(self.path).path != "/control":
                    return self._json(404, {"error": "There is nothing at this address."})
                origin = self.headers.get("Origin")
                allowed = outer.request_allowed(origin, self.headers.get("X-Live-Token"))
                outer.recent.append((origin, allowed))
                if not allowed:                                    # nothing is run: not a page of this server (another site, another local page, a program with no token)
                    return self._json(403, {"error": "This control did not come from the live page itself, so it was refused."})
                try:
                    length = min(int(self.headers.get("Content-Length") or 0), 2000)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    cmd, value = body.get("cmd"), body.get("value")
                except (ValueError, TypeError, AttributeError):
                    return self._json(400, {"error": "The control was not understood."})
                reply = outer.control(cmd, value)
                if reply is not None:
                    return self._json(400, {"error": reply})
                state = outer.state(0, 0)
                if cmd not in ("restart", "setup"):                  # an answer to a control only brings the status; what is new in the feed comes with the page's own regular request
                    for key in ("timelines", "timeline_total", "events", "event_total"):
                        state.pop(key, None)
                self._json(200, state)

        self.httpd = ThreadingHTTPServer((HOST, port), Handler)
        self.port = self.httpd.server_address[1]
        self.allowed_origins = {f"http://{host}:{self.port}" for host in ("127.0.0.1", "localhost")}

    def request_allowed(self, origin: str | None, token: str | None) -> bool:
        """A control is accepted only from this server's own page: its Origin is this server's own address (the browser writes it and a web page cannot change it) AND it carries this server's secret token (compared in constant time)."""
        return origin in self.allowed_origins and hmac.compare_digest((token or "").encode("utf-8"), self.token.encode("utf-8"))

    def vision_check(self, trial: int, action_id: str, demo: str = ""):
        """(the check's answer, None) for an action in which the arm picks up an ingredient bottle; (None, "none") for any other action or an unpublished trial; (None, a plain sentence) if the vision part is unavailable."""
        with self.run.feed.lock:
            timeline = next((t for t in self.run.feed.timelines if t["trial"] == trial), None)
        if timeline is None:
            return None, "none"
        action = next((a for a in timeline["actions"] if a["id"] == action_id), None)
        bottle = next((o for o in self.run.layout["objects"] if action and o["id"] == action.get("object") and o["type"] == "bottle"), None)
        if action is None or action["type"] != "pick" or bottle is None:
            return None, "none"
        key = (trial, action_id, demo)
        with self._vision_lock:
            if key in self._vision_cache:
                return self._vision_cache[key], None
        try:
            from ..vision.bottle_check import check, demo_settings
        except ImportError:
            return None, "The vision check is not available on this computer."
        try:
            found = check(bottle["ingredient_id"], trial, bottle["ingredient_id"].replace("_pct", ""), engine="auto", **demo_settings(bottle["ingredient_id"], demo))
        except Exception:  # noqa: BLE001 - the page just shows no check; never a technical trace
            return None, "The vision check could not be made."
        answer = {"bottle": found.ingredient, "expected": found.expected_colour, "read": found.read_colour, "level": None if found.level_pct is None else round(found.level_pct), "engine": found.engine,
                  "source": found.source, "verdict": found.verdict, "detail": found.detail,
                  "label_expected": found.label_expected, "label_read": found.label_read, "label_name": (found.label_name or "").removesuffix("_pct") or None, "name": found.ingredient,
                  "name_expected": found.name_expected, "name_read": found.name_read, "name_reader": found.name_reader, "overall": found.overall, "label_detail": found.label_detail, "image": "data:image/jpeg;base64," + base64.b64encode(found.jpeg).decode("ascii"), "action": action_id, "trial": trial, "demo": demo}
        with self._vision_lock:
            self._vision_cache[key] = answer
        return answer, None

    def tablet_check(self, trial: int, action_id: str, demo: str = ""):
        """(the check's answer, None) for the action in which the arm lifts the tablet out of the press; (None, "none") for any other action or an unpublished trial; (None, a plain sentence) if the tablet check is unavailable."""
        with self.run.feed.lock:
            timeline = next((t for t in self.run.feed.timelines if t["trial"] == trial), None)
        if timeline is None:
            return None, "none"
        action = next((a for a in timeline["actions"] if a["id"] == action_id), None)
        if action is None or action["type"] != "pick" or action.get("object") != "tablet" or action.get("from") != "press":
            return None, "none"
        key = ("tablet", trial, action_id, demo)
        with self._vision_lock:
            if key in self._vision_cache:
                return self._vision_cache[key], None
        try:
            from ..vision.tablet import check
        except ImportError:
            return None, "The tablet check is not available on this computer."
        try:
            found = check(trial, demo)
        except Exception:  # noqa: BLE001 - the page just shows no check; never a technical trace
            return None, "The tablet check could not be made."
        if found is None:
            return None, "The tablet check is not set up on this computer (the trained network or the demonstration photographs are missing)."
        answer = {"label": found.label, "probability": round(100 * found.defect_probability), "verdict": found.verdict, "action_taken": found.action, "photo": found.photo, "source": found.source,
                  "image": "data:image/jpeg;base64," + base64.b64encode(found.jpeg).decode("ascii"), "action": action_id, "trial": trial, "demo": demo}
        with self._vision_lock:
            self._vision_cache[key] = answer
        return answer, None

    def picture(self, trial: int, seconds: float):
        """(JPEG bytes, None) for a published trial; (None, "none") if that trial has not been published; (None, a plain sentence) if the MuJoCo picture cannot be made (MuJoCo missing, or a plan the arm cannot play)."""
        with self.run.feed.lock:
            timeline = next((t for t in self.run.feed.timelines if t["trial"] == trial), None)
        if timeline is None and trial != 0:
            return None, "none"
        try:
            from ..physics import Stage
            from ..physics.motion import MotionError
        except ImportError:
            return None, "The MuJoCo picture is not available on this computer, so the page keeps its own 3D scene."
        layout_id = self.run.layout.get("layout_id")
        with self._stage_lock:
            if self._stage is None or self._stage_layout_id != layout_id:
                if self._stage is not None:
                    self._stage.close()
                self._stage, self._stage_layout_id = Stage(self.run.layout), layout_id
            stage = self._stage
        try:
            return (stage.rest_jpeg() if trial == 0 else stage.jpeg(timeline, seconds)), None
        except MotionError as exc:
            return None, str(exc)
        except Exception:  # noqa: BLE001 - the page keeps its own 3D scene; never a technical trace
            return None, "The MuJoCo picture could not be drawn, so the page keeps its own 3D scene."

    def _refresh_page(self) -> None:
        """The page embeds the equipment layout of the current setup; it is built again when a different setup brings a different layout."""
        layout_id = self.run.layout.get("layout_id")
        if layout_id != self._page_layout_id:
            self.page = build_live_page(self.run.layout, token=self.token, autostart_hook=self.autostart_hook)
            self.console = build_console_page(self.run.layout, token=self.token, autostart_hook=self.autostart_hook)
            self._page_layout_id = layout_id

    def state(self, timelines_seen: int = 0, events_seen: int = 0) -> dict:
        """The run's state plus which setup it is and which ones can be chosen (the names only: the server turns a name into a file from its own list)."""
        out = self.run.state(timelines_seen, events_seen)
        listed = setup_choices.choices()
        out.update({"setup_id": self.current_id, "setups": [{"id": c.id, "label": c.label} for c in listed], "layout_id": self.run.layout.get("layout_id")})
        current = next((c for c in listed if c.id == self.current_id), None)
        out["setup_label"] = current.label if current else self.current_id
        return out

    def _build(self, choice: "setup_choices.Choice") -> LiveRun:
        speed = self.run.pacer.speed
        if choice.kind == "connected":
            return LiveRun(speed=speed, save_to=self.save_to, connected=choice.scenario)
        return LiveRun(choice.path, speed=speed, save_to=self.save_to)

    def control(self, cmd, value) -> str | None:
        """Do a control; returns a plain sentence when it cannot be done, else None."""
        with self.lock:
            if cmd == "start":
                self.run.start()
            elif cmd == "pause":
                self.run.pause()
            elif cmd == "speed":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) not in SPEEDS:
                    return "That speed is not one of the choices on the page."
                self.run.set_speed(float(value))
            elif cmd == "restart":
                self.run.stop()
                speed = self.run.pacer.speed
                known = setup_choices.find(self.current_id)
                self.run = self._first() if (self._first and known is None) else (self._build(known) if known else self._start())
                self.run.set_speed(speed)
            elif cmd == "setup":
                choice = setup_choices.find(value)
                if choice is None:
                    return "That setup is not one of the choices on the page."
                try:
                    fresh = self._build(choice)                    # built first, so that a setup that cannot be simulated leaves the current run as it was
                except (PlatformRunError, ConnectedError) as exc:
                    return f"That setup cannot be simulated: {exc}"
                except Exception:  # noqa: BLE001 - the page shows a plain sentence, never a technical trace
                    return "That setup could not be started. Open it in the setup app to see what needs changing."
                self.run.stop()
                self.run, self.current_id = fresh, choice.id
            else:
                return "That control is not one this page has."
        return None

    def serve_forever(self) -> None:
        try:
            self.httpd.serve_forever()
        finally:
            self.run.stop()
            if self._stage is not None:
                self._stage.close()
            self.httpd.server_close()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.httpd.serve_forever, name="live-server", daemon=True)
        thread.start()
        return thread

    def shutdown(self) -> None:
        self.run.stop()
        if self._stage is not None:
            self._stage.close()
        self.httpd.shutdown()
        self.httpd.server_close()
