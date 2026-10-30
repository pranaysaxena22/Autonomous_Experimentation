"""Runs every health check in order and prints one summary table: the five proof-of-concept checks, the format check and the platform check.

Each check runs exactly as its own double-click file does (a separate Python run); this only collects the results.
It changes nothing. Exit code 0 means every check passed.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    ("PoC stage 1", "check_stage1.bat", "checks.stage1_check", "settings, scenario page, virtual lab"),
    ("PoC stage 2", "check_stage2.bat", "checks.stage2_check", "the cell simulator"),
    ("PoC stage 3", "check_stage3.bat", "checks.stage3_check", "adaptive engine, 40-campaign comparison"),
    ("PoC stage 4", "check_stage4.bat", "checks.stage4_check", "closed-loop run, faults, alerts"),
    ("PoC stage 5", "check_stage5.bat", "checks.stage5_check", "the dashboard"),
    ("Formats", "check_formats.bat", "checks.formats_check", "file formats, schemas, naming rules"),
    ("Platform 1", "check_platform1.bat", "checks.platform1_check", "setup rules, setup app, converter"),
    ("Ingest", "check_ingest.bat", "checks.ingest_check", "reading data files (Stage 2)"),
    ("Models", "check_models.bat", "checks.models_check", "modelling: leakage rules, grouped splitters, models, reports (Stage 3a)"),
    ("Calibration", "check_calibration.bat", "checks.calibration_check", "calibration and the carry-forward rule (Stage 3b-1)"),
    ("Domain", "check_domain.bat", "checks.domain_check", "the applicability-domain warning (Stage 3b-2)"),
    ("Replay", "check_replay.bat", "checks.replay_check", "the decision-usefulness replay (Stage 3b-3)"),
    ("Scorecard", "check_scorecard.bat", "checks.scorecard_check", "the model scorecard pages (Stage 3b-4)"),
    ("Seal", "check_seal.bat", "checks.seal_check", "the sealed acceptance lab is intact and used by nothing else"),
    ("Brief", "check_brief.bat", "checks.brief_check", "the decision engine's brief from Stage 3 (Stage 4-1)"),
    ("Dev lab", "check_devlab.bat", "checks.devlab_check", "the development lab and its four scenarios (Stage 4-2)"),
    ("Engine", "check_engine.bat", "checks.engine_check", "the governed decision engine and its five rules (Stage 4-3)"),
    ("Comparison", "check_comparison.bat", "checks.comparison_check", "the development comparison: scoring, pairing, statistics, report, engine lock (Stage 4-4)"),
    ("Seed guard", "check_seedguard.bat", "checks.seedguard_check", "the code itself refuses a sealed acceptance seed"),
    ("Recalibrated", "check_recalibrated.bat", "checks.recalibrated_check", "the recalibrated response to a stale target (R), the adopted rule 5 response, and its recorded scope"),
    ("Planner", "check_planner.bat", "checks.planner_check", "the motion planner: plans obey every rule, refusals in plain words (Stage 6)"),
    ("Executor", "check_executor.bat", "checks.executor_check", "the cell executor: the hand-authored timeline reproduced, faults, skips, refusals (Stage 6)"),
    ("Cell simulator", "check_cellsim.bat", "checks.cellsim_check", "the configurable cell simulator: the proof of concept's run with the setup's plan, executor and faults (Stage 5)"),
    ("3D viewer", "check_viewer.bat", "checks.viewer_check", "the 3D replay viewer: self-contained, offline, no logic of its own, a fault shows (Stage 7)"),
    ("Dashboard", "check_dashboard.bat", "checks.stage8_check", "the dashboard with the platform wired in: platform pages added, the proof of concept unchanged (Stage 8)"),
    ("Reports", "check_reports.bat", "checks.reports_check", "reports and exports: report page, PDF, Excel, CSV; numbers match the record, labelled, Deloitte look (Stage 9)"),
    ("Run this setup", "check_setup_run.bat", "checks.setup_run_check", "the setup app's 'Save and run it': the setup you fill in drives a simulated run (30 trials, 60 with a longer window), refusals in words, the dashboard and live buttons"),
    ("Connected loop", "check_connected.bat", "checks.connected_check", "the connected loop: the adopted engine chooses the recipes from the data file and what Stage 3 concluded; everything else unchanged"),
    ("Live run", "check_live.bat", "checks.live_check", "the live run: the same simulation as a batch run, paced; nothing published before its moment; its page shows it as it happens, on this computer only"),
    ("Launchers", "check_launchers.bat", "checks.launchers_check", "run_platform.bat (both variants) starts a dashboard that answers this computer only, looked at on the real listening addresses, with a self-test that can fail"),
    ("Instruments", "check_instruments.bat", "checks.instruments_check", "the barcode scanner and balance drivers against pretend devices, the barcode fault through the cell, a pretend real scanner in the executor, normal runs unchanged"),
    ("Physics", "check_physics.bat", "checks.physics_check", "the MuJoCo model of the cell from the layout: gravity, repeatability, all 28 reach targets solved by MuJoCo, spare reach equals the setup rules' formula, self-tests that can fail"),
    ("Client story", "check_story.bat", "checks.client_story_check", "the run told as results for a client: the Results page and the Overview's headline cards, every number recounted from the raw run record, planted wrong numbers caught"),
    ("Vision", "check_vision.bat", "checks.vision_check", "the vision: drawn bench scenes with a known answer (levels, colours, positions for the arm, reach, odd pictures) and the Vision page"),
    ("Unified app", "check_app.bat", "checks.app_check", "the unified app, Stages A to C (the setup app and the live view inside it): the menu and every page, hosted pages say what the dashboard says, the illustrative sentence once per page, the Overview's numbers match a separate recount (with planted wrong numbers), run_app.bat answers this computer only"),
    ("Console", "check_console.bat", "checks.console_check", "the operations console: served to this computer only, no developer wording, says what the rest of the app says, and in real Chrome its three views, camera verdicts, welcome and tour"),
    ("Client view", "check_client.bat", "checks.client_view_check", "the app as a client sees it: the client menu, no developer wording on any page, the illustrative labelling intact, the same numbers as the developer view, with a self-test that the scan can fail"),
    ("Rules 3/4 tool","check_rules34.bat", "checks.rules34_check", "the rules 3/4 diagnosis tool: its accounting is exactly right on hand-worked campaigns, it reads only the stored 4-4R data and reproduces the 4-4R table first"),
    ("Hardening", "check_hardening.bat", "checks.hardening_check", "bad files, odd folder names, no network, a clean copy, time limits, documentation (Stage 10)"),
]
RESULT = re.compile(r"(\d+) passed, (\d+) failed(?:, (\d+) warnings?)?")


def clock(seconds: float) -> str:
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest:02d} s" if minutes else f"{rest} s"


def run_one(module: str) -> tuple[int, int, int, float, list[str], bool]:
    """(passed, failed, warnings, seconds, lines worth showing, whether a result line was found)"""
    started = time.time()
    done = subprocess.run([sys.executable, "-B", "-m", module], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    seconds = time.time() - started
    lines = (done.stdout or "").splitlines()
    found = None
    for line in reversed(lines):
        found = RESULT.search(line)
        if found:
            break
    shown = [line.strip() for line in lines if line.startswith("[FAIL]") or line.startswith("[WARN]")]
    if not found:
        tail = (done.stderr or "").strip().splitlines()[-3:]
        return 0, 1, 0, seconds, ["no result line was printed"] + tail, False
    passed, failed, warned = int(found.group(1)), int(found.group(2)), int(found.group(3) or 0)
    if done.returncode != 0 and failed == 0:
        failed = 1
        shown.append(f"the check ended with an error (exit code {done.returncode})")
    return passed, failed, warned, seconds, shown, True


def main() -> int:
    print("Running every health check in order. This takes several minutes (stages 3 and 5 are the slow ones).\n", flush=True)
    started = time.time()
    rows = []
    for name, launcher, module, covers in CHECKS:
        print(f"  running {name} ({launcher}) ...", flush=True)
        rows.append((name, launcher, covers, *run_one(module)))
    total = time.time() - started

    width = max(len(r[0]) for r in rows)
    print("\n" + "=" * 78)
    print(f"{'Check'.ljust(width)}  {'Passed':>6}  {'Failed':>6}  {'Warnings':>8}  {'Time':>10}  Result")
    print("-" * 78)
    for name, launcher, covers, passed, failed, warned, seconds, shown, found in rows:
        print(f"{name.ljust(width)}  {passed:>6}  {failed:>6}  {warned:>8}  {clock(seconds):>10}  {'ALL GOOD' if not failed else 'NEEDS ATTENTION'}")
    print("-" * 78)
    passed_all, failed_all, warned_all = (sum(r[3] for r in rows), sum(r[4] for r in rows), sum(r[5] for r in rows))
    print(f"{'Total'.ljust(width)}  {passed_all:>6}  {failed_all:>6}  {warned_all:>8}  {clock(total):>10}  {'ALL GOOD' if not failed_all else 'NEEDS ATTENTION'}")
    print("=" * 78)
    notes = [(r[0], line) for r in rows for line in r[7] if line.startswith("[WARN]") or r[4]]
    if notes:
        print("\nThings to look at:")
        for name, line in notes:
            print(f"  {name}: {line}")
    if failed_all:
        print("\nTo see the detail, double-click the launcher of the check marked NEEDS ATTENTION:",
              ", ".join(r[1] for r in rows if r[4]) + ".")
    print(f"\nFinished in {clock(total)}. " + ("Everything passed." if not failed_all else "Something needs attention."))
    return 1 if failed_all else 0


if __name__ == "__main__":
    sys.exit(main())
