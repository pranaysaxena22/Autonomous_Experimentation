"""The run told as results a client cares about, worked out in advance from the saved run record and written next to it as client_story.json.

The dashboard's Results page and the Overview's headline cards only display this file (they calculate nothing). Every number here is counted or converted from the run record's own fields, and each is labelled as illustrative:
the run is a simulation with made-up values. Where a comparison needs an assumption (what a person working by hand would manage) the assumption is the manual baseline from the run record, named as such.
"""
from __future__ import annotations

STORY_FILE = "client_story.json"
LABEL = "ILLUSTRATIVE results of a simulated run: made-up values, not a result about real tablets."
START_PREFIX = "Spread-out starting recipe"            # how the engine words the recipes it places evenly before it starts choosing


def _target_text(constraint: dict) -> str:
    unit = f" {constraint['unit']}" if constraint.get("unit") and constraint["unit"] != "%" else (constraint.get("unit") or "")
    goal = constraint.get("goal")
    if goal == "at_least":
        return f"at least {constraint['value']:g}{unit}"
    if goal == "at_most":
        return f"at most {constraint['value']:g}{unit}"
    if goal == "between":
        return f"between {constraint['low']:g} and {constraint['high']:g}{unit}"
    return ""


def build(record: dict, setup: dict | None = None) -> dict:
    """The story for one run record (as saved, a dictionary) and, when known, the setup that made it."""
    summary, trials, meta = record["summary"], record["trials"], record["meta"]
    run_hours = summary["run_hours"]
    manual = summary["manual_baseline_trials_per_week"]
    attempted = len(trials)
    started = [t for t in trials if str(t["reason"]).startswith(START_PREFIX)]
    chosen = [t for t in trials if not str(t["reason"]).startswith(START_PREFIX)]
    judged = lambda group: [t for t in group if t["status"] == "Completed"]
    story = {
        "format_version": 1,
        "label": LABEL,
        "run_name": setup["project"]["name"] if setup and setup.get("project") else meta["run_id"],
        "run_hours": run_hours,
        "run_days": run_hours / 24,
        "unattended_hours": summary["unattended_hours"],
        "staffed_hours": run_hours - summary["unattended_hours"],
        "unattended_share_pct": 100 * summary["unattended_hours"] / run_hours if run_hours else 0,
        "trials_attempted": attempted,
        "trials_with_result": summary["trials_with_result"],
        "trials_good": summary["trials_good"],
        "trials_skipped": summary["trials_skipped"],
        "trials_started_unattended": summary["trials_started_unattended"],
        "trials_per_week": summary["trials_per_week"],
        "manual_per_week": manual,
        "multiple": summary["speedup_vs_manual"],
        "faults_recovered": summary["faults_recovered"],
        "alerts_for_staff": summary["alerts_for_staff"],
        "good_share_pct": 100 * summary["trials_good"] / summary["trials_with_result"] if summary["trials_with_result"] else 0,
        "first_good": None,
        "starting": {"count": len(started), "with_result": len(judged(started)), "good": sum(1 for t in started if t["outcome"] == "Good")} if started and chosen else None,
        "chosen": {"count": len(chosen), "with_result": len(judged(chosen)), "good": sum(1 for t in chosen if t["outcome"] == "Good")} if started and chosen else None,
        "targets": [{"label": c["label"], "response": c["response"], "goal": c["goal"], "value": c.get("value"), "low": c.get("low"), "high": c.get("high"), "unit": c.get("unit"), "text": _target_text(c), "required": c.get("required", True)}
                    for c in (setup or {}).get("targets", {}).get("constraints", [])],
        "starting_trials": len(started),
        "learning": [],
        "space": [],
        "week": {"windows": [], "trials": []},
        "events": [],
        "handovers": [{"title": h["title"], "text": h["text"]} for h in record.get("handovers", [])],
    }
    first = summary.get("first_good_trial")
    if first:
        trial = next(t for t in trials if t["trial"] == first)
        hours = trial["end_minute"] / 60
        story["first_good"] = {"trial": first, "hours": hours, "manual_hours": first / manual * 7 * 24 if manual else None}
    good_so_far = 0
    for t in trials:
        good_so_far += 1 if t["outcome"] == "Good" else 0
        story["learning"].append({"trial": t["trial"], "dissolution": t["dissolution_pct"], "hardness": t["hardness_kp"], "outcome": t["outcome"], "good_so_far": good_so_far,
                                  "chosen_by": "Placed evenly at the start" if str(t["reason"]).startswith(START_PREFIX) else "Chosen by the engine from the results so far", "hours": t["end_minute"] / 60, "day": t["end_minute"] / 1440})
        story["space"].append({"trial": t["trial"], "drug": t["recipe"].get("drug"), "filler": t["recipe"].get("filler"), "outcome": t["outcome"]})
        story["week"]["trials"].append({"trial": t["trial"], "start_h": t["start_minute"] / 60, "end_h": t["end_minute"] / 60, "start_d": t["start_minute"] / 1440, "end_d": t["end_minute"] / 1440, "outcome": t["outcome"]})
    for w in record["calendar"]:
        story["week"]["windows"].append({"start_h": w["start_minute"] / 60, "end_h": w["end_minute"] / 60, "start_d": w["start_minute"] / 1440, "end_d": w["end_minute"] / 1440, "staffed": w["staffed"], "label": w["label"], "from": w["start"], "to": w["end"]})
    for a in record["alerts"]:
        story["events"].append({"when": a["when"], "title": a["title"], "text": a["message"], "needs_human": a["needs_human"], "queued_for": a["queued_for"]})
    return story
