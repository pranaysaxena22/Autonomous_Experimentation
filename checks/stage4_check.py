"""Stage 4 health check: the closed-loop unattended run, with scripted faults.

One run of the cell: the adaptive engine, the whole 120-hour window, trial 8 recovering from a
binder-dispenser clog, trial 19 failing its retry and being skipped. Prints a PASS/FAIL list and
writes files you can open in runs/stage4/:
  timeline.html           every step, fault, purge and retry on the clock; plus Sense/Reason/Act/Adapt per trial
  closed_loop_summary.txt the run in words: attempts, results, alerts, what happened overnight
  event_log.csv           the full event log
  trials.csv              one row per trial: recipe, status, result, why-text, notes
  alerts.csv              the alerts
  record.json             the run record the dashboard will read
"""
from __future__ import annotations

import csv
import dataclasses
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.contracts import Formulation  # noqa: E402
from cellpoc.runner import run_closed_loop  # noqa: E402
from cellpoc.settings import SettingsError, load_settings  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, external_references, write_chart_page  # noqa: E402

OUT = ROOT / "runs" / "stage4"
FMT = "%Y-%m-%d %H:%M"
checklist = Checklist("STAGE 4 CHECK - closed-loop unattended run with scripted faults")
record = checklist.record


# ------------------------------------------------------------------ separate arithmetic from the settings
def staffed_at(settings, moment: datetime) -> bool:
    p = settings.people
    return moment.weekday() in p.staffed_weekdays and p.staffed_from <= moment.time() < p.staffed_until


def expected_schedule(settings):
    """(trial, start, end, skipped) for every trial that fits, worked out from the settings alone."""
    faults = {e.trial: e for e in settings.scripted_faults.events}
    purge = settings.scripted_faults.purge_minutes
    dur = {s.name: s.duration_minutes for s in settings.cell.steps}
    order = [s.name for s in settings.cell.steps]
    nominal = sum(dur.values())
    end_of_run = settings.run.duration_hours * 60
    schedule, t, n = [], 0.0, 1
    while True:
        f = faults.get(n)
        if f is None:
            length, skipped = nominal, False
        elif f.retry_succeeds:
            length, skipped = nominal + purge + dur[f.station], False
        else:
            length = sum(dur[x] for x in order[:order.index(f.station)]) + 2 * dur[f.station] + purge
            if settings.scripted_faults.clean_after_skip:
                length += dur[settings.cell.phases.reason_adapt_step]   # the cleaning step still follows a skipped candidate
            skipped = True
        if t + length > end_of_run:
            return schedule
        schedule.append((n, t, t + length, skipped))
        t += length
        n += 1


def independent_arrival_after(settings, minute: float):
    """First moment after `minute` when staff arrive, found by stepping through the clock."""
    for later in range(int(minute) + 1, int(settings.run.duration_hours * 60) + 1):
        now = settings.run.start + timedelta(minutes=later)
        before = settings.run.start + timedelta(minutes=later - 1)
        if staffed_at(settings, now) and not staffed_at(settings, before):
            return later
    return None


# ------------------------------------------------------------------ the checks
def check_counts_and_timing(settings, run):
    s, sched = run.summary, expected_schedule(settings)
    skipped_expected = [n for n, _, _, sk in sched if sk]
    t = run.trials
    record(len(t) == len(sched) == s.trials_attempted,
           "The number of trials attempted is exactly how many fit in the 120 hours given the fault delays (worked out separately from the settings)",
           s.attempts_text)
    record(s.trials_with_result + s.trials_skipped == s.trials_attempted
           and s.trials_with_result == sum(x.status == "Completed" for x in t)
           and s.trials_skipped == sum(x.status == "Skipped" for x in t),
           "Attempted = completed with a result + skipped, and the totals match the trial list", s.attempts_text)
    record([x.trial for x in t if x.status == "Skipped"] == skipped_expected == [19],
           "Only trial 19 is skipped", f"skipped: {[x.trial for x in t if x.status == 'Skipped']}")
    record(all((x.start_minute, x.end_minute) == (a, b) for x, (_, a, b, _) in zip(t, sched)),
           "Every trial starts and ends at the minute the settings predict, delays included",
           f"trial 8 takes {t[7].end_minute - t[7].start_minute:g} min, trial 19 takes {t[18].end_minute - t[18].start_minute:g} min, others {t[0].end_minute - t[0].start_minute:g} min")
    last_end = max(x.end_minute for x in t)
    record(last_end <= run.meta.duration_minutes, "No trial runs past the end of the run",
           f"last trial ends {run.meta.duration_minutes - last_end:g} minutes before the run window closes")

    skipped = t[18]
    record(skipped.status == "Skipped" and skipped.dissolution_pct is None and skipped.hardness_kp is None
           and skipped.outcome == "No result" and skipped.margin is None,
           "The skipped trial (19) has no result: no dissolution, no hardness, no verdict")
    record(all(x.status == "Completed" and x.dissolution_pct is not None for x in t[19:]) and len(t) > 19,
           "Later trials still happen after the skip, each with a result", f"trials {t[19].trial} to {t[-1].trial}")
    record(t[7].status == "Completed" and t[7].dissolution_pct is not None,
           "Trial 8, which hit the same fault but recovered, has a normal result")
    after = t[19]
    record(after.recipe != skipped.recipe, "The recipe of the skipped candidate is not tried again straight away",
           f"trial 20's recipe differs from trial 19's")
    record(all(x.good_so_far == sum(y.outcome == "Good" for y in t[:i + 1]) for i, x in enumerate(t)),
           "The 'good recipes found so far' running count is correct trial by trial")


def check_no_double_booking(run):
    intervals = sorted((i.start_minute, i.end_minute, i.step, x.trial, i.label) for x in run.trials for i in x.steps)
    record(all(b[0] >= a[1] for a, b in zip(intervals, intervals[1:])),
           "Only one thing happens at a time, including the failed attempts, purges and retries",
           f"{len(intervals)} stretches of work checked")
    clashes = []
    for station in {i[2] for i in intervals}:
        mine = [i for i in intervals if i[2] == station]
        clashes += [(a, b) for a, b in zip(mine, mine[1:]) if b[0] < a[1]]
    record(not clashes, "No station is ever double-booked, even after the fault delays")
    times = [e.minute for e in run.events]
    record(times == sorted(times), "The event log is in time order", f"{len(run.events)} events")
    kinds8 = [i.kind for i in run.trials[7].steps if i.step == "dispense"]
    kinds19 = [i.kind for i in run.trials[18].steps if i.step == "dispense"]
    record(kinds8 == ["failed_attempt", "purge", "retry"] and kinds19 == ["failed_attempt", "purge", "retry"],
           "Both faulty trials show the same sequence at the dispenser: failed attempt, purge, retry",
           f"trial 8: {' > '.join(kinds8)}; trial 19: {' > '.join(kinds19)}")


def check_phases(settings, run):
    cfg = settings.cell.phases
    dur = {s.name: s.duration_minutes for s in settings.cell.steps}
    ok_shape, ok_times, ok_cover = True, True, True
    for x in run.trials:
        if x.status != "Completed":
            continue
        names = [p.phase for p in x.phases]
        ok_shape &= names == ["Act", "Sense", "Reason", "Adapt"]
        by = {p.phase: p for p in x.phases}
        sense_len = sum(dur[n] for n in cfg.sense)
        ok_times &= (by["Sense"].end_minute - by["Sense"].start_minute == sense_len
                     and by["Reason"].end_minute - by["Reason"].start_minute == cfg.reason_minutes
                     and by["Adapt"].end_minute - by["Adapt"].start_minute == dur[cfg.reason_adapt_step] - cfg.reason_minutes)
        ok_cover &= (by["Act"].start_minute == x.start_minute and by["Adapt"].end_minute == x.end_minute
                     and all(a.end_minute == b.start_minute for a, b in zip(x.phases, x.phases[1:])))
    record(ok_shape, "Every completed trial has the four phases in order: Act, Sense, Reason, Adapt")
    record(ok_times, f"Sense is the test ({dur['test']:g} min); Reason is the first {cfg.reason_minutes:g} min of cleaning; Adapt is the rest",
           f"Adapt = {dur[cfg.reason_adapt_step] - cfg.reason_minutes:g} min")
    record(ok_cover, "The four phases run back to back and together cover the whole trial, with no gaps")
    act_normal = run.trials[0].phases[0]
    act_8 = run.trials[7].phases[0]
    expected_act = sum(dur[n] for n in cfg.act)
    record(act_normal.end_minute - act_normal.start_minute == expected_act
           and act_8.end_minute - act_8.start_minute == expected_act + settings.scripted_faults.purge_minutes + dur["dispense"],
           "Act is dispense + blend + press; on trial 8 it is longer by the purge and the retry",
           f"normal {expected_act:g} min; trial 8 {act_8.end_minute - act_8.start_minute:g} min")
    skipped = run.trials[18]
    expected_phases = ["Act", "Reason", "Adapt"] if settings.scripted_faults.clean_after_skip else ["Act"]
    record([p.phase for p in skipped.phases] == expected_phases and skipped.phases[0].status == "failed",
           "The skipped trial shows an Act phase marked failed, then Reason and Adapt during the cleaning that follows"
           if settings.scripted_faults.clean_after_skip else "The skipped trial shows only an Act phase, marked failed",
           " > ".join(p.phase for p in skipped.phases))
    if settings.scripted_faults.clean_after_skip:
        by = {p.phase: p for p in skipped.phases}
        record(by["Reason"].end_minute - by["Reason"].start_minute == cfg.reason_minutes
               and by["Reason"].start_minute == by["Act"].end_minute and by["Adapt"].end_minute == skipped.end_minute,
               "After the skip, cleaning follows at once: Reason is its first 30 minutes and Adapt the rest")
        record([i.step for i in skipped.steps] == ["dispense", "dispense", "dispense", "clean"],
               "The skipped trial's work is: failed attempt, purge, failed retry, then a full cleaning step",
               " > ".join(i.label for i in skipped.steps))
    record(all(p.description and len(p.description) > 20 for x in run.trials for p in x.phases),
           "Every phase carries a plain-language description the dashboard can show as it is")


def check_alerts(settings, run):
    ev = [(e.kind, e.trial) for e in run.events]
    for kind in ("fault", "recovery"):
        record((kind, 8) in ev, f"Trial 8 logs a {kind}")
    t8 = [e.kind for e in run.events if e.trial == 8 and e.kind in ("fault", "recovery", "retry_failed", "candidate_skipped", "alert_queued")]
    record(t8 == ["fault", "recovery"], "Trial 8 logs a fault then a recovery, and nothing else",
           " > ".join(t8))
    t19 = [e.kind for e in run.events if e.trial == 19 and e.kind in ("fault", "recovery", "retry_failed", "candidate_skipped", "alert_queued")]
    record(t19 == ["fault", "retry_failed", "candidate_skipped", "alert_queued"],
           "Trial 19 logs the fault, the failed retry, the skipped candidate and a queued alert, in that order",
           " > ".join(t19))
    a8, a19 = [a for a in run.alerts if a.trial == 8], [a for a in run.alerts if a.trial == 19]
    record(len(a8) == 1 and not a8[0].needs_human and a8[0].queued_for is None and a8[0].severity == "Recovered",
           "Trial 8's alert says it recovered and needs nobody")
    # the moment the retry fails = start of trial 19 + the steps before the faulty one + attempt + purge + retry
    dur = {s.name: s.duration_minutes for s in settings.cell.steps}
    order = [s.name for s in settings.cell.steps]
    fault19 = settings.scripted_faults.events[1]
    start19 = [a for n, a, _, _ in expected_schedule(settings) if n == 19][0]
    skip_minute = (start19 + sum(dur[x] for x in order[:order.index(fault19.station)]) + 2 * dur[fault19.station]
                   + settings.scripted_faults.purge_minutes)
    arrives = independent_arrival_after(settings, skip_minute)
    expected_when = (settings.run.start + timedelta(minutes=arrives)).strftime("%a %d %b %H:%M") if arrives else None
    record(len(a19) == 1 and a19[0].needs_human and a19[0].queued_for == expected_when,
           "Trial 19's alert is queued for the next working day: the first moment staff arrive after it happened",
           f"alert at {a19[0].when if a19 else '?'}, queued for {a19[0].queued_for if a19 else '?'} (separately worked out: {expected_when})")
    record(a19 and staffed_at(settings, datetime.strptime(run.meta.start, FMT) + timedelta(minutes=arrives)),
           "That queued time really is a moment when the lab is staffed")
    messages = {e.kind: e.message for e in run.events if e.trial == 19}
    record(settings.scripted_faults.events[1].alert in messages.get("alert_queued", ""),
           "The queued alert carries the alert text from the settings")
    unattended = [e for e in run.events if e.kind in ("fault", "alert_queued") and e.trial == 19]
    record(all(not e.attended for e in unattended), "Trial 19's fault happens while nobody is in the lab (the point of the scenario)")


def check_trial_fields(settings, run):
    lab = VirtualLab(settings)
    ok_fields, ok_results = True, True
    for x in run.trials:
        ok_fields &= (set(x.recipe) == {i.key for i in settings.design_space.ingredients}
                      and all(i.min <= x.recipe[i.key] <= i.max for i in settings.design_space.ingredients)
                      and len(x.reason) > 40 and x.status in ("Completed", "Skipped") and x.outcome in ("Good", "Not good", "No result"))
        if x.status == "Completed":
            m = lab.measure(x.trial, Formulation(**x.recipe))
            ok_results &= (m.dissolution_pct == x.dissolution_pct and m.hardness_kp == x.hardness_kp)
    record(ok_fields, "Every trial carries its recipe (inside the ranges), a why-text, a status and an outcome")
    record(ok_results, "Every result is exactly what the lab reports for that recipe and trial number")
    record(all(x.notes for x in run.trials if x.trial in (8, 19)) and not any(x.notes for x in run.trials if x.trial not in (8, 19)),
           "Only the two faulty trials carry fault notes")


def check_overnight(settings, run):
    start = settings.run.start
    blocks, begin, minutes = [], None, int(settings.run.duration_hours * 60)
    for m in range(minutes + 1):
        unattended = m < minutes and not staffed_at(settings, start + timedelta(minutes=m))
        if unattended and begin is None:
            begin = m
        if not unattended and begin is not None:
            blocks.append((begin, m))
            begin = None
    record([(h.start_minute, h.end_minute) for h in run.handovers] == blocks,
           "There is one 'what happened overnight' summary for every stretch when nobody was in the lab",
           f"{len(blocks)} stretches, found separately from the settings")
    ok = True
    for h in run.handovers:
        finished = [x for x in run.trials if h.start_minute < x.end_minute <= h.end_minute]
        ok &= (h.trials_with_result == sum(x.status == "Completed" for x in finished)
               and h.trials_skipped == sum(x.status == "Skipped" for x in finished)
               and h.trials_good == sum(x.outcome == "Good" for x in finished)
               and h.trials_started == sum(1 for x in run.trials if h.start_minute <= x.start_minute < h.end_minute))
    record(ok, "Each summary's counts match a fresh count of the trials in that stretch")
    middle = run.handovers[1]
    record("skipped" in middle.text and "Needs your attention" in middle.text and middle.alerts_for_staff == 1,
           "The overnight summary containing trial 19 mentions the skipped candidate and the alert waiting for staff")
    record(all(len(h.text) > 100 and h.title for h in run.handovers), "Every summary is ready-made text with a title")


def check_reproducible(settings, run):
    again = run_closed_loop(settings, run_id=run.meta.run_id)
    record(again == run, "The same seed gives an identical run record, every number and every word")
    other = run_closed_loop(dataclasses.replace(settings, run=dataclasses.replace(settings.run, random_seed=settings.run.random_seed + 1)),
                            run_id=run.meta.run_id)
    record(other != run, "A different seed gives a different run")


def check_what_ifs(settings, run):
    base = settings.scripted_faults
    slower = dataclasses.replace(settings, scripted_faults=dataclasses.replace(base, purge_minutes=90))
    r = run_closed_loop(slower)
    expected = len(expected_schedule(slower))
    record(r.summary.trials_attempted == expected and "not started" in r.events[-1].message,
           "What-if: with a 90-minute purge the count changes to what fits, and the log says why. Nothing forces a particular number",
           f"{r.summary.attempts_text} (separately worked out: {expected} fit)")
    flipped = dataclasses.replace(settings, scripted_faults=dataclasses.replace(base, clean_after_skip=not base.clean_after_skip))
    r_flip = run_closed_loop(flipped)
    record(r_flip.summary.trials_attempted == len(expected_schedule(flipped))
           and r_flip.summary.trials_attempted != run.summary.trials_attempted,
           f"What-if: with cleaning after the skip switched {'off' if base.clean_after_skip else 'on'}, the trial count changes",
           f"{run.summary.attempts_text} -> {r_flip.summary.attempts_text}")
    nofaults = dataclasses.replace(settings, scripted_faults=dataclasses.replace(base, events=()))
    r2 = run_closed_loop(nofaults)
    record(r2.summary.trials_attempted == len(expected_schedule(nofaults)) and r2.summary.trials_skipped == 0 and not r2.alerts,
           "What-if: with no faults at all the same engine fits the full 120 hours with no skips and no alerts", r2.summary.attempts_text)
    record(run.comparison is None, "The closed-loop run is separate from the 40-campaign comparison (it carries no comparison)")


# ------------------------------------------------------------------ outputs
def write_outputs(settings, run):
    OUT.mkdir(parents=True, exist_ok=True)
    path = run_store.save(run, OUT)
    record(run_store.load(path) == run, "The run record saved to disk reads back identical", str(path.relative_to(ROOT)))
    labels = run.ingredient_labels

    with open(OUT / "event_log.csv", "w", newline="", encoding="utf-8-sig") as handle:
        w = csv.writer(handle)
        w.writerow(["When", "Kind", "Trial", "Station", "Someone in the lab?", "Event"])
        for e in run.events:
            w.writerow([e.when, e.kind, e.trial or "", e.station or "", "yes" if e.attended else "no", e.message])
    with open(OUT / "trials.csv", "w", newline="", encoding="utf-8-sig") as handle:
        w = csv.writer(handle)
        w.writerow(["Trial", "Status", "Started", "Finished"] + [f"{v} %" for v in labels.values()]
                   + ["Dissolution %", "Hardness kP", "Outcome", "Why this recipe", "Notes"])
        for x in run.trials:
            w.writerow([x.trial, x.status, x.start, x.end] + [round(x.recipe[k], 2) for k in labels]
                       + ["" if x.dissolution_pct is None else round(x.dissolution_pct, 1),
                          "" if x.hardness_kp is None else round(x.hardness_kp, 2), x.outcome, x.reason, " ".join(x.notes)])
    with open(OUT / "alerts.csv", "w", newline="", encoding="utf-8-sig") as handle:
        w = csv.writer(handle)
        w.writerow(["When", "Trial", "Severity", "Title", "Message", "Needs a person?", "Queued for"])
        for a in run.alerts:
            w.writerow([a.when, a.trial, a.severity, a.title, a.message, "yes" if a.needs_human else "no", a.queued_for or ""])

    s = run.summary
    spare = run.meta.duration_minutes - max(x.end_minute for x in run.trials)
    lines = ["CLOSED-LOOP RUN: adaptive engine, whole run window, scripted faults applied", "=" * 70,
             f"Trials: {s.attempts_text}", f"Good recipes found: {s.trials_good} (first at trial {s.first_good_trial})",
             f"Throughput: {s.headline}",
             f"Unattended for {s.unattended_hours:g} of {s.run_hours:g} hours; {s.trials_started_unattended} of {s.trials_attempted} trials started with nobody in the lab",
             f"Faults recovered on their own: {s.faults_recovered}; alerts waiting for staff: {s.alerts_for_staff}",
             f"The last trial finished {spare:g} minutes before the run window closed.", "", "ALERTS", "-" * 70]
    lines += [f"{a.when}  [{a.severity}]  {a.message}" + (f"  (queued for {a.queued_for})" if a.queued_for else "") for a in run.alerts]
    lines += ["", "WHAT HAPPENED WHILE NOBODY WAS IN THE LAB", "-" * 70]
    for h in run.handovers:
        lines += [h.title, h.text, ""]
    (OUT / "closed_loop_summary.txt").write_text("\n".join(lines), encoding="utf-8")

    import altair as alt
    import pandas as pd

    green, grey, font = settings.display.accent_colour, "#9AA5B1", settings.display.font
    rows = []
    for x in run.trials:
        for i in x.steps:
            look = {"failed_attempt": "Failed attempt (fault)", "purge": "Purge", "retry": "Retry"}.get(i.kind)
            if i.kind == "retry" and i.outcome == "failed":
                look = "Retry failed - candidate skipped"
            rows.append({"Station": i.step.capitalize(), "Stage": i.label, "Trial": x.trial, "Start": i.start, "End": i.end,
                         "Look": look or ("Trial measured good" if x.outcome == "Good" else "Trial measured not good")})
    looks = ["Trial measured good", "Trial measured not good", "Failed attempt (fault)", "Purge", "Retry", "Retry failed - candidate skipped"]
    palette = [green, grey, "#D0021B", "#F5A623", "#7B5C00", "#8B0000"]
    shade = pd.DataFrame([{"Start": b.start, "End": b.end, "State": b.label} for b in run.calendar])
    order = [st.label for st in run.steps]
    for r in rows:
        r["Station"] = next(st.label for st in run.steps if st.name.capitalize() == r["Station"])
    background = alt.Chart(shade).mark_rect(opacity=0.35).encode(
        x=alt.X("Start:T", title="Date and time"), x2="End:T",
        color=alt.Color("State:N", scale=alt.Scale(domain=["Unattended", "Staffed"], range=["#D5D9DE", "#FFFFFF"]), legend=alt.Legend(title="Lab")))
    bars = alt.Chart(pd.DataFrame(rows)).mark_bar(height=18).encode(
        x="Start:T", x2="End:T", y=alt.Y("Station:N", sort=order, title=None),
        color=alt.Color("Look:N", scale=alt.Scale(domain=looks, range=palette), legend=alt.Legend(title="What happened")),
        tooltip=["Trial", "Stage", "Start", "End", "Look"])
    timeline = (background + bars).properties(width=1000, height=210, title="Every step, fault, purge and retry. Grey background = nobody in the lab")

    phase_rows = [{"Phase": p.phase, "Trial": x.trial, "Start": p.start, "End": p.end, "What it did": p.description}
                  for x in run.trials for p in x.phases]
    phases = alt.Chart(pd.DataFrame(phase_rows)).mark_bar(height=16).encode(
        x=alt.X("Start:T", title="Date and time"), x2="End:T", y=alt.Y("Phase:N", sort=["Sense", "Reason", "Act", "Adapt"], title=None),
        color=alt.Color("Phase:N", scale=alt.Scale(domain=["Sense", "Reason", "Act", "Adapt"], range=["#0097A9", "#005587", green, "#C4D600"])),
        tooltip=["Trial", "Phase", "Start", "End", "What it did"]).properties(
        width=1000, height=150, title="Sense / Reason / Act / Adapt for every trial (hover for what each did)")
    chart = alt.vconcat(timeline, phases).configure(font=font).configure_title(font=font, color="#333", fontSize=14)
    write_chart_page(chart, OUT / "timeline.html", settings.display.banner, green, font)
    record(all((OUT / f).exists() for f in ("timeline.html", "event_log.csv", "trials.csv", "alerts.csv", "closed_loop_summary.txt")),
           "The timeline, summary, event log, trials and alerts files were written", str(OUT.relative_to(ROOT)))


def check_offline():
    pages = sorted((ROOT / "runs").rglob("*.html"))
    stale = {p.relative_to(ROOT).as_posix(): external_references(p.read_text(encoding="utf-8")) for p in pages}
    bad = {k: v for k, v in stale.items() if v}
    record(bool(pages) and not bad, "Every generated chart page works with no internet (the chart library is bundled inside each file)",
           (f"{len(pages)} pages checked" if not bad else f"still need the internet: {', '.join(bad)} - re-run that stage's check")
           + "; fonts fall back to Arial offline unless Open Sans is installed")


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as error:
        record(False, "The settings file loads without problems", "\n        ".join(error.problems))
        return checklist.print()

    run = run_closed_loop(settings, run_id="stage4-closed-loop")
    check_counts_and_timing(settings, run)
    check_no_double_booking(run)
    check_phases(settings, run)
    check_alerts(settings, run)
    check_trial_fields(settings, run)
    check_overnight(settings, run)
    check_reproducible(settings, run)
    check_what_ifs(settings, run)
    architecture.check(checklist)
    write_outputs(settings, run)
    check_offline()

    s = run.summary
    checklist.headline(f"Trials: {s.attempts_text}. Good recipes found: {s.trials_good}.")
    checklist.headline(s.headline)
    checklist.headline(f"{s.alerts_for_staff} alert waiting for staff; {s.faults_recovered} fault recovered unaided. Full text: runs\\stage4\\closed_loop_summary.txt")
    return checklist.print()


if __name__ == "__main__":
    sys.exit(main())
