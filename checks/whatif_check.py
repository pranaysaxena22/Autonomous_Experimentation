"""Health check for "try a recipe yourself": the person types their own recipe, the virtual lab measures it, and the decision engine says what it would do next.

In plain words it checks that: a recipe that is not five numbers, one for each ingredient and each within its allowed range, is refused with a plain sentence that names the ingredient and the range; a good recipe is measured and the
reading is exactly what the virtual lab gives for it; the same recipe tried twice reads a little differently (a real lab scatters), but the same first try gives the same answer every time; the engine is shown the six starting results and
the person's recipe as the next trial, and says what it would try as the one after, with its reason, inside the allowed ranges; the engine is given measurements only and the part that does this imports nothing that touches the lab's
hidden truth; on the real server the control needs the page's secret, a bad recipe gets a plain sentence and HTTP 400, a good one gets the answer, and trying a recipe does not start, move or change the run or the queue; the page has the
Try it view with one box for each ingredient and a button, in real Chrome; no developer wording is on the page; and nothing is written into the project.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.live.run import LiveRun  # noqa: E402
from cellpoc.live.server import LiveServer  # noqa: E402
from cellpoc.live.whatif import FIRST_TRY_ID, WhatIf, design_of  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from checks.approvals_check import get  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.console_check import developer_words  # noqa: E402
from checks.models_check import project_files  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
GOOD = {"drug": 11.0, "filler": 75.5, "binder": 2.7, "disintegrant": 8.0, "lubricant": 0.9}


def logic_checks(cl: Checklist) -> WhatIf:
    run = LiveRun(None, save_to=None)
    tool = WhatIf(run.settings)
    bad = {"not a dictionary": "x", "a missing ingredient": {"drug": 1}, "a word where a number goes": {**GOOD, "lubricant": "a"}, "a true/false": {**GOOD, "drug": True},
           "not a number (NaN)": {**GOOD, "drug": float("nan")}, "an extra ingredient": {**GOOD, "water": 1.0}, "too much drug": {**GOOD, "drug": 99}, "too little binder": {**GOOD, "binder": 0.1}}
    replies = {name: tool.try_recipe(v) for name, v in bad.items()}
    cl.record(all(isinstance(r, str) and len(r) > 15 for r in replies.values()) and "between 10 and 30%" in replies["too much drug"] and "Drug (active)" in replies["too much drug"] and "Binder" in replies["too little binder"],
              "A recipe that is not five numbers within the allowed ranges is refused with a plain sentence that names the ingredient and its range (eight kinds of bad input tried)", replies["too much drug"])
    first = WhatIf(run.settings).try_recipe(GOOD)
    again = WhatIf(run.settings).try_recipe(GOOD)
    expected = VirtualLab(run.settings).measure(FIRST_TRY_ID + 1, WhatIf(run.settings).check(GOOD)[0])
    cl.record(isinstance(first, dict) and first["measured"]["dissolution_pct"] == round(expected.dissolution_pct, 1) and first["measured"]["hardness_kp"] == round(expected.hardness_kp, 2) and first == again,
              "The reading is exactly what the virtual lab gives for the recipe, and the same first try gives the same answer every time", f"dissolution {first['measured']['dissolution_pct']}%, hardness {first['measured']['hardness_kp']} kP")
    second = tool.try_recipe(GOOD)
    third = tool.try_recipe(GOOD)
    cl.record(isinstance(second, dict) and isinstance(third, dict) and second["measured"] != third["measured"], "The same recipe tried twice reads a little differently, as in a real lab", f"{second['measured']['dissolution_pct']}% then {third['measured']['dissolution_pct']}%")
    design = design_of(run.settings)
    ranges = {i["key"]: (i["min"], i["max"]) for i in design["ingredients"]}
    nxt = first["next"]
    cl.record(first["trial"] == 7 and nxt["trial"] == 8 and [x["trial"] for x in first["starting"]] == [1, 2, 3, 4, 5, 6] and all(ranges[k][0] <= v <= ranges[k][1] for k, v in nxt["recipe"].items())
              and nxt["reason"].startswith("Chosen from 7 measured results") and "allowing for test-to-test scatter" in nxt["reason"],
              "The engine sees the six starting results and the person's recipe as trial 7, and says what it would try as trial 8, inside the allowed ranges, with its reason", nxt["reason"][:90])
    poor = tool.try_recipe({"drug": 25.0, "filler": 52.0, "binder": 6.0, "disintegrant": 1.0, "lubricant": 2.0})
    cl.record(isinstance(poor, dict) and not poor["measured"]["good"] and poor["measured"]["dissolution_pct"] < 85 and not poor["measured"]["dissolution_ok"],
              "A poor recipe is measured as not good, with the specification it missed", f"dissolution {poor['measured']['dissolution_pct']}%")
    return tool


def server_checks(cl: Checklist) -> None:
    server = LiveServer(port=0, save_to=None)
    server.start_in_thread()
    port = server.port

    def post(cmd: str, value=None, token: bool = True):
        headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
        if token:
            headers["X-Live-Token"] = server.token
        request = urllib.request.Request(f"http://127.0.0.1:{port}/control", data=json.dumps({"cmd": cmd, "value": value}).encode(), method="POST", headers=headers)
        try:
            reply = urllib.request.urlopen(request, timeout=60)
            return reply.status, json.loads(reply.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        before = get(port, "/state")
        design = before["design"]
        cl.record([i["key"] for i in design["ingredients"]] == ["drug", "filler", "binder", "disintegrant", "lubricant"] and all(i["min"] <= i["start"] <= i["max"] for i in design["ingredients"]) and "85" in design["targets"]["dissolution"],
                  "The page's state carries the form: five ingredients with their ranges and a starting value, and the targets in words", design["targets"]["hardness"])
        no_secret = post("try_recipe", GOOD, token=False)
        refused = post("try_recipe", {**GOOD, "drug": 99})
        answered = post("try_recipe", GOOD)
        after = get(port, "/state")
        cl.record(no_secret[0] == 403 and refused[0] == 400 and "between 10 and 30%" in refused[1]["error"] and answered[0] == 200 and answered[1]["whatif"]["measured"]["dissolution_pct"] > 0,
                  "On the real server a try needs the page's secret (HTTP 403 without it), a bad recipe gets HTTP 400 and a plain sentence, and a good one gets the lab's answer", refused[1]["error"])
        cl.record(after["status"] == before["status"] == "ready" and after["sim_s"] == before["sim_s"] == 0 and after["event_total"] == before["event_total"] and after["jobs"] == before["jobs"] and after["epoch"] == before["epoch"],
                  "Trying a recipe does not start, move or change the run or the queue", f"status {after['status']}, clock {after['sim_s']}")
        dom = chrome_dom(port)
        if dom is None:
            cl.skip("In real Chrome the Try it view has a box for each ingredient and a button", "Chrome is not installed here, or it did not produce the page")
        else:
            boxes = [k for k in ("drug", "filler", "binder", "disintegrant", "lubricant") if f'id="tryIn_{k}"' in dom]
            cl.record(len(boxes) == 5 and 'id="tryGo"' in dom and "Measure this recipe" in dom and 'data-tab="try"' in dom and "Good means" not in dom.split('id="view-try"')[0] and "A recipe is good when dissolution is at least 85%" in dom,
                      "In real Chrome the Try it view shows a box for each of the five ingredients (with its range), the targets in words and the button", f"{len(boxes)} boxes")
    finally:
        server.shutdown()


def chrome_dom(port: int) -> str | None:
    if not CHROME.exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        for budget in (9000, 20000):
            done = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}\\p{budget}", f"--virtual-time-budget={budget}", "--dump-dom",
                                   f"http://127.0.0.1:{port}/console?tab=try&welcome=off"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
            if 'id="view-try"' in done.stdout and 'id="tryIn_drug"' in done.stdout:
                return done.stdout
    return None


def import_checks(cl: Checklist) -> None:
    source = (ROOT / "cellpoc" / "live" / "whatif.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 2 and node.module:
            imported.add(node.module.split(".")[0])
    cl.record(imported <= {"contracts", "decision_engine", "virtual_lab"} and "_truth" not in source and "oracle" not in source,
              "The part that does this imports only the shared shapes, the engine and the lab's measuring call, and never the lab's hidden truth (its truth or scoring modules)", ", ".join(sorted(imported)))
    page = (ROOT / "cellpoc" / "live" / "console_part3.js").read_text(encoding="utf-8") + (ROOT / "cellpoc" / "live" / "console_template.html").read_text(encoding="utf-8")
    cl.record(not developer_words(page), "No developer wording is anywhere in the console's page or script, the Try it view included", ", ".join(developer_words(page)))


def main() -> int:
    cl = Checklist("TRY A RECIPE YOURSELF: the lab measures what you type and the engine says what it would do next")
    before = project_files()
    logic_checks(cl)
    server_checks(cl)
    import_checks(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    cl.headline("Type your own recipe and the lab measures it and the engine says what it would do next; bad input is refused in plain words; the run is untouched.")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
