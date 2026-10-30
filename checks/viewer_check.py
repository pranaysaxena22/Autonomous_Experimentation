"""Health check for the 3D replay viewer (Stage 7): is it ONE self-contained file that replays exactly the executed timelines it was given, with no logic of its own, works with no internet, and shows a fault?

In plain words it checks that: the page is built from a real platform run (30 trials) and from the hand-authored example timeline; it is one file with the layout, every timeline, the 3D library (three.js r128, unchanged
from the recorded fingerprint, with its licence beside it) and the font inside, and nothing in it points to the web; the viewer's own code contains no random numbers, no network calls and nothing about models, engines or
labs; the embedded layout and timelines are exactly the ones given; every one of the ten action types has an animation; and then, in real headless Chrome: its self-test steps through the start, middle and end of EVERY
action of EVERY trial (1,447 actions in the platform run) without an error, with every action type seen and the counts equal to an independent count; it works with ALL network access blocked; the screenshot of a normal moment
is a real 3D picture with no fault banner, the screenshot of the jam shows the red fault banner and the readings and names the cause, and the screenshot of a recovery action shows the recovery badge; the address chooses the trial and
the moment; and with WebGL switched off it says so plainly and still lists and times the actions. A page that cannot be built (no timeline, the wrong layout) is refused in plain words. Nothing is written into the project and
nothing uses the network. If Chrome is not installed the browser parts are skipped, and the by-eye checklist in docs/platform_plan.md replaces them.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.planner import ACTION_TYPES  # noqa: E402
from cellpoc.platform_runner import run_platform  # noqa: E402
from cellpoc.viewer import ViewerError, build_viewer  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
VIEWER = ROOT / "cellpoc" / "viewer"
THREE_SHA256 = "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2"          # three.js r128, as downloaded once from cdnjs and recorded in docs/decisions.md
FORMATS = ROOT / "docs" / "platform_formats"
SIZE = "1400,980"


def chrome(url: str, args: list[str], profile: Path, timeout: int = 150) -> subprocess.CompletedProcess:
    return subprocess.run([str(CHROME), "--headless=new", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}", *args, url], capture_output=True, text=True, timeout=timeout)


def dump(page: Path, query: str, profile: Path, extra: list[str] = ()) -> str:
    return chrome(page.as_uri() + "?" + query, ["--disable-gpu", "--virtual-time-budget=20000", "--dump-dom", *extra], profile).stdout


def shot(page: Path, query: str, png: Path, profile: Path, extra: list[str] = ()) -> Image.Image | None:
    png.unlink(missing_ok=True)
    chrome(page.as_uri() + "?" + query, ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", f"--window-size={SIZE}", "--virtual-time-budget=15000", f"--screenshot={png}", *extra], profile)
    return Image.open(png).convert("RGB") if png.exists() else None


def selftest(dom: str) -> dict | None:
    m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', dom, re.S)
    return json.loads(html.unescape(m.group(1))) if m and m.group(1).strip() else None


def pixels(img: Image.Image):
    return getattr(img, "get_flattened_data", img.getdata)()


def count_pixels(img: Image.Image, box: tuple, test) -> int:
    px = pixels(img.crop(box))
    return sum(1 for p in px if test(*p))


def is_red(r, g, b):
    return r > 200 and g < 70 and b < 70


def is_amber(r, g, b):
    return r > 200 and 140 < g < 190 and b < 70


def colours(img: Image.Image, box: tuple) -> tuple[int, float]:
    crop = img.crop(box)
    distinct = len({(r // 16, g // 16, b // 16) for r, g, b in pixels(crop)})
    lum = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels(crop)]
    mean = sum(lum) / len(lum)
    return distinct, (sum((x - mean) ** 2 for x in lum) / len(lum)) ** 0.5


def embedded(page_text: str, ident: str):
    m = re.search(rf'<script type="application/json" id="{ident}">(.*?)</script>', page_text, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def main() -> int:
    cl = Checklist("PLATFORM STAGE 7 (3D replay viewer): one self-contained file that replays exactly the executed timelines it was given, with no logic of its own, offline")
    before = project_files()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = run_platform()
        page = build_viewer(run.layout, run.executed, tmp / "replay.html", "Robot cell: 3D replay")
        text = page.read_text(encoding="utf-8")
        layout_ex = json.loads((ROOT / "cellpoc" / "formats" / "examples" / "cell_layout_example.json").read_text(encoding="utf-8"))
        hand = json.loads((FORMATS / "executed_timeline_example.json").read_text(encoding="utf-8"))
        example = build_viewer(layout_ex, [hand], tmp / "example.html", "Hand-authored example")
        js = (VIEWER / "viewer.js").read_text(encoding="utf-8")
        tpl = (VIEWER / "template.html").read_text(encoding="utf-8")
        three = (VIEWER / "vendor" / "three.min.js").read_bytes()
        mine = js + tpl

        # ---------------------------------------------------------------- static
        outside = re.findall(r'(?:src|href)\s*=\s*["\']https?://|url\(\s*["\']?https?://|@import|<link[^>]+rel=["\']stylesheet', tpl + js)
        cl.record(page.exists() and len(page.read_bytes()) < 16_000_000 and text.count("<html") == 1 and "base64," in text and "THREE" in text and not outside and "https://fonts.googleapis" not in text and "cdnjs" not in mine,
                  "The page is ONE file with the layout, every timeline, the 3D library and the font inside (under 16 MB), and the viewer's own page and code point to nothing on the web (no web script, style sheet, font or import)",
                  f"{len(text) / 1e6:.2f} MB; outside references {outside[:2]}")
        cl.record(hashlib.sha256(three).hexdigest() == THREE_SHA256 and (VIEWER / "vendor" / "THREE-LICENSE.txt").exists() and "MIT" in (VIEWER / "vendor" / "THREE-LICENSE.txt").read_text(encoding="utf-8") and (ROOT / "static" / "OpenSans.ttf").exists(),
                  "The bundled 3D library is exactly three.js r128 as recorded (its fingerprint matches), its MIT licence is kept beside it, and the font is the one already bundled in static/", f"fingerprint {hashlib.sha256(three).hexdigest()[:12]}")
        forbidden = {"random numbers": r"Math\.random", "a network call": r"\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|\bimport\s*\(|importScripts", "storage": r"localStorage|sessionStorage|indexedDB|document\.cookie",
                     "decision, model or lab code": r"\b(propose|strategy|surrogate|gaussian|hidden|virtual_?lab|measure\(|Strategy)\b"}
        found = {k: re.findall(v, js) for k, v in forbidden.items()}
        cl.record(not any(found.values()), "The viewer's own code contains no random numbers, no network call, no browser storage, and nothing about decisions, models or the lab: it only replays what it is given", str({k: v[:2] for k, v in found.items() if v}) or "clean")
        lay, tls = embedded(text, "data-layout"), embedded(text, "data-timelines")
        cl.record(lay == run.layout and tls == run.executed and len(tls) == len(run.executed) == 30 and embedded(example.read_text(encoding="utf-8"), "data-timelines") == [hand],
                  "The layout and timelines inside the page are exactly the ones given (30 trials of the platform run; and the hand-authored example timeline), so the viewer replays what the executor reported and nothing else", f"{len(tls)} timelines embedded")
        handlers = re.findall(r"^  (move|pick|place|pour|shake|press|stir|scan|read|wait)\(", js, re.M)
        cl.record(sorted(handlers) == sorted(ACTION_TYPES) and len(handlers) == 10, "Every one of the ten action types has an animation (and no other name has)", ", ".join(sorted(handlers)))

        def refuses(fn):
            try:
                fn()
            except ViewerError as error:
                return str(error)
            return None
        msgs = [refuses(lambda: build_viewer(run.layout, [], tmp / "x.html")), refuses(lambda: build_viewer({**run.layout, "layout_id": "other_layout"}, run.executed, tmp / "y.html"))]
        cl.record(all(m and len(m) > 30 for m in msgs), "A page with no timeline, or timelines run on a different layout, is refused in plain words and nothing is written", "; ".join((m or "NOT REFUSED")[:60] for m in msgs))

        # ---------------------------------------------------------------- real Chrome
        if not CHROME.exists():
            for name in ("The self-test through every action", "It works with all network access blocked", "The pictures: normal, fault, recovery", "The address chooses the trial and the moment", "With WebGL switched off"):
                cl.skip(name, "Google Chrome is not installed here: use the by-eye checklist in docs/platform_plan.md")
        else:
            profile = tmp / "profile"
            st = selftest(dump(page, "selftest=1", profile))
            types = Counter(a["type"] for t in run.executed for a in t["actions"])
            ex_st = selftest(dump(example, "selftest=1", profile))
            cl.record(bool(st) and st["ok"] and st["timelines"] == 30 and st["actions"] == sum(types.values()) and st["types"] == dict(types) and set(st["types"]) == set(ACTION_TYPES) and st["webgl"] is True
                      and bool(ex_st) and ex_st["ok"] and ex_st["actions"] == len(hand["actions"]) == 54,
                      "In real headless Chrome the self-test steps through the start, middle and end of EVERY action of EVERY trial without an error, sees every action type, its counts equal an independent count, the robot has put everything down at the end of each trial, and the 3D view starts; and the hand-authored example's 54 actions pass too",
                      f"{st and st['actions']} actions, errors {st and st['errors'][:2]}, webgl {st and st['webgl']}; example {ex_st and ex_st['actions']}")
            blocked = ["--host-resolver-rules=MAP * ~NOTFOUND", "--disable-gpu"]
            off = selftest(dump(page, "selftest=1", tmp / "p2", blocked))
            img = shot(page, "trial=8&t=400&cam=balance", tmp / "offline.png", tmp / "p3", ["--host-resolver-rules=MAP * ~NOTFOUND"])
            d, sd = colours(img, (120, 300, 800, 650)) if img else (0, 0)
            cl.record(bool(off) and off["ok"] and off["actions"] == st["actions"] and img is not None and d > 40 and sd > 15,
                      "With ALL network access blocked (every outside address unreachable) the viewer still starts, steps through every action, and draws a real 3D picture (many colours, a lit scene), so it needs no internet", f"{off and off['actions']} actions; {d} colours, brightness spread {sd:.0f}")
            t8 = run.executed[7]
            failed = next(a for a in t8["actions"] if a["outcome"] == "failed")
            recovery = next(a for a in t8["actions"] if a["origin"] == "recovery")
            normal_t = 400
            normal = shot(page, f"trial=8&t={normal_t}&cam=balance", tmp / "normal.png", tmp / "p4")
            fault = shot(page, f"trial=8&action={failed['id']}&cam=balance", tmp / "fault.png", tmp / "p4")
            recov = shot(page, f"trial=8&action={recovery['id']}&cam=balance", tmp / "recov.png", tmp / "p4")
            banner, badge = (100, 226, 700, 262), (700, 226, 851, 262)
            ok = all(i is not None and i.size[0] >= 1300 for i in (normal, fault, recov))
            if ok:
                n_red, f_red = count_pixels(normal, banner, is_red), count_pixels(fault, banner, is_red)
                f_amb, r_amb, n_amb = count_pixels(fault, badge, is_amber), count_pixels(recov, badge, is_amber), count_pixels(normal, badge, is_amber)
                dn, sn = colours(normal, (120, 300, 800, 650))
                cl.record(n_red < 50 and f_red > 2000 and r_amb > 800 and n_amb < 50 and f_amb < 50 and dn > 40 and sn > 15,
                          "The pictures tell the story: a normal moment is a real 3D scene with NO fault banner; the moment of the binder jam shows the red fault banner; a recovery action shows the amber RECOVERY badge (and neither banner appears when it should not)",
                          f"red banner pixels: normal {n_red}, jam {f_red}; amber badge pixels: normal {n_amb}, jam {f_amb}, recovery {r_amb}")
                dom = dump(page, f"trial=8&action={failed['id']}", tmp / "p5")
                cl.record(failed["fault"]["cause"] in html.unescape(dom) and "FAULT:" in html.unescape(dom) and failed["fault"]["detail"][:20] in html.unescape(dom) and f"{failed['reading']['value']:.2f} g" in html.unescape(dom),
                          "At the moment of the jam the page names the cause and the detail from the timeline and shows the balance's own reading (the amount that really arrived), taken from the timeline and not worked out", f"cause '{failed['fault']['cause']}', reading {failed['reading']['value']} g")
            else:
                cl.record(False, "The pictures: normal, fault, recovery", "Chrome produced no screenshot")
            dom19 = dump(page, "trial=19&t=100", tmp / "p6")
            dom8 = dump(page, "trial=8&t=1000", tmp / "p6")
            cl.record('tchip skip cur' in dom19 and 'tchip pass rec cur' in dom8 and "0:" not in re.search(r'id="clockT">([^<]*)<', dom8).group(1)[:0] + "x" and re.search(r'id="clockT">([^<]*)<', dom8).group(1).startswith("16:40") and re.search(r'id="clockT">([^<]*)<', dom19).group(1).startswith("1:40"),
                      "The address chooses the trial and the moment: trial=19&t=100 selects the skipped trial at 1:40, trial=8&t=1000 selects the recovered trial at 16:40", "")
            nogl = dump(page, "trial=8&t=400", tmp / "p7", ["--disable-3d-apis", "--disable-gpu", "--disable-webgl"])
            self_off = selftest(dump(page, "selftest=1", tmp / "p8", ["--disable-3d-apis", "--disable-gpu", "--disable-webgl"]))
            nogl_visible = re.search(r'id="nogl"[^>]*style="[^"]*display:\s*flex', nogl) is not None
            cl.record(nogl_visible and "WebGL is unavailable" in nogl and bool(self_off) and self_off["ok"] and self_off["webgl"] is False and re.search(r"A001\s+pick", html.unescape(nogl)) is not None,
                      "With WebGL switched off the page says plainly that the 3D view could not start, and still lists the actions, their times and the readings (and the self-test still passes, with the 3D view reported as off)", f"message shown {nogl_visible}; self-test {self_off and self_off['ok']}")
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
