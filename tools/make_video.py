"""Make the demo video: a short presentation (intro, the problem, what was built and who it helps, how it works), then the guided walkthrough, all with the narrator's voice.

Run it with the voice tool's environment (`.venv_voice`): build_video.bat does that. Needs the recorded replay (build_replay.bat) first.
  slides    draws the presentation slides (Chrome, headless)
  voice     records the narration of the slides and of the walkthrough with the offline voice
  capture   plays the replay full screen in Chrome and records the screen for the length of the walkthrough (about three minutes: leave the computer alone)
  assemble  puts the slides, the recording and the voice together into runs/video/Autonomous_Formulation_Cell_demo.mp4

Everything stays on this computer. Everything shown is illustrative: a simulation with made-up values.
"""
from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "runs" / "video"
SLIDES = OUT / "slides"
FRAMES = OUT / "frames"
REPLAY = ROOT / "runs" / "replay" / "Autonomous_Formulation_Cell_replay.html"
LINES = ROOT / "voice_models" / "narration_lines.json"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
FONT = ROOT / "static" / "OpenSans.ttf"
VOICE = "en_US-ryan-high"
SIZE = (1920, 1200)             # the screen of this computer: the slides and the recording share it, so nothing is stretched

# what is said while each slide is shown (the same story as the team-call script, docs/guides/team_call_demo_script.md)
DECK = [
    ("intro", "Hello, and welcome. This is the Autonomous Formulation Cell: a simulated lab station that makes, tests and learns from tablet recipes by itself. Everything you will see is a simulation with illustrative values."),
    ("problem", "Developing a tablet recipe is slow and manual. A team can run only about nine experiments a week by hand, and that is an assumption we would replace with the client's own figure. "
                "Nights and weekends are lost, so good recipes wait. Every bottle and every tablet is checked by eye, so a mix-up can slip through. And a fault at night stops the work until morning."),
    ("built", "So we built a robotic lab station that runs experiments around the clock. An arm weighs, mixes, presses and tests tablets. Cameras check every ingredient bottle and every pressed tablet. "
              "A decision engine chooses the next recipe from the results so far, and when something goes wrong the cell recovers by itself, or hands over to the morning team. "
              "For customers and the medical industry, that means more experiments per week, fewer invalid results, a faster route to a recipe that meets specification, and a record of every check."),
    ("how", "Here is how it works. The cell senses, reasons, acts and adapts, in a loop. Each trial dispenses the ingredients, mixes, presses a tablet, tests it, and cleans up, while the cameras check every bottle and every tablet. Now, let us watch it run."),
]

CSS = """
@font-face{font-family:'Open Sans';font-weight:300 800;src:url('%FONT%')}
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1200px;overflow:hidden}
body{font-family:'Open Sans',Arial,sans-serif;color:#fff;background:radial-gradient(1400px 700px at 90% -10%,rgba(134,188,37,.16),transparent 60%),linear-gradient(160deg,#141414,#282728 70%);position:relative}
.top{position:absolute;left:90px;top:54px;display:flex;align-items:center;gap:20px;font-size:30px;font-weight:700}
.mark{width:50px;height:50px;border-radius:50%;border:5px solid #86BC25;position:relative}.mark::after{content:"";position:absolute;inset:11px;border-radius:50%;background:#86EB22}
.foot{position:absolute;left:0;right:0;bottom:0;padding:16px 90px;background:#000;font-size:22px;color:#c8c8c8;display:flex;justify-content:space-between}.foot b{color:#86EB22;letter-spacing:.06em}
.rings{position:absolute;right:-220px;bottom:-260px;width:760px;height:760px;border-radius:50%;background:repeating-radial-gradient(circle,transparent 0 70px,rgba(134,188,37,.22) 70px 72px)}
main{position:absolute;left:90px;right:90px;top:170px;bottom:110px}
h1{margin:0 0 20px;font-size:98px;line-height:1.05;font-weight:700;letter-spacing:-.025em}
h2{margin:0 0 44px;font-size:84px;font-weight:700;letter-spacing:-.02em}
em{font-style:italic;color:#86EB22}
.eyebrow{font-size:28px;letter-spacing:.16em;text-transform:uppercase;color:#86EB22;font-weight:800;margin-bottom:20px}
.sub{font-size:44px;line-height:1.35;color:#e6e6e6;max-width:1300px}
.chips{display:flex;gap:18px;margin-top:50px}.chips span{border:2px solid #86BC25;border-radius:999px;padding:8px 28px;font-size:30px;font-weight:600}
.pt{display:flex;gap:30px;align-items:flex-start;margin-bottom:38px}
.pt i{flex:0 0 74px;height:74px;border-radius:50%;border:5px solid #86BC25;display:flex;align-items:center;justify-content:center;font-style:normal;font-weight:800;font-size:34px;background:#000}
.pt b{display:block;font-size:44px;line-height:1.2}.pt span{display:block;font-size:30px;color:#c8c8c8;margin-top:6px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:50px}
.card{background:rgba(255,255,255,.06);border:2px solid rgba(255,255,255,.16);border-top:8px solid #86BC25;border-radius:26px;padding:40px 46px}
.card h3{margin:0 0 26px;font-size:46px}.card li{font-size:36px;line-height:1.35;margin:0 0 20px;list-style:none;padding-left:46px;position:relative}
.card li::before{content:"";position:absolute;left:0;top:14px;width:20px;height:20px;border-radius:50%;background:#86BC25}
.loop{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:20px 0 70px}
.loop div{text-align:center;position:relative}.loop div::before{content:"";position:absolute;top:60px;left:-50%;width:100%;height:4px;background:linear-gradient(90deg,transparent,#86BC25)}.loop div:first-child::before{display:none}
.loop .c{font-style:normal;position:relative;z-index:1;width:120px;height:120px;border-radius:50%;border:5px solid #86BC25;background:#000;margin:0 auto 20px;display:flex;align-items:center;justify-content:center;font-size:44px;font-weight:800}
.loop b{display:block;font-size:40px;letter-spacing:.08em;text-transform:uppercase}.loop span{font-size:28px;color:#c8c8c8}
.steps{display:flex;align-items:center;gap:0;margin-top:20px}
.steps div{flex:1;text-align:center;padding:30px 10px;border:2px solid #86BC25;font-size:40px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;background:rgba(134,188,37,.12)}
.steps div:first-child{border-radius:999px 0 0 999px}.steps div:last-child{border-radius:0 999px 999px 0}
.note{margin-top:46px;font-size:36px;color:#e6e6e6}.note b{color:#86EB22}
"""

PAGES = {
    "intro": """<div class="top"><div class="mark"></div>Autonomous Formulation Cell</div><div class="rings"></div>
<main style="top:260px"><div class="eyebrow">Autonomous experimentation · tablet formulation</div><h1>Experiments that run <em>themselves</em>,<br>day and night</h1>
<div class="sub">A lab station that makes, tests and learns from tablet recipes by itself, and checks every bottle and every tablet with its own cameras.</div>
<div class="chips"><span>Robot arm</span><span>Computer vision</span><span>Decision engine</span></div></main>""",
    "problem": """<div class="top"><div class="mark"></div>Autonomous Formulation Cell</div>
<main><div class="eyebrow">Why this is hard by hand</div><h2>The <em>problem</em></h2>
<div class="pt"><i>1</i><div><b>About 9 experiments a week</b><span>What a team can run by hand. This is an assumption: replace it with your own figure.</span></div></div>
<div class="pt"><i>2</i><div><b>Nights and weekends are lost</b><span>People work set hours, so good recipes wait.</span></div></div>
<div class="pt"><i>3</i><div><b>Every bottle and tablet checked by eye</b><span>A wrong bottle or a damaged tablet can slip through and spoil a result.</span></div></div>
<div class="pt"><i>4</i><div><b>A fault at night stops everything</b><span>Until somebody arrives in the morning.</span></div></div></main>""",
    "built": """<div class="top"><div class="mark"></div>Autonomous Formulation Cell</div>
<main><div class="eyebrow">One loop, working through the night</div><h2>What we <em>built</em>, and who it helps</h2>
<div class="cols"><div class="card"><h3>A robotic lab station</h3><ul><li>An arm weighs, mixes, presses and tests tablets</li><li>Cameras check every bottle and every tablet</li><li>An engine chooses the next recipe from the results so far</li><li>It recovers from faults, or hands over to the morning team</li></ul></div>
<div class="card"><h3>For customers and the medical industry</h3><ul><li>More experiments per week</li><li>Fewer invalid results</li><li>A faster route to a recipe that meets specification</li><li>A record of every check</li></ul></div></div></main>""",
    "how": """<div class="top"><div class="mark"></div>Autonomous Formulation Cell</div>
<main><div class="eyebrow">How it works</div><h2>Sense, reason, act, <em>adapt</em></h2>
<div class="loop"><div><i class="c">1</i><b>Sense</b><span>Reads the instruments</span></div><div><i class="c">2</i><b>Reason</b><span>Chooses the next recipe</span></div><div><i class="c">3</i><b>Act</b><span>Makes and tests the tablets</span></div><div><i class="c">4</i><b>Adapt</b><span>Recovers from faults, then hands over</span></div></div>
<div class="steps"><div>Dispense</div><div>Mix</div><div>Press</div><div>Test</div><div>Clean</div></div>
<div class="note">Cameras check <b>every ingredient bottle</b> (barcode, printed name, liquid) and <b>every pressed tablet</b>.</div></main>""",
}


def page(name: str) -> str:
    body = PAGES[name]
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>" + CSS.replace("%FONT%", FONT.as_uri()) + "</style></head><body>" + body
            + "<div class='foot'><b>SIMULATION WITH ILLUSTRATIVE VALUES</b><span>every number is made up · not a result about real tablets</span></div></body></html>")


def chrome_shot(html_file: Path, png: Path) -> None:
    tmp = tempfile.mkdtemp(prefix="vs_")
    try:
        for budget in (6000, 9000, 12000):
            if png.exists():
                png.unlink()
            try:
                subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}\\p{budget}", "--hide-scrollbars", f"--window-size={SIZE[0]},{SIZE[1]}",
                                f"--virtual-time-budget={budget}", f"--screenshot={png}", html_file.as_uri()], capture_output=True, timeout=90)
            except subprocess.TimeoutExpired:
                continue
            if png.exists() and png.stat().st_size > 20000:
                return
        raise SystemExit(f"Chrome did not draw {html_file.name}.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def slides() -> None:
    SLIDES.mkdir(parents=True, exist_ok=True)
    for name, _ in DECK:
        html = SLIDES / f"{name}.html"
        html.write_text(page(name), encoding="utf-8")
        chrome_shot(html, SLIDES / f"{name}.png")
        print(f"slide drawn: {name}")


def voice() -> None:
    import make_voice
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "voice").mkdir(exist_ok=True)
    narrator = make_voice.load(VOICE)
    items = [(f"deck_{name}", text) for name, text in DECK] + [(f"walk_{i:02d}_{line['hash']}", line["text"]) for i, line in enumerate(json.loads(LINES.read_text(encoding='utf-8')))]
    lengths = {}
    for key, text in items:
        wav = make_voice.speak(narrator, text)
        (OUT / "voice" / f"{key}.wav").write_bytes(wav)
        with wave.open(str(OUT / "voice" / f"{key}.wav")) as w:
            lengths[key] = w.getnframes() / w.getframerate()
        print(f"  {key}: {lengths[key]:.1f} s")
    (OUT / "voice" / "lengths.json").write_text(json.dumps(lengths, indent=1), encoding="utf-8")
    print(f"slides {sum(v for k, v in lengths.items() if k.startswith('deck_')):.0f} s of speech; walkthrough {sum(v for k, v in lengths.items() if k.startswith('walk_')):.0f} s of speech")


def capture() -> None:
    """Plays the replay full screen and records the screen. The page names each sentence in its window title as it begins, which is how the voice is lined up with the picture."""
    import re
    from PIL import ImageGrab
    if not REPLAY.exists():
        raise SystemExit("There is no replay file yet: run build_replay.bat first.")
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    user32 = ctypes.windll.user32
    lines = json.loads(LINES.read_text(encoding="utf-8"))
    lengths = json.loads((OUT / "voice" / "lengths.json").read_text(encoding="utf-8"))
    last_hash = lines[-1]["hash"]
    last_len = lengths[f"walk_{len(lines) - 1:02d}_{last_hash}"]
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    profile = tempfile.mkdtemp(prefix="vc_")
    titles: list[str] = []
    enum_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(300)
            user32.GetWindowTextW(hwnd, buf, 300)
            if buf.value.startswith("say:"):
                titles.append(buf.value)
        return True

    callback = enum_type(collect)
    url = REPLAY.as_uri() + "?welcome=off&guided=1&theme=dark"
    user32.SetCursorPos(SIZE[0] - 1, SIZE[1] - 1)
    proc = subprocess.Popen([str(CHROME), "--kiosk", url, f"--user-data-dir={profile}", "--autoplay-policy=no-user-gesture-required", "--mute-audio", "--no-first-run", "--no-default-browser-check",
                             "--hide-scrollbars", "--disable-infobars", "--disable-session-crashed-bubble"])
    spoken: list[tuple[float, str]] = []          # (seconds on the recording's clock, sentence fingerprint)
    shots: list[float] = []
    started = time.time()
    last_title = ""
    ended_at = None
    try:
        while True:
            now = time.time() - started
            titles.clear()
            user32.EnumWindows(callback, 0)
            if titles and titles[0] != last_title:
                last_title = titles[0]
                found = re.match(r"say:([0-9a-f]{8})", last_title)
                if found:
                    spoken.append((now, found.group(1)))
                    print(f"  {now:6.1f} s  sentence {len(spoken)} of {len(lines)}", flush=True)
                    if found.group(1) == last_hash:
                        ended_at = now + last_len + 3.0
            image = ImageGrab.grab()
            image.convert("RGB").save(FRAMES / f"f{len(shots):05d}.jpg", quality=88)
            shots.append(now)
            if ended_at is not None and now > ended_at:
                break
            if proc.poll() is not None and ended_at is None:
                raise SystemExit('The browser window was closed before the walkthrough finished (was a key pressed?), so the recording was stopped. Run it again and leave the computer alone.')
            if now > 600:
                raise SystemExit("The walkthrough did not finish within ten minutes: the recording was stopped.")
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        shutil.rmtree(profile, ignore_errors=True)
    if len(spoken) < len(lines) - 1:
        raise SystemExit(f"Only {len(spoken)} of {len(lines)} sentences were heard being spoken: see runs/video/frames to see what Chrome showed.")
    (OUT / "capture.json").write_text(json.dumps({"shots": shots, "spoken": spoken}), encoding="utf-8")
    print(f"recorded {len(shots)} pictures over {shots[-1]:.0f} s ({len(shots) / shots[-1]:.1f} per second)")


def read_wav(path: Path):
    import numpy
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        data = numpy.frombuffer(w.readframes(w.getnframes()), dtype=numpy.int16).astype("float32") / 32768.0
    return data, rate


def assemble() -> None:
    import imageio_ffmpeg
    import numpy
    lengths = json.loads((OUT / "voice" / "lengths.json").read_text(encoding="utf-8"))
    cap = json.loads((OUT / "capture.json").read_text(encoding="utf-8"))
    lines = json.loads(LINES.read_text(encoding="utf-8"))
    lead, pad = 0.4, 0.7
    timeline: list[tuple[Path, float]] = []              # (picture, seconds shown)
    sounds: list[tuple[float, Path]] = []                # (start second, sound)
    clock = 0.0
    for name, _ in DECK:
        wav = OUT / "voice" / f"deck_{name}.wav"
        length = lengths[f"deck_{name}"]
        shown = lead + length + pad
        timeline.append((SLIDES / f"{name}.png", shown))
        sounds.append((clock + lead, wav))
        clock += shown
    first = cap["spoken"][0][0]
    begin = max(0.0, first - lead)                       # the walkthrough starts just before its first sentence
    end = cap["shots"][-1]
    shots = cap["shots"]
    # the stretches in which nobody is speaking (the simulation just running) are played faster, so the whole video fits in five minutes; the voice itself is never sped up
    speaking = [(t0, t0 + lengths[f"walk_{i:02d}_{h}"] + 0.4) for i, (t0, h) in enumerate(cap["spoken"])]
    quiet_speed = 2.2

    def speed_at(moment: float) -> float:
        return 1.0 if any(a <= moment <= b for a, b in speaking) else quiet_speed

    shown_at: list[float] = []                           # where each recorded picture falls on the video's own clock, from the start of the walkthrough
    elapsed = 0.0
    for i, moment in enumerate(shots):
        if moment < begin:
            shown_at.append(-1.0)
            continue
        nxt = shots[i + 1] if i + 1 < len(shots) else end + 0.2
        length = max(0.04, nxt - moment) / speed_at(moment)
        shown_at.append(elapsed)
        elapsed += length
        timeline.append((FRAMES / f"f{i:05d}.jpg", length))
    walk_start = clock
    for index, (moment, hash_) in enumerate(cap["spoken"]):
        later = [shown_at[i] for i, m in enumerate(shots) if m >= moment and shown_at[i] >= 0]
        sounds.append((walk_start + (later[0] if later else elapsed), OUT / "voice" / f"walk_{index:02d}_{hash_}.wav"))
    total = clock + elapsed + 0.2
    rate = 22050
    track = numpy.zeros(int((total + 1) * rate), dtype="float32")
    for start, wav in sounds:
        data, r = read_wav(wav)
        if r != rate:
            raise SystemExit("The voice recordings have different sample rates.")
        i0 = int(start * rate)
        track[i0:i0 + len(data)] += data[:max(0, len(track) - i0)]
    audio = OUT / "narration.wav"
    with wave.open(str(audio), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((numpy.clip(track, -1, 1) * 32767).astype("int16").tobytes())
    listing = OUT / "timeline.txt"
    with listing.open("w", encoding="utf-8") as f:
        for picture, seconds in timeline:
            f.write(f"file '{picture.as_posix()}'\nduration {seconds:.3f}\n")
        f.write(f"file '{timeline[-1][0].as_posix()}'\n")
    target = OUT / "Autonomous_Formulation_Cell_demo.mp4"
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio),
               "-vf", f"fps=25,scale={SIZE[0]}:{SIZE[1]},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", str(target)]
    subprocess.run(command, check=True)
    print(f"video written: {target} ({target.stat().st_size / 1_000_000:.1f} MB, {total // 60:.0f} min {total % 60:.0f} s)")


if __name__ == "__main__":
    steps = {"slides": slides, "voice": voice, "capture": capture, "assemble": assemble}
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    if command == "all":
        for step in steps.values():
            step()
    elif command in steps:
        steps[command]()
    else:
        raise SystemExit(__doc__)
