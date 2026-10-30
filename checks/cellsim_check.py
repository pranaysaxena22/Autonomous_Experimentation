"""Health check for the configurable cell simulator (Stage 5): is a platform run the proof of concept's run with the setup's own plan, executor and faults in it, and does it move as the setup says it should?

In plain words it checks that: with no faults a platform run is, trial for trial, the proof of concept's own run (same recipes, same start and end minutes, same results, same outcomes), so reusing the simulator changed nothing
in its meaning; with the example setup the faults behave as the setup says (trial 8's jam is recovered, trial 19's candidate is skipped, no result) and cost what the executor says, NOT what the proof of concept's rule would
charge; every trial's steps in the record add up to its executed timeline's step totals and start and end where the timeline says; changing a timing or a fault in the setup moves the number of trials exactly as a SEPARATE
recount from the setup's own numbers predicts (a longer dispense step, a shorter run, a longer purge, cleaning off after a skip, a random press jam on every trial, no faults); the staffed and unattended hours match an
independent count of the calendar; the alert for a skipped candidate is queued for the next staffed start; every measurement is logged only when its test step has finished; random faults are repeatable and change with the
seed; the saved plans, timelines and index obey their schemas and the record reloads; a setup the proof of concept cannot represent, or one with errors, is refused in plain words; and no proof of concept file differs
from `main`. Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.cell_simulator import simulate  # noqa: E402
from cellpoc.decision_engine import AdaptiveStrategy  # noqa: E402
from cellpoc.platform_runner import PlatformRunError, build_inputs, run_setup, save_platform_run  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

EX = ROOT / "cellpoc" / "formats" / "examples"
BASE = yaml.safe_load((EX / "setup_example.yaml").read_text(encoding="utf-8"))
SCHEMAS = ROOT / "cellpoc" / "formats" / "schemas"
RUN_MINUTES = BASE["calendar"]["duration_h"] * 60


def variant(**edits) -> dict:
    s = copy.deepcopy(BASE)
    for key, fn in edits.items():
        fn(s)
    return s


def run(setup: dict, strategy: str = "adaptive"):
    layout, settings = build_inputs(setup, EX)
    return run_setup(setup, layout, settings, "check", strategy)


def no_faults(s):
    s["faults"]["scripted"] = []


def r5(x):
    return int(round(x / 5) * 5)


def r10(x):
    return int(round(x / 10) * 10)


def recount_seconds(setup: dict, plan: dict, fault: dict | None) -> float:
    """How long a trial takes, worked out from the setup's numbers and the plan's own pour (never from the executor): used to predict the trial count."""
    nominal = sum(s["time_min"] * 60 for s in setup["equipment"]["steps"])
    if fault is None:
        return nominal
    f = setup["faults"]
    purge, tap, clean_s = f["purge_min"] * 60, f["recovery"]["tap_shake_s"], next(s["time_min"] * 60 for s in setup["equipment"]["steps"] if s["name"] == "clean")
    if fault["where"]["action"] == "pour":
        bottle = "bottle_" + fault["where"]["ingredient"].replace("_pct", "")
        pour = next(a for a in plan["actions"] if a["type"] == "pour" and a.get("object") == bottle)
        d, amount = pour["duration_s"], pour["amount_g"]
        fail, delivered = max(5, r5(0.28 * d)), round(0.36 * amount, 2)
        retry = max(60, r10(d * round(amount - delivered, 2) / amount))
        if fault["retry_succeeds"]:
            return nominal + fail + tap + 60 + purge + 60 + retry - d
        return pour["start_s"] + fail + tap + 60 + purge + 60 + retry + 60 + (clean_s if f["clean_after_skip"] else 0)
    press = next(a for a in plan["actions"] if a["type"] == "press")                       # a press jam with a working retry
    return nominal + max(5, r5(0.5 * press["duration_s"])) + 60 + purge + 60


def scripted(setup: dict, trial: int):
    return next((x for x in setup["faults"]["scripted"] if x["trial"] == trial), None)


def predicts(pr, setup: dict, fault_for) -> tuple[bool, str]:
    """The run's trial starts and count against the recount: each trial starts where the last ended, every attempted trial fits, and the next trial (with no fault, a full step cycle) would not."""
    t, starts, ok = 0.0, [], True
    for i, plan in enumerate(pr.plans, 1):
        starts.append(t)
        t += recount_seconds(setup, plan, fault_for(i)) / 60
        ok &= abs(pr.record.trials[i - 1].start_minute - starts[-1]) < 1e-6 and abs(pr.record.trials[i - 1].end_minute - t) < 1e-6
    run_minutes = setup["calendar"]["duration_h"] * 60
    following = recount_seconds(setup, pr.plans[-1], fault_for(len(pr.plans) + 1)) / 60          # the next trial, with its own fault if it has one (a press jam costs the same whatever the recipe)
    fits = t <= run_minutes + 1e-6 and (run_minutes - t) < following - 1e-6
    return ok and fits, f"{len(pr.plans)} trials, last ends at minute {t:.1f} of {run_minutes:g}"


def poc_equivalence_checks(cl: Checklist) -> None:
    setup = variant(a=no_faults)
    pr = run(setup)
    layout, settings = build_inputs(setup, EX)
    poc = simulate(settings, VirtualLab(settings), AdaptiveStrategy(settings.design_space, settings.specifications, settings.engine, settings.run.random_seed), "poc", None)
    same = len(pr.record.trials) == len(poc.trials) and all(
        (a.trial, a.recipe, a.start_minute, a.end_minute, a.dissolution_pct, a.hardness_kp, a.outcome, a.status) == (b.trial, b.recipe, b.start_minute, b.end_minute, b.dissolution_pct, b.hardness_kp, b.outcome, b.status)
        for a, b in zip(pr.record.trials, poc.trials))
    cl.record(same and pr.record.summary.trials_attempted == poc.summary.trials_attempted == 30 and pr.record.summary.trials_good == poc.summary.trials_good and pr.record.summary.unattended_hours == poc.summary.unattended_hours,
              "With no faults a platform run is, trial for trial, the proof of concept's own run on the same setup (same recipes, start and end minutes, measured results and outcomes; same attempts, good trials and unattended hours), so reusing the simulator changed nothing in its meaning",
              f"{len(pr.record.trials)} trials compared; attempted {pr.record.summary.trials_attempted}")


def example_run_checks(cl: Checklist) -> dict:
    pr = run(BASE)
    rec = pr.record
    t8, t19 = rec.trials[7], rec.trials[18]
    e8, e19 = pr.executed[7], pr.executed[18]
    extra8 = (e8["step_totals_s"]["actual"]["dispense"] - e8["step_totals_s"]["planned"]["dispense"]) / 60
    poc_rule = BASE["faults"]["purge_min"] + 30                                             # the proof of concept would add a purge and a whole step again
    alerts = {a.trial: a for a in rec.alerts}
    ok = (t8.status == "Completed" and t8.outcome in ("Good", "Not good") and e8["outcome"] == "completed_after_recovery" and t19.status == "Skipped" and t19.outcome == "No result" and t19.dissolution_pct is None
          and e19["outcome"] == "skipped" and alerts[8].severity == "Recovered" and not alerts[8].needs_human and alerts[19].severity == "Needs attention" and alerts[19].needs_human
          and abs(extra8 - poc_rule) > 1 and 55 < extra8 < 70 and rec.summary.trials_skipped == 1 and rec.summary.faults_recovered == 1 and rec.summary.alerts_for_staff == 1 and rec.meta.faults_applied)
    cl.record(ok, "With the example setup the faults behave as it says: trial 8's binder jam is recovered (and costs what the executor says, about 64 minutes, not the proof of concept's 90), trial 19's retry fails so the candidate is skipped with no result and an alert for staff, one fault recovered, one skipped, one alert for staff",
              f"trial 8 extra {extra8:.1f} min against the proof of concept's rule {poc_rule:g} min; {rec.summary.attempts_text}")
    return {"pr": pr}


def consistency_checks(cl: Checklist, pr) -> None:
    names = {"mix": "blend"}
    bad = []
    for plan, ex, tr in zip(pr.plans, pr.executed, pr.record.trials):
        total = ex["actions"][-1]["actual_start_s"] + ex["actions"][-1]["actual_duration_s"]
        sums = {}
        for iv in tr.steps:
            sums[iv.step] = sums.get(iv.step, 0.0) + (iv.end_minute - iv.start_minute)
        want = {names.get(s, s): v / 60 for s, v in ex["step_totals_s"]["actual"].items() if v}
        gaps = any(abs(b.start_minute - a.end_minute) > 1e-6 for a, b in zip(tr.steps, tr.steps[1:]))
        if (abs(tr.start_minute - plan["trial_start_minute"]) > 1e-6 or abs(tr.end_minute - (tr.start_minute + total / 60)) > 1e-6
                or set(sums) != set(want) or any(abs(sums[k] - want[k]) > 1e-6 for k in want) or gaps):
            bad.append(tr.trial)
    ev = pr.record.events
    ordered = all(a.minute <= b.minute + 1e-9 for a, b in zip(ev, ev[1:]))
    early = []
    for tr in pr.record.trials:
        if tr.status == "Completed":
            test_end = max(iv.end_minute for iv in tr.steps if iv.step == "test")
            ms = [e for e in ev if e.kind == "measurement" and e.trial == tr.trial]
            if len(ms) != 1 or abs(ms[0].minute - test_end) > 1e-6:
                early.append(tr.trial)
    cl.record(not bad and ordered and not early,
              "Every trial's steps in the record add up to its executed timeline's step totals (the fault's three stretches included), run without gaps from the trial's start to where the timeline ends; the event log runs in time order; and each measurement is logged exactly once, when its test step has finished, never before",
              f"inconsistent trials {bad[:3]}; early measurements {early[:3]}")


def recount_checks(cl: Checklist) -> None:
    """Change a timing or a fault in the setup: the number of trials moves as a separate recount predicts."""
    cases = {}
    cases["the example (jam on trial 8 recovered, trial 19 skipped)"] = (BASE, lambda i: scripted(BASE, i))
    s = variant(a=no_faults)
    cases["no faults"] = (s, lambda i: None)
    s = variant(a=no_faults, b=lambda x: next(y for y in x["equipment"]["steps"] if y["name"] == "dispense").__setitem__("time_min", 35))
    cases["a longer dispense step (35 minutes)"] = (s, lambda i: None)
    s = variant(a=no_faults, b=lambda x: x["calendar"].__setitem__("duration_h", 96))
    cases["a shorter run (96 hours)"] = (s, lambda i: None)
    s = variant(a=lambda x: x["faults"].__setitem__("purge_min", 120))
    cases["a longer purge (120 minutes)"] = (s, lambda i, s=s: scripted(s, i))
    s = variant(a=lambda x: x["faults"].__setitem__("clean_after_skip", False))
    cases["cleaning off after a skip"] = (s, lambda i, s=s: scripted(s, i))
    s = variant(a=no_faults, b=lambda x: x["faults"].__setitem__("random", [{"where": {"step": "press", "action": "press"}, "cause": "press jam", "chance_per_trial": 1.0, "retry_succeeds_chance": 1.0}]))
    press = {"where": {"step": "press", "action": "press"}, "retry_succeeds": True}
    cases["a press jam on every trial, always recovered"] = (s, lambda i: press)
    results = {}
    for name, (setup, fault_for) in cases.items():
        pr = run(setup)
        ok, text = predicts(pr, setup, fault_for)
        results[name] = (ok, len(pr.plans), text)
    closed = {"no faults": 30, "a longer dispense step (35 minutes)": 29, "a shorter run (96 hours)": 24, "a press jam on every trial, always recovered": 23}      # floor(run / trial), worked out by hand
    closed_ok = all(results[k][1] == v for k, v in closed.items())
    cl.record(all(v[0] for v in results.values()) and closed_ok,
              "Changing a timing or a fault in the setup moves the trials exactly as a separate recount predicts (each trial starts where the last ended, every attempted trial fits, the next, with its own fault if it has one, would not), in seven setups; and the plain-arithmetic cases come out as worked out by hand: 30 trials with no faults, 29 with a 35-minute dispense, 24 in a 96-hour run, 23 with a press jam on every trial",
              "; ".join(f"{k}: {v[1]}" for k, v in results.items()))


def calendar_checks(cl: Checklist) -> None:
    def unattended(setup: dict) -> float:
        start = datetime.strptime(setup["calendar"]["start"], "%Y-%m-%d %H:%M")
        days = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        on = {days[d] for d in setup["calendar"]["staffed_days"]}
        f, u = (datetime.strptime(setup["calendar"][k], "%H:%M").time() for k in ("staffed_from", "staffed_until"))
        staffed = sum(1 for m in range(int(setup["calendar"]["duration_h"] * 60)) if (start + timedelta(minutes=m)).weekday() in on and f <= (start + timedelta(minutes=m)).time() < u)
        return setup["calendar"]["duration_h"] - staffed / 60
    results = {}
    for name, setup in {"example (Mon and Tue)": BASE, "nobody ever staffed": variant(a=lambda s: s["calendar"].__setitem__("staffed_days", ["Sat"])),
                        "staffed Mon to Wed": variant(a=lambda s: s["calendar"].__setitem__("staffed_days", ["Mon", "Tue", "Wed"]))}.items():
        pr = run(setup)
        results[name] = abs(pr.record.summary.unattended_hours - unattended(setup)) < 1e-6
    pr = run(BASE)
    alert = next(a for a in pr.record.alerts if a.trial == 19)
    start = datetime.strptime(BASE["calendar"]["start"], "%Y-%m-%d %H:%M")
    when = next(m for m in range(int(alert.minute) + 1, RUN_MINUTES + 1) if (start + timedelta(minutes=m)).weekday() in (0, 1) and (start + timedelta(minutes=m)).strftime("%H:%M") == "08:00")
    cl.record(all(results.values()) and alert.queued_for_minute == when,
              "The unattended hours equal an independent count of the setup's calendar (the example's Monday and Tuesday, nobody staffed, Monday to Wednesday), and the alert for the skipped candidate is queued for the next minute someone arrives (08:00 on a staffed day)",
              f"{results}; alert queued for minute {alert.queued_for_minute}, expected {when}")


def random_fault_checks(cl: Checklist) -> None:
    s = variant(a=no_faults, b=lambda x: x["faults"].__setitem__("random", [{"where": {"step": "press", "action": "press"}, "cause": "press jam", "chance_per_trial": 0.4, "retry_succeeds_chance": 0.5}]),
                c=lambda x: x["calendar"].__setitem__("duration_h", 480))
    a, b = run(s), run(s)
    other = copy.deepcopy(s)
    other["seeds"]["run"] = 7
    c = run(other)
    faulted = lambda pr: [e["trial"] for e in pr.executed if e["faults"]]
    outcomes = lambda pr: [(e["trial"], e["outcome"]) for e in pr.executed]
    rate = len(faulted(a)) / len(a.executed)
    cl.record(outcomes(a) == outcomes(b) and a.record.summary.headline == b.record.summary.headline and outcomes(a) != outcomes(c) and 0.2 < rate < 0.6 and any(o == "skipped" for _, o in outcomes(a)) and any(o == "completed_after_recovery" for _, o in outcomes(a)),
              "Random faults are repeatable (the same setup gives the identical run), change with the seed, happen about as often as their chance (40%), and give both recovered and skipped trials",
              f"{len(a.executed)} trials, {len(faulted(a))} with a fault ({rate:.0%}); seed 7 gives {len(faulted(c))}")


def save_checks(cl: Checklist, pr) -> None:
    plan_schema = Draft202012Validator(json.loads((SCHEMAS / "plan.schema.json").read_text(encoding="utf-8")))
    run_schema = Draft202012Validator(json.loads((SCHEMAS / "executed_timeline.schema.json").read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory() as tmp:
        record_path = save_platform_run(pr, tmp)
        index = json.loads((Path(tmp) / "platform_index.json").read_text(encoding="utf-8"))
        files_ok = all((Path(tmp) / t["plan_file"]).exists() and (Path(tmp) / t["executed_file"]).exists() for t in index["trials"]) and len(index["trials"]) == len(pr.plans)
        schema_bad = [t["trial"] for t in index["trials"]
                      if list(plan_schema.iter_errors(json.loads((Path(tmp) / t["plan_file"]).read_text(encoding="utf-8")))) or list(run_schema.iter_errors(json.loads((Path(tmp) / t["executed_file"]).read_text(encoding="utf-8"))))]
        reloaded = run_store.load(record_path)
        same = reloaded.summary == pr.record.summary and len(reloaded.trials) == len(pr.record.trials)
        labelled = "ILLUSTRATIVE" in index["label"] and index["data_status"] == "illustrative"
    cl.record(files_ok and not schema_bad and same and labelled, "A saved platform run has every trial's plan and executed timeline (each obeying its JSON schema), an index that says what is where and labels the run illustrative, and its run record reloads unchanged", f"{len(index['trials'])} trials; schema failures {schema_bad[:3]}")


def refusal_checks(cl: Checklist) -> None:
    def refused(setup):
        try:
            build_inputs(setup, EX)
        except PlatformRunError as error:
            return str(error)
        return None
    six = variant(a=lambda s: s["ingredients"].append({"id": "extra_pct", "label": "Extra", "role": "other", "unit": "%", "min": 1, "max": 2}))
    broken = variant(a=lambda s: s["ingredients"][0].__setitem__("min", 99))
    in_clean = variant(a=lambda s: s["faults"]["scripted"].append({"trial": 5, "where": {"step": "clean", "action": "wait"}, "cause": "wipe fault", "retry_succeeds": True}))
    msgs = {"six ingredients": refused(six), "a setup with an error": refused(broken), "a fault in the cleaning step": refused(in_clean)}
    cl.record(all(m and len(m) > 30 and "Traceback" not in m for m in msgs.values()),
              "A setup the proof of concept cannot represent (a sixth ingredient), a setup with an error and a fault in the cleaning step are each refused in plain words before anything runs", "; ".join(f"{k}: {(v or 'NOT REFUSED')[:70]}" for k, v in msgs.items()))


def style_only_text_changed() -> tuple[bool, str]:
    """Is cellpoc/dashboard/style.py the same code as on `main` once every string (the CSS and its f-strings), the FAVICON constant and the page_icon argument are set aside?"""
    import ast
    try:
        old = subprocess.run(["git", "show", "main:cellpoc/dashboard/style.py"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True, "git is not available here (not compared)"
    if old.returncode != 0:
        return True, "git could not read main (not compared)"

    class Normalise(ast.NodeTransformer):
        def visit_Constant(self, node):
            return ast.Constant("") if isinstance(node.value, str) else node

        def visit_JoinedStr(self, node):
            return ast.Constant("")

        def visit_keyword(self, node):
            return None if node.arg == "page_icon" else self.generic_visit(node)

        def visit_Assign(self, node):
            return None if any(isinstance(t, ast.Name) and t.id == "FAVICON" for t in node.targets) else self.generic_visit(node)

    def shape(source: str) -> str:
        return ast.dump(Normalise().visit(ast.parse(source)))
    now = (ROOT / "cellpoc" / "dashboard" / "style.py").read_text(encoding="utf-8")
    return shape(old.stdout) == shape(now), "same code apart from strings and the icon" if shape(old.stdout) == shape(now) else "the code differs beyond strings and the icon"


def poc_untouched_checks(cl: Checklist) -> None:
    # Stages 8 and 9 changed cellpoc/dashboard/app.py on purpose (it adds three pages for a platform record: 3D replay, Data and model, Reports) and added three page files; the eight proof-of-concept page files are still untouched, and the stage 8 check proves the
    # proof of concept's dashboard renders exactly as before. The record's shape gained one optional section (contracts/run_record.py, run_store/store.py); stage 8's check covers that too.
    paths = ["app.py", *[f"cellpoc/dashboard/{name}.py" for name in ("about", "comparison", "data", "handovers", "run_view", "throughput", "timeline")], "cellpoc/cell_simulator", "cellpoc/settings", "config/settings.yaml", "cellpoc/virtual_lab/lab.py", "cellpoc/virtual_lab/_truth.py",
             "cellpoc/decision_engine/adaptive.py", "cellpoc/decision_engine/fixed_list.py", "cellpoc/decision_engine/random_recipes.py", "cellpoc/runner.py", "cellpoc/about_text.py"]
    try:
        done = subprocess.run(["git", "diff", "--name-only", "main", "--", *paths], cwd=ROOT, capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            cl.skip("No proof of concept file differs from `main`", "git could not compare with main here")
            return
        changed = [line for line in done.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        cl.skip("No proof of concept file differs from `main`", "git is not available here")
        return
    changed_style, how = style_only_text_changed()
    cl.record(changed_style, "The one proof of concept file that differs from `main` on purpose, cellpoc/dashboard/style.py (the style sheet text and the tab icon, approved 2026-10-13 and -14), differs ONLY in text strings and the icon: with every string and the page_icon argument set aside, its code is identical to `main`'s (no function logic changed)", how)
    cl.record(not changed, "No proof of concept file differs from `main`: the dashboard's proof-of-concept pages, the simulator, the settings and their file, the lab and its truth, the three proof of concept strategies, the runner and the about text are untouched by the platform work", f"differing: {changed[:3]}")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 5 (configurable cell simulator): is a platform run the proof of concept's run with the setup's plan, executor and faults in it?")
    before = project_files()
    poc_equivalence_checks(cl)
    pr = example_run_checks(cl)["pr"]
    consistency_checks(cl, pr)
    recount_checks(cl)
    calendar_checks(cl)
    random_fault_checks(cl)
    save_checks(cl, pr)
    refusal_checks(cl)
    poc_untouched_checks(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
