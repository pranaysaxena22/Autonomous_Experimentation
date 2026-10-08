"""Stage 5 health check: the dashboard.

Rebuilds the demonstration run record (about a minute), then checks:
  * the moment-by-moment data stored in it, against an independent recount from the trial list and settings;
  * the real dashboard, driven through Streamlit's test harness: tabs, slider, Next/Previous event, the result
    staying hidden until it is known, the comparison, the editable baseline;
  * that the dashboard reads only the run record, contains no logic of its own, and needs no internet.
Writes runs/demo/record.json (what the dashboard shows) and runs/stage5/dashboard_check_report.txt.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.runner import DEMO_FOLDER, run_full_demo  # noqa: E402
from cellpoc.settings import SettingsError, load_settings  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, external_references  # noqa: E402

OUT = ROOT / "runs" / "stage5"
checklist = Checklist("STAGE 5 CHECK - the dashboard")
record = checklist.record
EXPECTED_TABS = ["The run", "Timeline", "Overnight handovers", "Does learning help?", "Throughput", "What this shows"]


def staffed_at(settings, minute) -> bool:
    p, moment = settings.people, settings.run.start + timedelta(minutes=minute)
    return moment.weekday() in p.staffed_weekdays and p.staffed_from <= moment.time() < p.staffed_until


# ------------------------------------------------------------------ the stored moment-by-moment data
def check_snapshots(settings, run):
    snaps, trials, events = run.snapshots, run.trials, run.events
    duration = run.meta.duration_minutes
    gaps = [b.minute - a.minute for a, b in zip(snaps, snaps[1:])]
    record(snaps[0].minute == 0 and snaps[-1].minute == duration and all(0 < g <= 15 for g in gaps)
           and [s.index for s in snaps] == list(range(len(snaps))),
           "The slider covers the whole run from the first minute to the last, never more than 15 minutes between stops",
           f"{len(snaps)} stops")

    event_minutes = sorted({e.minute for e in events})
    flagged = [s.minute for s in snaps if s.is_event]
    record(flagged == event_minutes, "Every moment where something is logged is a stop on the slider, and only those are flagged as events",
           f"{len(event_minutes)} event moments")
    nav_ok = True
    for s in snaps:
        later = [x for x in snaps if x.is_event and x.minute > s.minute]
        earlier = [x for x in snaps if x.is_event and x.minute < s.minute]
        nav_ok &= (s.next_event_index == (later[0].index if later else None)
                   and s.previous_event_index == (earlier[-1].index if earlier else None))
    record(nav_ok, "'Next event' always lands on the very next event and 'Previous event' on the one before, checked at every stop")
    record(snaps[0].previous_event_index is None and snaps[-1].next_event_index is None,
           "There is no previous event at the start and no next event at the end")

    record(all(s.staff_present == staffed_at(settings, s.minute) for s in snaps),
           "'Is anyone in the lab' is right at every stop, checked against the staffing settings")
    in_progress = lambda m: next((t.trial for t in trials if t.start_minute <= m < t.end_minute), None)  # noqa: E731
    record(all(s.trial == in_progress(s.minute) for s in snaps),
           "The trial shown at every stop is the trial actually in progress at that minute")

    # stations: recount from the step stretches
    bad = []
    for s in snaps:
        for station, step in zip(s.stations, run.steps):
            busy = [(i, t.trial) for t in trials for i in t.steps if i.step == step.name and i.start_minute <= s.minute < i.end_minute]
            if busy:
                interval, trial = busy[0]
                ok = station.state == interval.state and station.text == interval.status_text and f"trial {trial}" in station.text
            else:
                ok = station.state == "idle" and station.text == "Idle"
            if not ok:
                bad.append((s.when, station.station))
    record(not bad, "Each station's status at every stop matches a recount from the trial's steps (working, purging, retrying, idle)",
           f"{len(snaps)} stops x {len(run.steps)} stations" if not bad else f"mismatches: {bad[:3]}")
    one_busy = all(sum(st.state != "idle" for st in s.stations) <= 1 for s in snaps)
    record(one_busy, "At no moment are two stations busy at once (one trial at a time)")

    # phases
    phase_bad = []
    for s in snaps:
        t = next((x for x in trials if x.trial == s.trial), None)
        if t is None:
            continue
        active = [p.phase for p in t.phases if p.start_minute <= s.minute < p.end_minute]
        if (s.active_phase or None) != (active[0] if active else None):
            phase_bad.append(s.when)
        if [p.phase for p in s.phases] != ["Sense", "Reason", "Act", "Adapt"]:
            phase_bad.append(s.when)
    record(not phase_bad, "The active phase (Act, Sense, Reason or Adapt) at every stop matches the trial's recorded phases")

    # results stay hidden until known
    import dataclasses
    import json

    leaks, shown_late, checked = [], [], 0
    for t in trials:
        known = next(p.end_minute for p in t.phases if p.phase == ("Sense" if t.status == "Completed" else "Act"))
        for s in snaps:
            if s.trial != t.trial:
                continue
            if t.status == "Completed":
                numbers = (f"{t.dissolution_pct:.1f}%", f"{t.hardness_kp:.2f}")
                has_numbers = all(n in s.result_text for n in numbers)
                everywhere = json.dumps(dataclasses.asdict(s))   # ANY text in the snapshot: result box, phases, events, alerts
                if s.minute < known and (all(n in everywhere for n in numbers) or s.result_kind != "pending"):
                    leaks.append((t.trial, s.when))
                if s.minute >= known and not (has_numbers and s.result_kind in ("good", "not_good")):
                    shown_late.append((t.trial, s.when))
            else:
                if s.minute < known and s.result_kind != "pending":
                    leaks.append((t.trial, s.when))
                if s.minute >= known and s.result_kind != "no_result":
                    shown_late.append((t.trial, s.when))
            checked += 1
    record(not leaks, "A trial's result appears nowhere in any text of the page before it is known (the moment the test finishes)",
           f"{checked} trial-moments checked, every text field searched" if not leaks else f"LEAKS at: {leaks[:4]}")
    fault_hints = [(t.trial, s.when) for t in trials for s in snaps
                   if s.trial == t.trial and t.notes and s.minute < next(p.end_minute for p in t.phases if p.phase == "Act")
                   and any(p.phase == "Act" and p.state == "active" and ("clog" in p.description or "retry" in p.description)
                           for p in s.phases)]
    record(not fault_hints, "While a trial is still being made, its Act phase does not describe a fault that has not happened yet")
    record(not shown_late, "From that moment on the result is shown: numbers and verdict for a normal trial, 'no result' for the skipped one")

    why_ok = all(s.why == trials[s.trial - 1].reason and len(s.recipe_lines) == len(run.ingredient_labels)
                 for s in snaps if s.trial)
    record(why_ok, "At every stop the recipe and the why-text are those of the trial in progress")
    reason_leak = [s.when for s in snaps for p in s.phases
                   if p.phase == "Reason" and p.state == "active" and "Recipe" in p.description]
    record(not reason_leak, "While the engine is still reasoning, the dashboard does not reveal the next recipe early")

    finished_ok = all(s.trials_finished == sum(t.end_minute <= s.minute for t in trials)
                      and s.good_so_far == sum(t.outcome == "Good" and next(p.end_minute for p in t.phases if p.phase == "Sense") <= s.minute
                                               for t in trials if t.status == "Completed") for s in snaps)
    record(finished_ok, "The running counts (trials finished, good so far) are right at every stop")

    # alerts
    a8 = [a for a in run.alerts if a.trial == 8][0]
    a19 = [a for a in run.alerts if a.trial == 19][0]
    before = [s for s in snaps if s.minute < a19.minute][-1]
    at = [s for s in snaps if s.minute >= a19.minute][0]
    arrived = [s for s in snaps if a19.queued_for_minute is not None and s.minute >= a19.queued_for_minute][0]
    record(not any("trial 19" in x for x in before.alerts_so_far) and any("Waiting for staff" in x for x in at.alerts_so_far)
           and any("Staff arrived" in x for x in arrived.alerts_so_far) and any("RECOVERED" in x for x in arrived.alerts_so_far),
           "The alert for trial 19 appears when it happens, says it is waiting for staff, and changes once staff arrive; trial 8's shows as recovered",
           f"queued for {a19.queued_for}")


# ------------------------------------------------------------------ the real dashboard, through Streamlit's test harness
def check_dashboard_pages(settings, run):
    from streamlit.testing.v1 import AppTest

    os.environ.pop("CELLPOC_RECORD", None)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    app.run()
    record(not app.exception, "The dashboard starts and draws every page with no error", "; ".join(str(e.value) for e in app.exception))
    record([t.label for t in app.tabs] == EXPECTED_TABS, "The pages are in the requested order",
           " | ".join(t.label for t in app.tabs))
    banners = [m.value for m in app.markdown if '<div class="sim-banner">' in m.value]
    stamps = [m.value for m in app.markdown if '<div class="sim-stamp">' in m.value]
    record(len(banners) == 1 and "illustrative values" in banners[0].lower() and len(stamps) == len(EXPECTED_TABS)
           and all("illustrative values" in x.lower() for x in stamps),
           "'Simulation with illustrative values' is shown at the top of the dashboard and again on every page",
           f"{len(stamps)} page stamps")

    page_text = "\n".join(m.value for m in app.markdown)
    boxes = re.findall(r'class="phase phase-\w+">(\w+)<', page_text)
    record(boxes == ["SENSE", "REASON", "ACT", "ADAPT"],
           "The four phases are shown in the order Sense, Reason, Act, Adapt", " > ".join(boxes))
    record(any("loop that repeats for every trial" in c.value for c in app.caption),
           "A one-line note says the phases form a loop that repeats every trial")
    expanders = {e.label: e.proto.expanded for e in app.expander}
    record(expanders.get("Sense / Reason / Act / Adapt over time") is True and expanders.get("Station by station") is False,
           "On the Timeline page the phases-over-time view is open by default and the station-by-station view is collapsed",
           f"phases view open: {expanders.get('Sense / Reason / Act / Adapt over time')}; station view open: {expanders.get('Station by station')}")

    snaps = run.snapshots
    slider = app.select_slider[0]
    record(len(slider.options) == len(snaps) and app.button(key="previous_event").disabled and not app.button(key="next_event").disabled,
           "The run page has a time slider over every stop, a Next event button, and Previous event disabled at the start")

    # Next event, several times, then Previous
    expected, ok = 0, True
    for _ in range(8):
        app.button(key="next_event").click().run()
        expected = snaps[expected].next_event_index
        ok &= (app.session_state["snap_index"] == expected and not app.exception
               and any(s.value == snaps[expected].when for s in app.subheader))
    record(ok, "Clicking Next event eight times moves through the events in order, and the page shows each moment's time")
    app.button(key="previous_event").click().run()
    back = snaps[expected].previous_event_index
    record(app.session_state["snap_index"] == back, "Previous event steps back to the earlier event")

    def go(index):
        app.select_slider[0].set_value(index).run()
        page = "\n".join(m.value for m in app.markdown)
        return page

    def at_minute(minute):
        return next(s for s in snaps if s.minute == minute)

    sched = {t.trial: t for t in run.trials}
    t8 = sched[8]
    purge8 = at_minute(t8.start_minute + 30 + 15)           # 15 minutes into the purge, worked out from the trial's start
    page = go(purge8.index)
    record("Purging after binder dispenser clog: trial 8" in page and "tile-purge" in page and not app.exception,
           "Moved to the middle of trial 8's purge, the dispenser tile says it is purging after the clog, in the fault colour")
    retry8 = at_minute(t8.start_minute + 30 + 60 + 15)
    page = go(retry8.index)
    record("retry after the purge: trial 8" in page and "tile-retry" in page,
           "Fifteen minutes into the retry, the dispenser tile says it is retrying")

    t19 = sched[19]
    retry19_end = t19.start_minute + 30 + 60 + 30
    page = go(at_minute(retry19_end + 15).index)
    record("Cleaning after the skipped candidate (trial 19)" in page and "Waiting for staff, queued for" in page
           and any("No result" in e.value or "skipped" in e.value for e in app.error),
           "After trial 19's failed retry: the cleaning tile says it is cleaning after the skipped candidate, the alert waits for staff, the result says no result")

    # a result is hidden, then shown
    t = next(x for x in run.trials if x.status == "Completed" and x.trial == 10)
    sense_end = next(p.end_minute for p in t.phases if p.phase == "Sense")
    go(at_minute(sense_end - 15).index)
    pending_text = [i.value for i in app.info]
    everything_shown = " ".join([m.value for m in app.markdown] + pending_text + [e.value for e in app.caption])
    record(any("Not known yet" in x for x in pending_text) and not app.success and not app.warning
           and not (f"{t.dissolution_pct:.1f}%" in everything_shown and f"{t.hardness_kp:.2f}" in everything_shown),
           "Fifteen minutes before trial 10's test finishes the page says the result is not known yet, and its numbers appear nowhere on the page")
    go(at_minute(sense_end).index)
    shown = [e.value for e in list(app.success) + list(app.warning)]
    record(any(f"{t.dissolution_pct:.1f}%" in x and f"{t.hardness_kp:.2f} kP" in x for x in shown),
           "The moment the test finishes, the result appears with its numbers and verdict")

    first_staffed = next(b for b in run.calendar if b.staffed)
    page = go(at_minute(first_staffed.start_minute).index)
    record("lab-in" in page and "Someone is in the lab" in page, "When staff arrive on Monday the page says someone is in the lab")
    page = go(0)
    record("lab-out" in page and "Nobody is in the lab" in page, "At the start of the run it says nobody is in the lab")

    # other pages
    handovers = [s.value for s in app.subheader if "While the lab was empty" in s.value]
    record(len(handovers) == len(run.handovers) and not app.exception, "The overnight page shows every handover summary", f"{len(handovers)} summaries")
    log_frames = [d.value for d in app.dataframe if "Event" in list(d.value.columns)]
    record(bool(log_frames) and len(log_frames[0]) == len(run.events), "The event log table has every event", f"{len(run.events)} rows")

    comp = [d.value for d in app.dataframe if "Half had by trial (median)" in list(d.value.columns)]
    record(bool(comp) and len(comp[0]) == 3 and any("Headline measure" in m.value for m in app.markdown),
           "The comparison page shows the headline measure and a three-strategy table")
    diff = [d.value for d in app.dataframe if "Difficulty" in list(d.value.columns)]
    record(bool(diff) and len(diff[0]) == 9 and run.about is not None and run.about.comparison_note in [i.value for i in app.info],
           "The difficulty table (3 levels x 3 strategies) and the plain-language note about the advantage shrinking are shown",
           run.about.comparison_note[:110] + "...")
    leads = [d.value for d in app.dataframe if "Measured against" in list(d.value.columns)]
    found = {r.level: {s.label: s.found_pct for s in r.strategies} for r in run.comparison.difficulty}
    expect_ok = bool(leads) and len(leads[0]) == 3
    for _, line in (leads[0].iterrows() if leads else []):
        pct = found[line["Difficulty"]]
        best = max(v for k, v in pct.items() if k != "Adaptive")
        winners = sorted(k for k, v in pct.items() if k != "Adaptive" and v == best)
        expect_ok &= (sorted(line["Measured against"].split(" and ")) == winners
                      and line["Adaptive's lead (percentage points)"] == f"{pct['Adaptive'] - best:+.0f}")
    note = run.about.comparison_note
    record(expect_ok and "Fixed list" in note and "Random" in note and "measured against" in note,
           "Next to each percentage-point gap the page names the baseline it is measured against (in a table and in the plain-language note)",
           "; ".join(f"{r.level}: {r.lead_text}" for r in run.comparison.difficulty))
    app.radio[0].set_value("With the scripted faults applied to every strategy").run()
    record(not app.exception and any("Scripted faults were applied" in m.value or "scripted faults" in m.value.lower() for m in app.markdown),
           "Switching the comparison to 'with faults' works and says faults were applied")

    # throughput: the one calculation
    default_multiple = f"{run.summary.speedup_vs_manual:.1f}x manual"
    record(any(m.value == default_multiple for m in app.metric),
           "Throughput, at the default baseline of 9: the multiple shown equals the simulator's own figure",
           default_multiple)
    app.number_input[0].set_value(12.0).run()
    expected_multiple = f"{run.summary.trials_per_week / 12.0:.1f}x manual"
    record(any(m.value == expected_multiple for m in app.metric) and not app.exception,
           "Editing the manual baseline to 12 recalculates the multiple (autonomous trials per week divided by 12)",
           f"{run.summary.trials_per_week:g} / 12 -> {expected_multiple}")

    about_text = " ".join(m.value for m in app.markdown)
    record(run.about is not None and all(line[:60] in about_text for line in run.about.does_not_show)
           and all(line[:60] in about_text for line in run.about.shows),
           "'What this shows' lists everything the run record says it shows and does not show")
    record("about 29 to 30 trials" in about_text or re.search(r"about \d+ to \d+ trials", about_text) is not None,
           "The trial count is always written as a range ('about 29 to 30 trials'), never a bare figure",
           re.search(r"about \d+ to \d+ trials", about_text).group(0) if re.search(r"about \d+ to \d+ trials", about_text) else "")
    record("margin" in about_text, "The Limitations include the note that the count depends on a small timing margin")
    charts = [e for e in app.get("arrow_vega_lite_chart")] + [e for e in app.get("vega_lite_chart")]
    record(len(charts) >= 6, "The charts are drawn (timeline x3, comparison x2, throughput x1)", f"{len(charts)} charts")


def check_friendly_errors():
    """If the record is missing or out of date, the dashboard must say so plainly, not crash."""
    from streamlit.testing.v1 import AppTest

    broken = OUT / "_broken_record"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "record.json").write_text('{"meta": {"run_id": "old"}}', encoding="utf-8")
    results = {}
    for name, target in (("damaged", broken), ("missing", OUT / "_no_such_folder")):
        os.environ["CELLPOC_RECORD"] = str(target)
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        app.run()
        results[name] = (not app.exception, " ".join(w.value for w in app.warning),
                         any('<div class="sim-banner">' in m.value for m in app.markdown))
    os.environ.pop("CELLPOC_RECORD", None)
    record(results["damaged"][0] and "out of date" in results["damaged"][1] and "build_demo.bat" in results["damaged"][1]
           and results["damaged"][2],
           "A damaged or out-of-date run record gives a plain message telling you to run build_demo.bat (and the banner still shows), not a crash")
    record(results["missing"][0] and "no run record" in results["missing"][1].lower() and "build_demo.bat" in results["missing"][1]
           and results["missing"][2],
           "A missing run record gives a plain message telling you to run build_demo.bat (and the banner still shows), not a crash")


# ------------------------------------------------------------------ the real server
def check_server():
    port = 8766
    env = dict(os.environ, CELLPOC_RECORD=str(DEMO_FOLDER))
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port),
                             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://localhost:{port}"
    try:
        healthy = False
        for _ in range(60):
            try:
                healthy = urllib.request.urlopen(f"{base}/_stcore/health", timeout=2).read().decode().strip() == "ok"
                if healthy:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        record(healthy, "The real dashboard server starts on this computer and reports healthy")
        if not healthy:
            return
        page = urllib.request.urlopen(base, timeout=10).read().decode("utf-8")
        record(not external_references(page), "The page the server sends contains nothing fetched from the internet",
               f"{len(page)} bytes checked")
        font = urllib.request.urlopen(f"{base}/app/static/OpenSans.ttf", timeout=10)
        data = font.read()
        record(font.status == 200 and len(data) > 100_000 and data[:4] == b"\x00\x01\x00\x00",
               "The Open Sans font is served from this computer (so it shows even with no internet)", f"{len(data) // 1024} KB")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


# ------------------------------------------------------------------ source rules
def check_sources():
    architecture.check(checklist)
    problems, count = architecture.dashboard_problems()
    probe = ROOT / "cellpoc" / "dashboard" / "_probe_violation.py"
    try:
        probe.write_text("import math\nx = 3 * 4\ny = sum([1, 2])\nz = [a for a in [1] if a]\nbase = 'https://example.com'\n", encoding="utf-8")
        planted, _ = architecture.dashboard_problems()
    finally:
        probe.unlink(missing_ok=True)
    record(len(planted) >= 5, "The no-logic guard really works: a deliberately bad file (arithmetic, sum, filtering, math, a web address) is caught",
           f"{len(planted)} problems flagged")
    leaker = ROOT / "cellpoc" / "dashboard" / "_probe_import.py"
    try:
        leaker.write_text("from cellpoc.virtual_lab import VirtualLab\nfrom cellpoc.decision_engine import AdaptiveStrategy\n", encoding="utf-8")
        from checks.common import Checklist as _C
        probe_list = _C("probe")
        architecture.check(probe_list)
        caught = probe_list.rows[0][0] == "FAIL"
    finally:
        leaker.unlink(missing_ok=True)
    record(caught, "The import guard really works: a dashboard file that imports the lab or the engine is caught")

    style = (ROOT / "cellpoc" / "dashboard" / "style.py").read_text(encoding="utf-8")
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    record("#86BC25" in style and "#86BC25" in config and "'Open Sans', Arial" in style and "gatherUsageStats = false" in config,
           "Deloitte green (#86BC25) and the Open Sans-then-Arial font stack are set; usage reporting to the internet is off")
    record((ROOT / "static" / "OpenSans.ttf").exists() and (ROOT / "static" / "OpenSans-OFL.txt").exists(),
           "The Open Sans font file and its licence are bundled in the project")


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as error:
        record(False, "The settings file loads without problems", "\n        ".join(error.problems))
        return checklist.print()

    print("Rebuilding the demonstration run record (about a minute)...", flush=True)
    run = run_full_demo(settings)
    path = run_store.save(run, DEMO_FOLDER)
    record(run_store.load(path) == run, "The demonstration run record (closed loop, both comparisons, difficulty table, notes) saved and read back identical",
           f"{path.relative_to(ROOT)}, {path.stat().st_size // 1024} KB")
    check_snapshots(settings, run)
    print("Driving the dashboard through its pages...", flush=True)
    check_dashboard_pages(settings, run)
    check_friendly_errors()
    check_server()
    check_sources()

    OUT.mkdir(parents=True, exist_ok=True)
    s = run.summary
    checklist.headline(f"Closed-loop run: {s.attempts_text}; {s.headline}")
    code = checklist.print()
    return code


if __name__ == "__main__":
    sys.exit(main())
