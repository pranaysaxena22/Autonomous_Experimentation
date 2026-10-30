"""Health check for Stage 8, the dashboard with the platform wired in: one app that shows a platform run's results, its 3D replay and its data and model page, and still shows the proof-of-concept run exactly as before.

In plain words it checks that: the proof-of-concept demo record still opens and gives exactly the six pages it always gave, with the same number of charts, figures, buttons and the same text (compared with a recording made
before Stage 8 was built); a record from a platform run gives those six pages plus '3D replay', 'Data and model' and (from Stage 9) 'Reports', and nothing crashes; the record keeps its platform section when saved and read back; each trial's line on
the replay page matches that trial in the record (same number, same outcome); the replay page puts the 3D replay file on the screen; the data page carries the data status label, the row accounting and the plain statement that
the Stage 4 engine is not used and what is known about it; the 'What this shows' page of a platform run describes the platform run, not the demo; a missing replay file gives a plain message, not a crash; a record without the
platform section (the demo) and one that is damaged still behave as before; the real dashboard server starts with a platform record and sends nothing fetched from the internet; and the dashboard still contains no
calculations, no filtering and no web addresses. Nothing is written into the project and nothing uses the network except the local server on this computer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.platform_info import ENGINE_SENTENCE  # noqa: E402
from cellpoc.platform_runner import build_replay, run_platform, save_platform_run  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, external_references  # noqa: E402
from checks.models_check import project_files  # noqa: E402

DEMO = ROOT / "runs" / "demo"
SIX = ["The run", "Timeline", "Overnight handovers", "Does learning help?", "Throughput", "What this shows"]
# Recorded from the unchanged dashboard on the proof-of-concept demo record BEFORE Stage 8 was built (2026-10-13). If the demo record is rebuilt on purpose, record this again and say why in docs/decisions.md.
# The fingerprint covers every word and tag on the pages but NOT the text inside the style sheet block (colours, spacing and fonts are looks, not content), so a restyle does not trip it while any change to the words or structure does.
# Its value is the fingerprint of the same pages as they were when recorded: the old style sheet and the current one give the same value (2026-10-13, see docs/decisions.md).
GOLDEN = {"n_markdown": 71, "n_metric": 18, "n_button": 2, "n_vega": 6, "n_dataframe": 4, "markdown_hash": "845905086fc4eed9870a47027308f9d4addd6d9c087034ff2eb103405b71d1fb"}
STYLE_SHEET = re.compile(r"<style>.*?</style>", re.DOTALL)


def render(folder: Path):
    from streamlit.testing.v1 import AppTest
    os.environ["CELLPOC_RECORD"] = str(folder)
    try:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
        app.run()
    finally:
        os.environ.pop("CELLPOC_RECORD", None)
    return app


def words_hash(blocks: list[str]) -> str:
    """Fingerprint of the text blocks with the inside of any <style>...</style> element left out (the block itself, its position and anything outside the element still count)."""
    return hashlib.sha256("\n".join(STYLE_SHEET.sub("<style></style>", block) for block in blocks).encode()).hexdigest()


def shape(app) -> dict:
    return {"n_markdown": len(app.markdown), "n_metric": len(app.metric), "n_button": len(app.button), "n_vega": len(app.get("arrow_vega_lite_chart")) + len(app.get("vega_lite_chart")),
            "n_dataframe": len(app.dataframe), "markdown_hash": words_hash([m.value for m in app.markdown])}


def planted_changes(blocks: list[str]) -> tuple[bool, str]:
    """Self-test of the fingerprint on the real page text: a restyle must NOT change it; a changed word, a removed or moved block, or words hidden next to a style sheet MUST."""
    base = words_hash(blocks)
    sheet = next(i for i, b in enumerate(blocks) if "<style>" in b)
    word = next(i for i, b in enumerate(blocks) if "<style>" not in b and "illustrative" in b.lower())

    def with_(i: int, text: str) -> list[str]:
        return [text if k == i else b for k, b in enumerate(blocks)]
    restyled = with_(sheet, blocks[sheet].replace("#86BC25", "#000000").replace("</style>", ".planted { color: red; margin: 99px; }\n</style>"))
    reworded = with_(word, blocks[word].replace("llustrative", "llustratife", 1))
    dropped = blocks[:word] + blocks[word + 1:]
    moved = list(blocks)
    moved[word], moved[word + 1] = moved[word + 1], moved[word]
    smuggled = with_(sheet, blocks[sheet] + " Planted words outside the style element.")
    ok = (words_hash(restyled) == base and words_hash(reworded) != base and words_hash(dropped) != base and words_hash(moved) != base and words_hash(smuggled) != base)
    return ok, (f"restyle same {words_hash(restyled) == base}; reworded differs {words_hash(reworded) != base}; block dropped differs {words_hash(dropped) != base}; "
                f"blocks swapped differs {words_hash(moved) != base}; words next to the style sheet differ {words_hash(smuggled) != base}")


def text_of(app) -> str:
    """Every piece of text on the page: paragraphs, headings, captions and notes."""
    return "\n".join(e.value for kind in ("markdown", "subheader", "caption", "info", "warning") for e in getattr(app, kind))


def server_check(cl: Checklist, folder: Path) -> None:
    port = 8767
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port), "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                            cwd=ROOT, env=dict(os.environ, CELLPOC_RECORD=str(folder)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        cl.record(healthy, "The real dashboard server starts with a platform record and reports healthy")
        if healthy:
            page = urllib.request.urlopen(base, timeout=10).read().decode("utf-8")
            cl.record(not external_references(page), "The page the server sends contains nothing fetched from the internet", f"{len(page)} bytes checked")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    cl = Checklist("PLATFORM STAGE 8 (dashboard integration): the platform run's results, 3D replay and data page in one app; the proof-of-concept run unchanged")
    before = project_files()
    # --- the proof of concept's record: unchanged
    if not (DEMO / "record.json").exists():
        cl.record(False, "The proof-of-concept demo record exists", "double-click build_demo.bat first")
        return cl.print()
    poc = render(DEMO)
    cl.record(not poc.exception and [t.label for t in poc.tabs] == SIX, "The proof-of-concept demo record still gives exactly its six pages, in the same order, with no error", ", ".join(t.label for t in poc.tabs))
    now = shape(poc)
    cl.record(now == GOLDEN, "...and everything on them is as it was before Stage 8: the same number of text blocks, figures, buttons, charts and tables, and the same words (compared with a recording made before the change)",
              "" if now == GOLDEN else f"differs: {[k for k in GOLDEN if GOLDEN[k] != now[k]]}")
    ok, detail = planted_changes([m.value for m in poc.markdown])
    cl.record(ok, "Self-test of that comparison on the real pages: restyling them (colours, spacing, a new rule in the style sheet) does NOT trip it, while a changed word, a removed block, two blocks swapped, or words slipped in next to the style sheet each DO", detail)
    demo_record = run_store.load(DEMO)
    cl.record(demo_record.platform is None, "A record without a platform section (the demo) is read as having none, and is not reported as out of date")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = run_platform()
        folder = tmp / "platform"
        save_platform_run(run, folder)
        build_replay(run, folder)
        info = run.record.platform
        back = run_store.load(folder)
        cl.record(info is not None and back.platform is not None and asdict(back.platform) == asdict(info) and asdict(back) == asdict(run.record),
                  "A platform run's record keeps its platform section when saved and read back, unchanged", f"{len(info.trial_rows) if info else 0} trial lines")

        app = render(folder)
        labels = [t.label for t in app.tabs]
        cl.record(not app.exception and labels == SIX + ["3D replay", "Data and model", "Reports"], "A platform record gives the six pages and then '3D replay', 'Data and model' and 'Reports' (Stage 9), with no error", ", ".join(labels))
        full = text_of(app)

        # the moments the demo script (docs/guides/demo_script.md) tells you to go to must exist in a platform run, with what it says happens there
        whens = {s.when for s in back.snapshots}
        story = {("Sat 10 Oct 22:15", "fault", 8), ("Sat 10 Oct 23:20", "recovery", 8), ("Mon 12 Oct 19:20", "fault", 19), ("Mon 12 Oct 20:26", "candidate_skipped", 19), ("Mon 12 Oct 20:26", "alert_queued", 19)}
        have = {(e.when, e.kind, e.trial) for e in back.events}
        cl.record(all(m in whens for m in ("Sat 10 Oct 09:00", "Tue 13 Oct 08:00")) and story <= have and any("Tue 13 Oct 08:00" in a.message or a.queued_for == "Tue 13 Oct 08:00" for a in back.alerts),
                  "The moments the demo script names exist in a platform run and show what the script says (trial 8's fault and recovery, trial 19's failed retry, skip and alert for Tue 13 Oct 08:00)", f"{len(story & have)} of {len(story)} events found")

        # trial lines against the record
        trials = back.trials
        rows = info.trial_rows
        agree = len(rows) == len(trials) and all(row.startswith(f"Trial {t.trial}:") and ((t.status == "Skipped" and "skipped (no result)" in row) or (t.status == "Completed" and f"result: {t.outcome}" in row))
                                                 for row, t in zip(rows, trials))
        cl.record(agree and all(row in full for row in rows), "Each trial's line on the replay page matches that trial in the record (same number, same outcome), and every line is on the page",
                  f"{len(rows)} lines, {len(trials)} trials, {sum(1 for t in trials if t.status == 'Skipped')} skipped")
        iframes = app.get("iframe")
        cl.record(len(iframes) >= 1, "The replay page puts the 3D replay file on the screen", f"{len(iframes)} embedded page(s)")
        replay_text = (folder / "replay.html").read_text(encoding="utf-8")
        src = ""
        if iframes:
            proto = iframes[0].proto
            src = getattr(proto, "srcdoc", "") or ""
        cl.record(bool(src) and src == replay_text, "...and it is exactly the replay file saved next to the record (nothing added, nothing taken out)", f"{len(src)} of {len(replay_text)} characters")
        cl.record(info.label in full and ("SYNTHETIC" in info.label or "ILLUSTRATIVE" in info.label), "The pages carry the data status label (synthetic or illustrative), written out in capitals", info.label)
        cl.record(any("ROW ACCOUNTING" in line for line in info.data_lines) and all(line in full for line in info.data_lines) and "ROW ACCOUNTING" in full,
                  "The data page shows the reader's data status line and its row accounting, as the reader wrote them", f"{len(info.data_lines)} lines")
        cl.record(ENGINE_SENTENCE in full and "does not show" in full.lower() and "not a prediction about real tablets" in full, "The data page states plainly that the Stage 4 engine is not used here, and the measured finding about it, and that this is not a prediction about real tablets")
        about = [m.value for m in app.markdown]
        cl.record(any(info.setup_name in v for v in about) and "Rebuild it with build_demo.bat" not in " ".join(i.value for i in app.info), "The 'What this shows' page of a platform run describes that platform run, not the demo", info.setup_name)
        cl.record(all(len(line) > 20 for line in info.pipeline + info.model_lines) and not any("Traceback" in line or "{" in line for line in info.pipeline + info.data_lines + info.model_lines + info.limits),
                  "All the platform text is plain words (no code, no braces, no error traces)")

        # missing replay file
        (folder / "replay.html").unlink()
        gone = render(folder)
        warning = " ".join(w.value for w in gone.warning)
        cl.record(not gone.exception and "make_platform_demo.bat" in warning and [t.label for t in gone.tabs] == labels, "If the 3D replay file is missing, the page says so plainly and names make_platform_demo.bat (everything else still shows), not a crash", warning[:90])
        server_check(cl, folder)

    # --- damaged records still behave as before (the Stage 5 check covers the wording in full)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "record.json").write_text('{"meta": {"run_id": "old"}}', encoding="utf-8")
        bad = render(Path(tmp))
        cl.record(not bad.exception and "out of date" in " ".join(w.value for w in bad.warning), "A damaged record still gives the plain 'out of date' message, not a crash")

    architecture.check(cl)
    problems, count = architecture.dashboard_problems()
    cl.record(not problems, f"The dashboard (now {count} files, including the two new pages) still does no calculations, no sorting or filtering, uses no calculation library and contains no web address", "; ".join(problems[:3]))
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
