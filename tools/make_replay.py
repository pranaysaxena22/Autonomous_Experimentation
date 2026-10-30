"""Make the shareable replay: ONE html file that plays the guided demo by itself, with the narrator's voice, in any browser, with no program running and no internet.

It is the console page with a recorded simulated run inside instead of a live program behind it. Steps (build_replay.bat runs them in order):
  python -m tools.make_replay collect   records a whole simulated run, the camera checks and the pictures of the cell (about two minutes), and lists the sentences to be spoken
  (voice) .venv_voice\\Scripts\\python tools\\make_voice.py clips VOICE   records the sentences with an offline neural voice (optional: without it the page uses the computer's own voice)
  python -m tools.make_replay assemble  puts everything into runs/replay/Autonomous_Formulation_Cell_replay.html

Everything shown is illustrative: a simulation with made-up values, as in the live console.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "runs" / "replay"
DATA = OUT / "replay_data.json"
LINES = ROOT / "voice_models" / "narration_lines.json"
PAGE = OUT / "Autonomous_Formulation_Cell_replay.html"
DEMOS = ("", "wrong", "unreadable", "blank", "liquid")          # what Inject event can arm for a bottle
FRAME_TIMES = list(range(0, 1300, 20)) + list(range(1300, 6200, 100)) + list(range(6200, 6510, 10))      # trial 1, in simulated seconds: finer where the guided demo stops to explain (the bottle checks, the tablet), coarser while it runs fast


def small(jpeg: bytes, width: int = 800, quality: int = 50) -> str:
    """The picture re-drawn a little smaller, so the file stays easy to send."""
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image.shape[1] > width:
        image = cv2.resize(image, (width, round(image.shape[0] * width / image.shape[1])), interpolation=cv2.INTER_AREA)
    ok, packed = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(packed.tobytes()).decode("ascii")


def collect() -> None:
    import threading
    from cellpoc.live import narration
    from cellpoc.live.pace import Pacer
    from cellpoc.live.run import LiveRun
    from cellpoc.live.server import LiveServer
    from cellpoc.physics import prepare_drawing

    OUT.mkdir(parents=True, exist_ok=True)
    prepare_drawing()
    run = LiveRun(pacer=Pacer(300), save_to=None)
    server = LiveServer(0, make_run=lambda: run, save_to=None)
    print("recording a whole simulated run ...", flush=True)
    run.fast_forward(run.sim.duration * 60, 300)
    waited = threading.Event()
    for _ in range(6000):                                   # up to about two minutes for the last trials to be published
        if run.status == "finished":
            break
        waited.wait(0.02)
    if run.status != "finished":
        raise SystemExit(f"The recorded run did not finish (status: {run.status}).")
    final = server.state(0, 0)
    feed = run.feed
    first = feed.timelines[0]
    bottle_picks = [a["id"] for a in first["actions"] if a["type"] == "pick" and str(a.get("object", "")).startswith("bottle_")]
    tablet_pick = next(a["id"] for a in first["actions"] if a["type"] == "pick" and a.get("object") == "tablet" and a.get("from") == "press")
    vision: dict[str, dict] = {}
    print(f"camera checks of trial 1: {len(bottle_picks)} bottles x {len(DEMOS)} cases, and the tablet ...", flush=True)
    for action in bottle_picks:
        for demo in DEMOS:
            answer, problem = server.vision_check(1, action, demo)
            if answer is None:
                raise SystemExit(f"The camera check of {action} ({demo or 'normal'}) could not be made: {problem}")
            vision[f"1|{action}|{demo}"] = answer
    for demo in ("", "defective"):
        answer, problem = server.tablet_check(1, tablet_pick, demo)
        if answer is None:
            raise SystemExit(f"The tablet check ({demo or 'normal'}) could not be made: {problem}")
        vision[f"t|1|{tablet_pick}|{demo}"] = answer
    print(f"pictures of the cell: {len(FRAME_TIMES) + 1} ...", flush=True)
    rest, problem = server.picture(0, 0.0)
    if rest is None:
        raise SystemExit(f"The picture of the cell could not be drawn: {problem}")
    frames = {}
    for t in FRAME_TIMES:
        picture, problem = server.picture(1, float(t))
        if picture is None:
            raise SystemExit(f"The picture of trial 1 at {t} s could not be drawn: {problem}")
        frames[str(t)] = small(picture)
    data = {"label": final["label"], "duration_s": final["duration_s"], "clock_start": run.sim.clock.iso(0), "setup_id": final["setup_id"], "setups": final["setups"], "layout_id": final["layout_id"], "setup_label": final.get("setup_label"),
            "timelines": final["timelines"], "timeline_times": list(feed.timeline_times), "events": final["events"], "results": final["results"], "alerts": final["alerts"], "summary": final["summary"],
            "vision": vision, "rest": small(rest), "frames": frames, "layout": run.layout}
    DATA.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    spoken = narration.lines(final["summary"])
    LINES.parent.mkdir(parents=True, exist_ok=True)
    LINES.write_text(json.dumps([{"hash": narration.hash_text(t), "text": t} for t in spoken], indent=1), encoding="utf-8")
    print(f"recorded: {DATA} ({DATA.stat().st_size // 1024} KB); {len(spoken)} sentences to be spoken listed in {LINES}")
    server.httpd.server_close()                              # (the server was never started, only used for its answers: shutdown() would wait for ever)


def moments(data: dict) -> dict:
    """When each thing was published, in simulated seconds: the moment the simulation logged it (its own minute), not the pacer's clock, which a recording made at full speed has already wound to the end."""
    for key in ("events", "results", "alerts"):
        for item in data[key]:
            item["published_at_sim_s"] = item["minute"] * 60.0
    data["timeline_times"] = [t["trial_start_minute"] * 60.0 for t in data["timelines"]]
    return data


def assemble() -> None:
    from cellpoc.live import page
    if not DATA.exists():
        raise SystemExit("There is no recording yet: run 'python -m tools.make_replay collect' first (build_replay.bat does).")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    layout = data.pop("layout")
    moments(data)
    clips = page.narration_audio()
    shim = (page.HERE / "replay_shim.js").read_text(encoding="utf-8")
    script = "window.REPLAY_DATA=" + json.dumps(data, separators=(",", ":")) + ";\n" + shim
    html = page.build_console_page(layout, title="Autonomous Formulation Cell (recorded replay)", token="", autostart_hook=False, replay_script=script, audio=clips)
    PAGE.write_text(html, encoding="utf-8")
    covered = sum(1 for line in json.loads(LINES.read_text(encoding="utf-8")) if line["hash"] in clips) if LINES.exists() else 0
    total = len(json.loads(LINES.read_text(encoding="utf-8"))) if LINES.exists() else 0
    print(f"replay written: {PAGE} ({PAGE.stat().st_size / 1_000_000:.1f} MB); the narrator's recorded voice covers {covered} of {total} sentences" + ("" if covered == total else " (the rest use the computer's own voice)"))


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "collect":
        collect()
    elif command == "assemble":
        assemble()
    else:
        raise SystemExit(__doc__)
