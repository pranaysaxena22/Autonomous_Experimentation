"""Health check for the job queue: several jobs for several drugs, each started one at a time or run one after another by itself, with a shelf of ingredients that can run out.

In plain words it checks that: the queue starts one job at a time and refuses a second with a plain sentence; run by itself it works through the jobs in order, and a job that runs out of an ingredient is marked blocked
with the reason in plain words and the queue moves on to the next; a job that cannot even start because the shelf is empty is blocked at once and says so; a run that fails is never silent; a job a person stops goes back to waiting;
a restock lets a blocked job be started again, and a reset puts everything back; the shelf is all-or-nothing and never goes below nothing; in the real simulation a job stops cleanly between trials when an ingredient cannot cover the
next batch (its record is complete, its events are in time order, and it says why it stopped), an almost empty shelf does not crash it, and a shelf that is big enough changes nothing about a run (exactly the same trials and
events as with no shelf); on the real server the queue's controls work, name a job only by its id, need the page's secret, and each job becomes the run the three views show, with the page told when the run is a different one;
the Jobs view shows the queue and the shelf in real Chrome; the scheduler part imports nothing but the shared data shapes; and nothing is written into the project.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.contracts import IngredientMissing  # noqa: E402
from cellpoc.decision_engine import AdaptiveStrategy  # noqa: E402
from cellpoc.executor import PythonStandInExecutor  # noqa: E402
from cellpoc.live.server import LiveServer  # noqa: E402
from cellpoc.platform_cell import PlatformSimulation  # noqa: E402
from cellpoc.platform_runner import load_inputs  # noqa: E402
from cellpoc.scheduler import Inventory, Job, JobQueue  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from checks.approvals_check import get, wait_for  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.console_check import developer_words  # noqa: E402
from checks.models_check import project_files  # noqa: E402

EXAMPLES = ROOT / "cellpoc" / "formats" / "examples"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


# ---------------------------------------------------------------- the queue's own logic, with a pretend runner (no simulation, so it is quick)
class PretendRun:
    def __init__(self, ending: tuple[str, str]):
        self.ending, self.steps, self.reason, self.folder, self.status = ending, 0, "", "", "running"

    def progress(self) -> tuple[int, int, int]:
        return self.steps, max(0, self.steps - 1), 0

    def stop(self) -> None:
        self.status = "stopped"

    def step(self) -> None:
        if self.status == "stopped":
            return
        self.steps += 1
        if self.steps >= 3:
            self.status, self.reason = self.ending


class PretendRunner:
    def __init__(self, endings: dict[str, tuple[str, str]]):
        self.endings, self.started = endings, []

    def minimum_need(self, job) -> dict[str, float]:
        return {"binder_pct": 0.4}

    def start(self, job, inventory):
        self.started.append(job.id)
        run = PretendRun(self.endings[job.id])
        run.folder = f"runs/jobs/{job.id}"
        return run


def pretend_queue(endings, binder: float = 26.0):
    inventory = Inventory({"binder_pct": binder}, {"binder_pct": 120.0}, {"binder_pct": "Binder"})
    jobs = [Job("job-1", "Drug 1", "example:1", "Example 1"), Job("job-2", "Drug 2", "example:3", "Example 3"), Job("job-3", "Drug 3", "example:2", "Example 2")]
    runner = PretendRunner(endings)
    return JobQueue(jobs, inventory, runner, watch=False), runner, jobs


def drive(queue: JobQueue, jobs, rounds: int = 30) -> None:
    for _ in range(rounds):
        for job in jobs:
            if job.handle is not None:
                job.handle.step()
        queue.tick()


def queue_logic(cl: Checklist) -> None:
    short = ("blocked", "Binder is missing: the next batch needs 0.90 g and only 0.30 g is left.")
    queue, runner, jobs = pretend_queue({"job-1": ("finished", ""), "job-2": short, "job-3": ("finished", "")})
    first = queue.start("job-2")
    second, unknown, wrong_type = queue.start("job-1"), queue.start("nope"), queue.start(7)
    cl.record(first is None and "already running" in (second or "") and "not in the queue" in (unknown or "") and "not in the queue" in (wrong_type or ""),
              "One job at a time: a second start while one runs, a job that is not in the queue and a job named by something that is not an id are each refused with a plain sentence", str(second))
    drive(queue, jobs)
    cl.record([j.status for j in jobs] == ["pending", "blocked", "pending"] and "Binder is missing" in jobs[1].reason and not queue.automated,
              "A job that runs out of an ingredient is marked blocked with the reason in plain words, and a job started by hand does not start the next one", jobs[1].reason[:70])
    queue, runner, jobs = pretend_queue({"job-1": ("finished", ""), "job-2": short, "job-3": ("finished", "")})
    queue.run_all()
    drive(queue, jobs)
    cl.record([j.status for j in jobs] == ["completed", "blocked", "completed"] and runner.started == ["job-1", "job-2", "job-3"] and not queue.automated,
              "Run by itself the queue works through the jobs in order, a blocked job does not stop it, and it switches itself off at the end", f"{[j.status for j in jobs]}")
    cl.record(jobs[0].folder == "runs/jobs/job-1" and "already completed" in (queue.start("job-1") or ""), "A completed job keeps where its record was saved, and is not started a second time", jobs[0].folder)
    queue, runner, jobs = pretend_queue({"job-1": ("finished", ""), "job-2": ("finished", ""), "job-3": ("finished", "")}, binder=0.1)
    queue.run_all()
    cl.record(all(j.status == "blocked" and "did not start" in j.reason and "Binder is missing" in j.reason for j in jobs) and runner.started == [],
              "With the shelf too empty to make even the smallest batch, every job is blocked at once and says so; nothing is started", jobs[0].reason[:90])
    queue.restock()
    cl.record(queue.start("job-1") is None and (drive(queue, jobs, 10) or True) and jobs[0].status == "completed" and queue.snapshot().supplies[0].left_g == 120.0,
              "After a restock a blocked job can be started again and completes", "")
    queue, runner, jobs = pretend_queue({"job-1": ("failed", ""), "job-2": ("finished", ""), "job-3": ("finished", "")})
    queue.start("job-1")
    drive(queue, jobs, 6)
    queue.start("job-2")
    jobs[1].handle.stop()
    queue.tick()
    cl.record(jobs[0].status == "blocked" and len(jobs[0].reason) > 20 and jobs[1].status == "pending" and not queue.automated,
              "A run that fails is never silent (it is marked blocked with a reason), and a job a person stops goes back to waiting", jobs[0].reason)
    queue.run_all()
    queue.reset()
    cl.record(all(j.status == "pending" and j.reason == "" and j.handle is None for j in jobs) and not queue.automated and queue.snapshot().supplies[0].left_g == 26.0,
              "Reset puts every job back to waiting, switches the automation off and puts the shelf back as it was", "")
    shelf = Inventory({"a": 5.0, "b": 1.0}, {"a": 9.0, "b": 9.0}, {"a": "A", "b": "B"})
    try:
        shelf.take({"a": 2.0, "b": 2.0})
        taken = True
    except IngredientMissing as missing:
        taken = False
        said = missing.message
    cl.record(not taken and [s.left_g for s in shelf.levels()] == [5.0, 1.0] and "B is missing" in said and "2.00 g" in said and "1.00 g" in said,
              "The shelf is all-or-nothing: when one ingredient is short nothing is taken, and the message names it with the amounts", said)


# ---------------------------------------------------------------- the real simulation against a shelf
def batch(name: str, supplies):
    setup, layout, settings = load_inputs(EXAMPLES / name)
    engine = AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine, settings.run.random_seed)
    return PlatformSimulation(settings, setup, layout, VirtualLab(settings), engine, "jobs", PythonStandInExecutor(), supplies=supplies).run_platform()


def fingerprint(run) -> str:
    rec = run.record
    return hashlib.sha256(json.dumps({"t": [(t.trial, t.status, t.outcome, t.dissolution_pct, t.start_minute, t.recipe) for t in rec.trials], "e": [(e.kind, round(e.minute, 4), e.trial) for e in rec.events],
                                      "x": run.executed}, sort_keys=True, default=str).encode()).hexdigest()


def left(shelf: Inventory, ingredient: str) -> float:
    return next(s.left_g for s in shelf.levels() if s.ingredient == ingredient)


def sim_needs(plan: dict, layout: dict) -> dict[str, float]:
    """Grams of each ingredient a plan weighs out, worked out here from the layout and the plan's own pours (a second route to the same number the simulation uses)."""
    ingredient_of = {o["id"]: o["ingredient_id"] for o in layout["objects"] if o["type"] == "bottle"}
    needs: dict[str, float] = {}
    for a in plan["actions"]:
        if a["type"] == "pour" and a.get("at") == "balance" and a.get("object") in ingredient_of:
            needs[ingredient_of[a["object"]]] = needs.get(ingredient_of[a["object"]], 0.0) + a["amount_g"]
    return needs


def simulation_checks(cl: Checklist) -> None:
    shelf = Inventory.demo()
    start = {s.ingredient: s.left_g for s in shelf.levels()}
    one = batch("setup_example.yaml", shelf)
    after_one = {s.ingredient: s.left_g for s in shelf.levels()}
    consumed: dict[str, float] = {}
    for plan in one.plans:
        for ingredient, grams in sim_needs(plan, one.layout).items():
            consumed[ingredient] = consumed.get(ingredient, 0.0) + grams
    cl.record(all(abs(after_one[i] - (start[i] - consumed.get(i, 0.0))) < 0.01 for i in start) and sum(consumed.values()) > 0,
              "What the shelf loses is exactly what the plans weigh out, ingredient by ingredient (checked against the first job)", ", ".join(f"{i[:-4]} {consumed[i]:.1f} g" for i in consumed))
    three = batch("setup_example_3_demanding_targets.yaml", shelf)
    rec = three.record
    stop = next((e for e in rec.events if e.kind == "job_blocked"), None)
    cl.record(len(one.record.trials) == 30 and not any(e.kind == "job_blocked" for e in one.record.events) and stop is not None and len(rec.trials) < 24,
              "On a shelf that is too small, the first job completes and the second stops part-way, between trials, saying so in the log", f"{len(one.record.trials)} trials, then {len(rec.trials)} of 24")
    last = rec.events[-1]
    cl.record(stop is not None and "Binder is missing" in stop.message and last.kind == "run_finished" and "The job stopped here" in last.message and [e.minute for e in rec.events] == sorted(e.minute for e in rec.events)
              and rec.summary.trials_attempted == len(rec.trials),
              "The stopped job's record is complete: its events are in time order, it says which ingredient ran out and the amounts, and its summary matches its trials", stop.message[:100] if stop else "no stop found")
    tiny = Inventory({"drug_pct": 250.0, "filler_pct": 1600.0, "binder_pct": 0.5, "disintegrant_pct": 500.0, "lubricant_pct": 40.0},
                     {"binder_pct": 120.0, "drug_pct": 400.0, "filler_pct": 2000.0, "disintegrant_pct": 600.0, "lubricant_pct": 60.0})
    try:
        none = batch("setup_example.yaml", tiny).record
        ok = len(none.trials) == 0 and none.events[-1].kind == "run_finished"
    except Exception as error:  # noqa: BLE001
        ok, none = False, error
    cl.record(ok, "A shelf with almost nothing left stops the job before its first trial without crashing, and the record still builds", "no trials, run_finished" if ok else repr(none))
    plain = batch("setup_example.yaml", None)
    generous = batch("setup_example.yaml", Inventory({k: 100000.0 for k in start}, {k: 100000.0 for k in start}))
    cl.record(fingerprint(plain) == fingerprint(generous), "A shelf that is big enough changes nothing: the run has exactly the same trials, events and executed timelines as with no shelf", fingerprint(plain)[:12])


# ---------------------------------------------------------------- the real server
def post_raw(server: LiveServer, cmd: str, value=None, token: bool = True) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.port}"}
    if token:
        headers["X-Live-Token"] = server.token
    request = urllib.request.Request(f"http://127.0.0.1:{server.port}/control", data=json.dumps({"cmd": cmd, "value": value}).encode(), method="POST", headers=headers)
    try:
        reply = urllib.request.urlopen(request, timeout=60)
        return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def queue_of(port: int) -> dict:
    return get(port, "/state")["jobs"]


def server_checks(cl: Checklist) -> None:
    server = LiveServer(port=0, save_to=None)
    server.start_in_thread()
    port = server.port
    try:
        state = get(port, "/state")
        cl.record([j["drug"] for j in state["jobs"]["jobs"]] == ["Drug 1", "Drug 2", "Drug 3"] and all(j["status"] == "pending" for j in state["jobs"]["jobs"]) and len(state["jobs"]["supplies"]) == 5 and state["epoch"],
                  "The page's state carries the queue (three drugs, all waiting) and the shelf (five ingredients), and says which run it is showing", str([j["setup_label"][:9] for j in state["jobs"]["jobs"]]))
        no_secret = post_raw(server, "job_start", "job-1", token=False)
        cl.record(no_secret[0] == 403 and queue_of(port)["active"] is None, "A queue control without the page's secret is refused and starts nothing", f"HTTP {no_secret[0]}")
        post_raw(server, "speed", 7200)
        first_epoch = state["epoch"]
        started = post_raw(server, "job_start", "job-1")
        refusals = [post_raw(server, "job_start", "job-2"), post_raw(server, "job_start", "../../x"), post_raw(server, "job_start", 7)]
        now = get(port, "/state")
        cl.record(started[0] == 200 and all(code == 400 and len(reply["error"]) > 20 for code, reply in refusals) and now["epoch"] != first_epoch and now["setup_label"].startswith("Drug 1:") and now["status"] == "running",
                  "Starting Drug 1 makes it the run the three views show (named for the drug, a new run id); a second start, an unknown name and a non-name are refused in plain words", now["setup_label"][:50])
        done = wait_for(lambda: (lambda q: q if q["jobs"][0]["status"] == "completed" else None)(queue_of(port)), 200, 0.5)
        if done is None:
            cl.record(False, "Drug 1 runs to its end and is marked completed", "it did not finish")
            return
        cl.record(done["jobs"][0]["trials_started"] == 30 and done["jobs"][0]["good"] > 0, "Drug 1 runs its 30 trials and is marked completed, with its counts", str(done["jobs"][0]["trials_with_result"]) + " results")
        run_all = post_raw(server, "job_run_all")
        end = wait_for(lambda: (lambda q: q if (not q["automated"] and q["active"] is None and q["jobs"][1]["status"] != "pending" and q["jobs"][2]["status"] != "pending") else None)(queue_of(port)), 240, 0.5)
        if end is None:
            cl.record(False, "Run by itself, the queue works through the rest", "it did not finish")
            return
        two, three = end["jobs"][1], end["jobs"][2]
        cl.record(run_all[0] == 200 and two["status"] == "blocked" and "Binder is missing" in two["reason"] and 0 < two["trials_started"] < 24 and three["status"] == "blocked" and "did not start" in three["reason"],
                  "Run by itself: Drug 2 stops part-way when the binder runs out (with the reason), the queue moves on, and Drug 3 is blocked at once because nothing is left", f"{two['trials_started']} trials; {two['reason'][:60]}")
        page = get(port, "/state")
        cl.record(any(a["kind"] == "job_blocked" for a in page["alerts"]) and page["status"] == "blocked" and "Binder is missing" in page["message"],
                  "The stopped job also shows on the run's own page (an alert, a blocked status and the reason), so it is never silent", page["message"][:70])
        post_raw(server, "job_restock")
        shelf = {s["ingredient"]: s["left_g"] for s in queue_of(port)["supplies"]}
        again = post_raw(server, "job_start", "job-2")
        finished = wait_for(lambda: (lambda q: q if q["jobs"][1]["status"] in ("completed", "blocked") else None)(queue_of(port)), 200, 0.5)
        cl.record(shelf["binder_pct"] == 120.0 and again[0] == 200 and finished is not None and finished["jobs"][1]["status"] == "completed" and finished["jobs"][1]["reason"] == "",
                  "After a restock Drug 2 is started again, completes, and its old reason is gone", f"{finished['jobs'][1]['trials_started'] if finished else '?'} trials")
        dom = chrome_dom(port)
        if dom is None:
            cl.skip("In real Chrome the Jobs view shows the queue and the shelf", "Chrome is not installed here, or it did not produce the page")
        else:
            cl.record(all(w in dom for w in ('id="view-jobs"', "Drug 1", "Drug 2", "Drug 3", "COMPLETED", "Ingredients on the shelf", "Restock the shelf", "Reset the queue")),
                      "In real Chrome the Jobs view shows the three drugs with their status, the buttons and the ingredients on the shelf", "found")
        reset = post_raw(server, "job_reset")
        after = queue_of(port)
        cl.record(reset[0] == 200 and all(j["status"] == "pending" for j in after["jobs"]) and after["supplies"][2]["left_g"] == 26.0 and not after["automated"], "Reset puts the queue and the shelf back as they were", "")
    finally:
        server.shutdown()


def chrome_dom(port: int) -> str | None:
    if not CHROME.exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        for budget in (9000, 20000):
            done = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}\\p{budget}", f"--virtual-time-budget={budget}", "--dump-dom",
                                   f"http://127.0.0.1:{port}/console?tab=jobs&welcome=off"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
            if 'id="view-jobs"' in done.stdout and "Drug 3" in done.stdout:
                return done.stdout
    return None


def import_checks(cl: Checklist) -> None:
    imported = set()
    for path in (ROOT / "cellpoc" / "scheduler").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level >= 2 and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("cellpoc"):
                imported.add(node.module.split(".")[1])
    cl.record(imported <= {"contracts"}, "The scheduler part imports nothing but the shared data shapes (so it knows nothing about simulations, pages or files)", ", ".join(sorted(imported)) or "no other part")
    source = (ROOT / "cellpoc" / "live" / "console_part3.js").read_text(encoding="utf-8") + (ROOT / "cellpoc" / "live" / "console_template.html").read_text(encoding="utf-8")
    cl.record(not developer_words(source), "No developer wording is anywhere in the console's page or script, the Jobs view included", ", ".join(developer_words(source)))


def main() -> int:
    cl = Checklist("THE JOB QUEUE: several drugs, started one at a time or run by itself, with a shelf that can run out")
    before = project_files()
    queue_logic(cl)
    simulation_checks(cl)
    server_checks(cl)
    import_checks(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    cl.headline("Jobs run one at a time or by themselves; a job that runs out of an ingredient is blocked with the reason and the queue moves on; a restock lets it be started again.")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
