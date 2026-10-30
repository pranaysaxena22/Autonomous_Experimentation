"""Health check for high-risk findings: a wrong vial that a person must accept or reject.

In plain words it checks that: a fault can say it is high risk, and the setup's rules accept that only for a wrong vial at the barcode scan; the example with such a fault (Example 4) is valid and the other examples have none;
with nobody to decide, the standing rule skips the batch and the cell moves on by itself; when a person accepts, the batch goes on with the flagged vial and its record says so; both ways the events are in time order, the
request and the decision are at the same simulated moment (the clock stands still while a person decides) and the trial's actions follow the executor's own rules; the old faults (the jams on trials 8 and 19) behave exactly as they did;
with a person at the live page the cell really stops at the finding, its clock does not move, start and speed are refused with a plain sentence, a choice that is neither accept nor reject is refused, and the run goes on
only when the answer arrives (reject: no result, the next batch starts; accept: a result, and the page is given the whole trial in place of the part it had); the decision is logged with the time; and in real Chrome the page shows the
card with both buttons, says the run is waiting for a decision, and after a reject shows the decision in the log. Nothing is written into the project.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.decision_engine import AdaptiveStrategy  # noqa: E402
from cellpoc.executor import PythonStandInExecutor  # noqa: E402
from cellpoc.executor.stand_in import WRONG_VIAL_WORDS  # noqa: E402
from cellpoc.live.run import LiveRun  # noqa: E402
from cellpoc.live.server import LiveServer  # noqa: E402
from cellpoc.planner.rules import timeline_problems  # noqa: E402
from cellpoc.platform_cell import PlatformSimulation  # noqa: E402
from cellpoc.platform_runner import load_inputs  # noqa: E402
from cellpoc.setup import has_errors, load_setup, validate  # noqa: E402
from cellpoc.setup.rules import WRONG_VIAL  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.console_check import developer_words  # noqa: E402
from checks.models_check import project_files  # noqa: E402

EXAMPLES = ROOT / "cellpoc" / "formats" / "examples"
EXAMPLE_4 = EXAMPLES / "setup_example_4_approval.yaml"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
FAULT_MINUTE = 2705.666666666667                                             # when the scanner finds the wrong vial on trial 12 in Example 4 (a fixed fact of that example)


def batch(name: str, rule: str):
    setup, layout, settings = load_inputs(EXAMPLES / name)
    engine = AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine, settings.run.random_seed)
    sim = PlatformSimulation(settings, setup, layout, VirtualLab(settings), engine, "approvals", PythonStandInExecutor())
    sim.approval_rule = rule
    return sim.run_platform(), setup, layout


def kinds(record, trial: int, wanted: tuple[str, ...]) -> list[str]:
    return [e.kind for e in record.events if e.trial == trial and e.kind in wanted]


def setup_checks(cl: Checklist) -> None:
    loaded = load_setup(EXAMPLE_4)
    problems = validate(loaded.setup, base_dir=loaded.base_dir)
    cl.record(loaded.setup is not None and not has_errors(problems), "Example 4 (a wrong vial on trial 12 that needs a person) passes the platform's own setup checker with no errors", f"{sum(p.level == 'warning' for p in problems)} warning(s)")
    risks = {name: [f.get("risk", "low") for f in load_setup(EXAMPLES / name).setup["faults"]["scripted"]] for name in ("setup_example.yaml", "setup_example_2_week_random_faults.yaml", "setup_example_3_demanding_targets.yaml", EXAMPLE_4.name)}
    cl.record(all(set(v) <= {"low"} for k, v in risks.items() if k != EXAMPLE_4.name) and sorted(risks[EXAMPLE_4.name]) == ["high", "low", "low"],
              "Examples 1 to 3 have no high-risk fault; Example 4 has the same two jams as Example 1 (low) and one high-risk fault", str({k[:20]: v for k, v in risks.items()}))
    wrong = copy.deepcopy(loaded.setup)
    wrong["faults"]["scripted"][0]["risk"] = "medium"
    found = [p for p in validate(wrong, base_dir=loaded.base_dir) if p.rule == "R74"]
    cl.record(len(found) == 1 and "low or high" in found[0].text and found[0].level == "error", "A risk that is neither low nor high is refused, in plain words", found[0].message if found else "no problem found")
    jam = copy.deepcopy(loaded.setup)
    jam["faults"]["scripted"][0]["risk"] = "high"
    found = [p for p in validate(jam, base_dir=loaded.base_dir) if p.rule == "R74"]
    cl.record(len(found) == 1 and "wrong vial" in found[0].text, "A jam cannot be marked high risk: only a wrong vial at the barcode scan can, because it is the only fault a person can accept", found[0].message if found else "no problem found")
    cl.record(WRONG_VIAL.pattern == WRONG_VIAL_WORDS.pattern and WRONG_VIAL.flags == WRONG_VIAL_WORDS.flags, "The setup's rule and the executor use exactly the same words to tell a wrong vial from an unreadable label", WRONG_VIAL.pattern)


def batch_checks(cl: Checklist) -> None:
    run, setup, layout = batch("setup_example_4_approval.yaml", "reject")
    rec = run.record
    t12 = next(t for t in rec.trials if t.trial == 12)
    seq = kinds(rec, 12, ("fault", "approval_requested", "batch_rejected", "deviation_accepted", "candidate_skipped", "alert_queued", "measurement"))
    cl.record(seq == ["fault", "approval_requested", "batch_rejected", "candidate_skipped"] and t12.status == "Skipped" and t12.dissolution_pct is None,
              "With nobody to decide, the standing rule skips the batch: the finding is raised, the batch is rejected and skipped, no result, and no alert is queued for staff (the decision is already made)", str(seq))
    request = next(e for e in rec.events if e.kind == "approval_requested" and e.trial == 12)
    decision = next(e for e in rec.events if e.kind == "batch_rejected" and e.trial == 12)
    cl.record(request.minute == decision.minute == FAULT_MINUTE and "the standing rule" in decision.message, "The request and the decision are at the same simulated moment, and the decision says who made it", decision.message[:90])
    nxt = next(t for t in rec.trials if t.trial == 13)
    cl.record(nxt.start_minute >= t12.end_minute and [e.minute for e in rec.events] == sorted(e.minute for e in rec.events),
              "The cell moves on by itself: trial 13 starts after trial 12 ends, and the event log is in time order", f"trial 13 starts at minute {nxt.start_minute:.0f}")
    cl.record([t.trial for t in rec.trials if t.status == "Skipped"] == [12, 19] and any(a.severity.startswith("Rejected") and a.trial == 12 for a in rec.alerts), "Trials 12 (rejected) and 19 (the old jam) are the two skipped; the rejection is in the record's alerts", "")
    kept, _, _ = batch("setup_example_4_approval.yaml", "accept")
    rec2 = kept.record
    t12b = next(t for t in rec2.trials if t.trial == 12)
    seq2 = kinds(rec2, 12, ("fault", "approval_requested", "batch_rejected", "deviation_accepted", "candidate_skipped", "measurement"))
    scan = next(a for a in kept.executed[11]["actions"] if a["type"] == "scan")
    cl.record(seq2 == ["fault", "approval_requested", "deviation_accepted", "measurement"] and t12b.status == "Completed" and t12b.dissolution_pct is not None,
              "When a person accepts, the batch goes on with the flagged vial and has a result", str(seq2))
    cl.record(scan["outcome"] == "ok" and "Accepted by a person" in scan["caption"] and timeline_problems(kept.executed[11], setup, layout) == []
              and any("accepted deviation" in n for n in t12b.notes) and any(a.severity == "Accepted deviation" for a in rec2.alerts),
              "The accepted trial's scan says it was accepted, its timeline obeys the executor's rules, and the record says accepted deviation in its notes and alerts", scan["caption"][:80])
    old, _, _ = batch("setup_example.yaml", "reject")
    o = old.record
    t8, t19 = kinds(o, 8, ("fault", "recovery", "candidate_skipped", "alert_queued")), kinds(o, 19, ("fault", "recovery", "candidate_skipped", "alert_queued"))
    cl.record(t8 == ["fault", "recovery"] and t19 == ["fault", "candidate_skipped", "alert_queued"] and not any(e.kind in ("approval_requested", "batch_rejected", "deviation_accepted") for e in o.events),
              "The old low-risk faults behave as they always did: trial 8 recovers by itself, trial 19 is skipped and queued for staff, and nothing asks a person", f"trial 8 {t8}; trial 19 {t19}")


def get(port: int, path: str) -> dict:
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30).read())


def post(server: LiveServer, cmd: str, value=None) -> tuple[int, dict]:
    request = urllib.request.Request(f"http://127.0.0.1:{server.port}/control", data=json.dumps({"cmd": cmd, "value": value}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.port}", "X-Live-Token": server.token})
    try:
        reply = urllib.request.urlopen(request, timeout=30)
        return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def wait_for(test, seconds: float, pause: float = 0.2):
    start = time.time()
    while time.time() - start < seconds:
        value = test()
        if value:
            return value
        time.sleep(pause)
    return None


def live_checks(cl: Checklist, choice: str) -> None:
    server = LiveServer(port=0, setup_path=EXAMPLE_4, save_to=None)
    server.start_in_thread()
    port = server.port
    try:
        post(server, "speed", 7200)
        post(server, "start")
        state = wait_for(lambda: (lambda s: s if s["approval"] else None)(get(port, "/state")), 150)
        if state is None:
            cl.record(False, "With a person at the page, the cell stops at the wrong vial and asks", "it never stopped")
            return
        ask = state["approval"]
        events = get(port, "/state")["events"]
        asked = next(e for e in events if e["kind"] == "approval_requested")
        before = state["sim_s"]
        time.sleep(1.5)
        after = get(port, "/state")["sim_s"]
        if choice == "reject":
            cl.record(ask["trial"] == 12 and len(ask["found"]) > 30 and "different vial" in ask["found"], "With a person at the page, the cell stops at the wrong vial on trial 12 and asks, saying in plain words what it found", ask["found"][:90])
            cl.record(after == before, "While it waits, the simulated clock does not move", f"{before:.0f} s, then {after:.0f} s")
            cl.record(asked["published_at_sim_s"] >= asked["minute"] * 60 - 1e-6 and asked.get("risk") == "high", "The request is published at its own simulated moment (not early), marked high risk", f"published at {asked['published_at_sim_s']:.0f} s for minute {asked['minute']:.0f}")
            refused = [post(server, "start"), post(server, "speed", 60), post(server, "decide", "maybe")]
            cl.record(all(code == 400 and len(reply["error"]) > 20 for code, reply in refused), "While it waits, start and speed are refused, and so is an answer that is neither accept nor reject, each with a plain sentence", refused[0][1]["error"])
        code, reply = post(server, "decide", choice)
        cl.record(code == 200 and reply["approval"] is None and reply["decisions"][-1]["decision"] in ("Accepted", "Rejected"),
                  f"The answer '{choice}' is taken at once: the reply already shows nothing is waiting", "")
        cl.record(post(server, "decide", choice)[0] == 400, "A second answer when nothing is waiting is refused", "")
        done = wait_for(lambda: (lambda s: s if s["status"] == "finished" else None)(get(port, "/state")), 240, 0.5)
        if done is None:
            cl.record(False, f"After '{choice}' the run goes on to its end", "it did not finish")
            return
        row = next(r for r in done["results"] if r["trial"] == 12)
        log = done["decisions"][-1]
        timeline = next(t for t in done["timelines"] if t["trial"] == 12)
        if choice == "reject":
            cl.record(row["verdict"] == "No result" and timeline["outcome"] == "skipped" and done["replaced_total"] == 1 and any(r["trial"] == 13 for r in done["results"]),
                      "After a reject the batch has no result, the page is given the whole trial in place of the part it had, and the next batch is run by itself", f"{len(done['results'])} results; trial 12 {row['verdict']}")
        else:
            cl.record(row["verdict"] in ("Good", "Not good") and timeline["outcome"] == "completed_after_recovery" and done["replaced_total"] == 1 and any(e["kind"] == "deviation_accepted" and e.get("risk") == "high" for e in done["events"]),
                      "After an accept the batch has a result, the page is given the whole trial, and the accepted deviation is logged (marked high risk)", f"trial 12 {row['verdict']}")
        cl.record(log["decision"] in ("Accepted", "Rejected") and (log["decision"] == "Accepted") == (choice == "accept") and len(log["decided_at"]) == 8 and log["trial"] == 12, "The decision is in the log with the trial, what was found and the time it was made", f"{log['decision']} at {log['decided_at']}")
    finally:
        server.shutdown()


def standing_rule_live(cl: Checklist) -> None:
    run = LiveRun(EXAMPLE_4, speed=1_000_000.0, save_to=None)
    run.start()
    done = wait_for(lambda: run.status in ("finished", "failed") or None, 240, 0.5)
    state = run.state()
    row = next((r for r in state["results"] if r["trial"] == 12), None)
    cl.record(bool(done) and run.status == "finished" and not run.approval_pending() and row is not None and row["verdict"] == "No result",
              "A live run with nobody at a page never waits: the standing rule skips the batch and the run finishes", f"status {run.status}; trial 12 {row['verdict'] if row else 'missing'}")


def chrome_checks(cl: Checklist) -> None:
    if not CHROME.exists():
        cl.skip("In real Chrome the page shows the decision card", "Chrome is not installed here")
        return
    server = LiveServer(port=0, setup_path=EXAMPLE_4, save_to=None)
    server.start_in_thread()
    port = server.port
    try:
        threading.Thread(target=lambda: server.run.fast_forward(FAULT_MINUTE * 60 + 5, 300), daemon=True).start()
        if not wait_for(lambda: get(port, "/state")["approval"], 150):
            cl.record(False, "In real Chrome the page shows the decision card", "the run never stopped")
            return

        def dom(query: str) -> str | None:
            with tempfile.TemporaryDirectory() as tmp:
                for budget in (9000, 20000):
                    done = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}\\p{budget}", f"--virtual-time-budget={budget}", "--dump-dom",
                                           f"http://127.0.0.1:{port}/console?{query}&welcome=off"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
                    if 'id="gate"' in done.stdout and "view-operator" in done.stdout:
                        return done.stdout
            return None

        page = dom("tab=operator")
        card = bool(page) and 'class="gate-card"' in page and 'id="gateAccept"' in page and 'id="gateReject"' in page and "HIGH RISK" in page and "Waiting for a decision" in page
        cl.record(card, "In real Chrome, while the cell waits, the page shows the red decision card with both buttons, says the run is waiting for a decision, and marks it high risk", "found" if card else "Chrome did not produce it")
        post(server, "decide", "reject")
        time.sleep(1.5)
        page = dom("tab=manager")
        operator = (page or "").split('id="view-operator"')[-1].split("</section>")[0]
        log = bool(page) and 'class="gate-card"' not in operator and "Rejected" in page.split('id="decisions"')[1][:1500] and page.count('title="Handled automatically') >= 1
        cl.record(log, "In real Chrome, after a reject the card is gone and the Lab manager's decisions log shows the rejection, with the older faults tagged low risk", "found" if log else "not found")
    finally:
        server.shutdown()


def main() -> int:
    cl = Checklist("HIGH-RISK FINDINGS: does a wrong vial stop the cell until a person accepts or rejects it?")
    before = project_files()
    setup_checks(cl)
    batch_checks(cl)
    live_checks(cl, "reject")
    live_checks(cl, "accept")
    standing_rule_live(cl)
    chrome_checks(cl)
    source = (ROOT / "cellpoc" / "live" / "console_part3.js").read_text(encoding="utf-8") + (ROOT / "cellpoc" / "live" / "console_template.html").read_text(encoding="utf-8")
    cl.record(not developer_words(source), "No developer wording (file names, document or stage names) is anywhere in the console's page or script, new card included", ", ".join(developer_words(source)))
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    cl.headline("A high-risk wrong vial stops the cell until a person decides; reject skips the batch, accept goes on and is logged; the old faults are unchanged.")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
