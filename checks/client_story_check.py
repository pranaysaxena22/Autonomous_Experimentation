"""Health check for the client story: the run told as results a client cares about (the Results page and the Overview's headline cards).

In plain words it checks that: every number in the saved story (client_story.json) equals a number worked out again from the raw run record (the unattended hours added up from the calendar, the first good recipe and its time found from the trials, the early and the engine-chosen
recipes counted from their reasons, the good and skipped recipes recounted), with a planted wrong story proving the comparison can fail; the story is written next to every run that is saved (here two of the three examples, one with demanding targets), says it is illustrative, and carries
the setup's targets; the Results page draws its four headline cards and its five charts, says the illustrative sentence once, and says in plain words how to get its summary when a run has none; the Overview shows the same four cards for a platform run and none for the proof of concept's demo;
the manual comparison is named as an assumption wherever it is shown; the dashboard module and the new part contain no logic and the part imports nothing from the project. Nothing is written into the project.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import client_story  # noqa: E402
from cellpoc.platform_runner import load_inputs, run_setup, save_platform_run  # noqa: E402
from cellpoc.setup import example_choices  # noqa: E402
from checks import architecture  # noqa: E402
from checks.app_check import DEMO, PLATFORM, all_text, run_app, sentence_count  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402


def independent(record: dict) -> dict:
    """The story's numbers worked out again from the raw record, written out here separately from the part that makes the story."""
    trials, calendar, summary = record["trials"], record["calendar"], record["summary"]
    unattended = sum((w["end_minute"] - w["start_minute"]) for w in calendar if not w["staffed"]) / 60
    start = [t for t in trials if str(t["reason"]).startswith("Spread-out starting recipe")]
    chosen = [t for t in trials if not str(t["reason"]).startswith("Spread-out starting recipe")]
    good = [t for t in trials if t["outcome"] == "Good"]
    first = good[0] if good else None
    with_result = [t for t in trials if t["status"] == "Completed"]
    manual = summary["manual_baseline_trials_per_week"]
    return {"unattended_hours": unattended, "trials_attempted": len(trials), "trials_with_result": len(with_result), "trials_good": len(good), "trials_skipped": len([t for t in trials if t["status"] == "Skipped"]),
            "start_count": len(start), "start_good": len([t for t in start if t["outcome"] == "Good"]), "chosen_count": len(chosen), "chosen_good": len([t for t in chosen if t["outcome"] == "Good"]),
            "first_trial": first["trial"] if first else None, "first_hours": first["end_minute"] / 60 if first else None, "manual_hours": (first["trial"] / manual) * 168 if first else None,
            "good_share_pct": 100 * len(good) / len(with_result), "unattended_share_pct": 100 * unattended / (record["meta"]["duration_minutes"] / 60)}


def differences(story: dict, truth: dict) -> list[str]:
    """The names of the numbers in a story that differ from the recount."""
    mine = {"unattended_hours": story["unattended_hours"], "trials_attempted": story["trials_attempted"], "trials_with_result": story["trials_with_result"], "trials_good": story["trials_good"], "trials_skipped": story["trials_skipped"],
            "start_count": story["starting"]["count"] if story["starting"] else None, "start_good": story["starting"]["good"] if story["starting"] else None,
            "chosen_count": story["chosen"]["count"] if story["chosen"] else None, "chosen_good": story["chosen"]["good"] if story["chosen"] else None,
            "first_trial": story["first_good"]["trial"] if story["first_good"] else None, "first_hours": story["first_good"]["hours"] if story["first_good"] else None,
            "manual_hours": story["first_good"]["manual_hours"] if story["first_good"] else None, "good_share_pct": story["good_share_pct"], "unattended_share_pct": story["unattended_share_pct"]}
    return [k for k, v in truth.items() if v is None and mine[k] is not None or v is not None and (mine[k] is None or abs(mine[k] - v) > 1e-6)]


def main() -> int:
    cl = Checklist("CLIENT STORY: the run told as results a client cares about (the Results page and the Overview's headline cards)")
    before = project_files()

    record = json.loads((PLATFORM / "record.json").read_text(encoding="utf-8"))
    story = json.loads((PLATFORM / client_story.STORY_FILE).read_text(encoding="utf-8")) if (PLATFORM / client_story.STORY_FILE).exists() else {}
    truth = independent(record)
    wrong = differences(story, truth) if story else ["no story file next to the platform run (run run_app.bat or make_platform_demo.bat once)"]
    cl.record(not wrong, "Every number in the platform run's saved story equals a number worked out again from the raw run record (unattended hours added up from the calendar, first good recipe and its time, early and engine-chosen recipes counted from their reasons, good and skipped recounted)",
              f"wrong: {wrong or 'none'}; first good trial {truth['first_trial']} at {truth['first_hours']} h; start {truth['start_good']}/{truth['start_count']}, engine {truth['chosen_good']}/{truth['chosen_count']}")
    lying = copy.deepcopy(story)
    lying["trials_good"] += 1
    lying["unattended_hours"] += 5
    lying["first_good"]["hours"] = 3.0
    lying["chosen"]["good"] -= 2
    caught = differences(lying, truth)
    cl.record(sorted(caught) == sorted(["trials_good", "unattended_hours", "first_hours", "chosen_good"]) and not differences(story, truth),
              "Self-test: a story with one more good recipe, five more unattended hours, a made-up time to the first good recipe and two fewer engine-chosen good recipes is caught on exactly those four numbers, and the honest story is not flagged, so the comparison can fail", f"caught {sorted(caught)}")

    # ---------------------------------------------------------------- the story is written for every saved run
    with tempfile.TemporaryDirectory() as tmp:
        results = {}
        examples = example_choices()
        for index in (0, 2):
            label, path = examples[index]
            setup, layout, settings = load_inputs(path)
            run = run_setup(setup, layout, settings)
            folder = Path(tmp) / f"example_{index + 1}"
            save_platform_run(run, folder)
            file = folder / client_story.STORY_FILE
            saved = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
            recount = independent(json.loads((folder / "record.json").read_text(encoding="utf-8")))
            results[label[:9]] = (bool(saved), "ILLUSTRATIVE" in saved.get("label", ""), differences(saved, recount) if saved else ["missing"],
                                  [t["text"] for t in saved.get("targets", [])] == [client_story.story._target_text(c) for c in setup["targets"]["constraints"]], saved.get("trials_attempted") == len(run.executed))
    cl.record(all(v[0] and v[1] and not v[2] and v[3] and v[4] for v in results.values()),
              "A saved run carries its story: written for Example 1 and for Example 3 (demanding targets), labelled illustrative, every number equal to a recount of that run, the setup's targets worded as the setup states them", f"{results}")

    # ---------------------------------------------------------------- the pages
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp) / "bare"
        shutil.copytree(PLATFORM, bare, ignore=shutil.ignore_patterns("physics_*", "replay.html", "reports", client_story.STORY_FILE))
        results_page = run_app(PLATFORM, "Results at a glance")
        missing = run_app(bare, "Results at a glance")
    cards = re.findall(r'class="ub-kpi-value">([^<]+)<', "\n".join(m.value for m in results_page.main.markdown))
    charts = len(results_page.get("arrow_vega_lite_chart")) + len(results_page.get("vega_lite_chart"))
    page_text = " ".join(all_text(results_page.main))
    cl.record(not results_page.exception and len(cards) == 4 and charts == 5 and sentence_count(all_text(results_page.main)) == 1
              and f"{story['multiple']:.1f}x" in cards and f"{story['unattended_share_pct']:.0f}%" in cards and f"{story['trials_good']} of {story['trials_with_result']}" in cards and "assumption" in page_text.lower(),
              "The Results page draws with no error: four headline cards that show the story's numbers (more experiments, share unattended, time to the first good recipe, good recipes), five charts, the illustrative sentence once, and the manual comparison named as an assumption",
              f"cards {cards}; charts {charts}; exceptions {[str(e.value)[:80] for e in results_page.exception]}")
    cl.record(not missing.exception and any("results summary was not found" in w.value and "run_app.bat" in w.value for w in missing.warning),
              "A run saved before the story existed gets a plain message on the Results page that says what to do (double-click run_app.bat), not an error", "; ".join(w.value[:80] for w in missing.warning))
    overview = run_app(PLATFORM)
    demo = run_app(DEMO)
    overview_cards = re.findall(r'class="ub-kpi-value">([^<]+)<', "\n".join(m.value for m in overview.main.markdown))
    demo_cards = re.findall(r'class="ub-kpi-value">([^<]+)<', "\n".join(m.value for m in demo.main.markdown))
    cl.record(overview_cards == cards and not demo_cards and not overview.exception and not demo.exception and sentence_count(all_text(overview.main)) == 1,
              "The Overview shows the same four headline cards for a platform run and none for the proof of concept's demo run (which has no story), with the illustrative sentence still once", f"overview {overview_cards}; demo {demo_cards}")

    # ---------------------------------------------------------------- the part and the page keep to the rules
    part = ROOT / "cellpoc" / "client_story"
    imports = [line for p in part.glob("*.py") for line in p.read_text(encoding="utf-8").splitlines() if line.startswith(("import ", "from ")) and ("cellpoc" in line or line.startswith("from .."))]
    users = [p.relative_to(ROOT).as_posix() for p in (ROOT / "cellpoc").rglob("*.py") if "client_story" not in p.parts and re.search(r"from \.+ import .*client_story|from \.+client_story|cellpoc\.client_story|import client_story", p.read_text(encoding="utf-8", errors="replace"))]
    cl.record(architecture.ALLOWED["client_story"] == set() and not imports and users == ["cellpoc/platform_runner.py"], "The client story part imports nothing from the project and only the platform runner uses it; the dashboard page only displays the file it writes", f"{len(list(part.glob('*.py')))} files; used by {users}")
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    os.environ.pop("CELLPOC_RECORD", None)
    sys.exit(main())
