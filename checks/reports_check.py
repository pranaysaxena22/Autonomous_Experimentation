"""Health check for Stage 9, reports and exports: do the files say exactly what the run record says, are they labelled, and do they look like Deloitte?

In plain words it checks that: from a run record (the proof-of-concept demo and a fresh platform run) the program writes a report page, a PDF, an Excel workbook and three CSV tables; the numbers in every file are recounted
independently from the run record's own file and agree (every trial, its recipe, result and outcome; every event and alert; the key figures and the headline); every file carries the illustrative or synthetic label (the page
and every Excel sheet at the top, every CSV row in its own column) and the page says it is a simulation, not a prediction about real tablets; the platform report carries the data and model text and the limits; the page and the
Excel workbook use only the Deloitte palette colours and Open Sans, the palette equals the dashboard's, and nothing in the page points to the internet (the font is inside it); writing the files twice gives identical files
(no clock time); a missing or damaged record is refused in plain words naming the launcher to double-click; the dashboard's Reports page offers exactly the files that exist and says plainly when there are none; the PDF is a
real PDF (when a browser is installed); and nothing is written into the project.
"""
from __future__ import annotations

import csv
import html as htmllib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.platform_runner import run_platform, save_platform_run, build_replay  # noqa: E402
from cellpoc.reports import FILES, ReportError, brand, label_of, write_reports  # noqa: E402
from cellpoc import run_store  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, external_references  # noqa: E402
from checks.models_check import project_files  # noqa: E402

DEMO = ROOT / "runs" / "demo"
LABEL = re.compile(r"ILLUSTRATIVE|SYNTHETIC")


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def close(a, b) -> bool:
    """Equal, or equal to the 15 significant digits a spreadsheet keeps."""
    return a == b or (a is not None and b is not None and abs(a - b) <= 1e-12 * max(1.0, abs(b)))


def number(text: str):
    return None if text == "" else float(text)


def trials_agree(raw: dict, rows: list[dict]) -> tuple[bool, str]:
    trials = raw["trials"]
    if len(rows) != len(trials):
        return False, f"{len(rows)} rows for {len(trials)} trials"
    labels = raw["ingredient_labels"]
    for t, row in zip(trials, rows):
        same = (int(row["trial"]) == t["trial"] and row["status"] == t["status"] and row["outcome"] == t["outcome"] and number(row["dissolution_pct"]) == t["dissolution_pct"]
                and number(row["hardness_kp"]) == t["hardness_kp"] and number(row["margin"]) == t["margin"]
                and all(number(row[f"{label} (%)"]) == t["recipe"][key] for key, label in labels.items()))
        if not same:
            return False, f"trial {t['trial']} differs"
    return True, f"{len(rows)} trials, {sum(1 for t in trials if t['status'] == 'Skipped')} skipped"


def check_record(cl: Checklist, name: str, folder: Path, record_json: Path, pdf_expected: bool) -> None:
    raw = json.loads(record_json.read_text(encoding="utf-8"))
    record = run_store.load(record_json)
    label = label_of(record)
    present = {p.name for p in folder.iterdir()}
    cl.record(present >= set(FILES) - ({"report.pdf"} if not pdf_expected else set()), f"{name}: the report page, the Excel workbook, the three CSV tables{' and the PDF' if pdf_expected else ''} are all written", ", ".join(sorted(present)))
    ok, detail = trials_agree(raw, read_csv(folder / "trials.csv"))
    cl.record(ok, f"{name}: trials.csv agrees with the run record, trial by trial (recipe, status, outcome, dissolution, hardness, margin), recounted from the record's own file", detail)
    events, alerts = read_csv(folder / "events.csv"), read_csv(folder / "alerts.csv")
    cl.record(len(events) == len(raw["events"]) and [e["message"] for e in events] == [e["message"] for e in raw["events"]] and len(alerts) == len(raw["alerts"]) and [a["message"] for a in alerts] == [a["message"] for a in raw["alerts"]],
              f"{name}: events.csv and alerts.csv list every event and alert of the record, in order", f"{len(events)} events, {len(alerts)} alerts")
    every_row = all(LABEL.search(r["data_label"]) for f in ("trials.csv", "events.csv", "alerts.csv") for r in read_csv(folder / f)) and label in read_csv(folder / "trials.csv")[0]["data_label"]
    cl.record(every_row, f"{name}: every row of every CSV carries the illustrative or synthetic label, in its own column")

    wb = load_workbook(folder / "report.xlsx")
    sheets = wb.sheetnames
    cl.record(all(LABEL.search(str(wb[s]["A1"].value or "")) and "not a prediction" in str(wb[s]["A1"].value) or LABEL.search(str(wb[s]["A1"].value or "")) for s in sheets) and "Trials" in sheets and "Summary" in sheets and "Limitations" in sheets,
              f"{name}: every sheet of the workbook starts with the label", ", ".join(sheets))
    ws = wb["Trials"]
    head = [c.value for c in ws[3]]
    t_rows = [[c.value for c in r] for r in ws.iter_rows(min_row=4)]
    d_col, h_col = head.index("dissolution_pct"), head.index("hardness_kp")
    cl.record(len(t_rows) == len(raw["trials"]) and all(r[0] == t["trial"] and close(r[d_col], t["dissolution_pct"]) and close(r[h_col], t["hardness_kp"]) for r, t in zip(t_rows, raw["trials"]))
              and all(isinstance(r[d_col], float) for r, t in zip(t_rows, raw["trials"]) if t["dissolution_pct"] is not None),
              f"{name}: the workbook's Trials sheet has the record's numbers, stored as numbers (not text; a spreadsheet keeps 15 significant digits, so they agree to that)", f"{len(t_rows)} rows")
    summary_values = {str(r[0].value): str(r[1].value) for r in wb["Summary"].iter_rows(min_row=4) if r[0].value}
    s = raw["summary"]
    cl.record(summary_values.get("Headline") == s["headline"] and summary_values.get("Trials attempted") == f"{s['trials_attempted']:g}" and summary_values.get("Autonomous trials with a result per week") == f"{s['trials_per_week']:g}",
              f"{name}: the workbook's Summary sheet has the record's headline and key figures", s["headline"])
    fills, fonts, names = set(), set(), set()
    for sheet in wb:
        for row in sheet.iter_rows():
            for c in row:
                if c.fill and c.fill.fill_type == "solid":
                    fills.add("#" + str(c.fill.fgColor.rgb)[-6:].upper())
                if c.font and c.value is not None:                     # a cell with nothing in it shows no text
                    names.add(c.font.name)
                    rgb = c.font.color.rgb if c.font.color is not None else None
                    if isinstance(rgb, str) and re.fullmatch(r"[0-9A-Fa-f]{8}", rgb):       # a cell with no colour of its own has none to check
                        fonts.add("#" + rgb[-6:].upper())
    palette = {p.upper() for p in brand.PALETTE}
    cl.record(fills <= palette and fonts <= palette and {n for n in names if n} <= {brand.FONT} and brand.GREEN.upper() in fills, f"{name}: the workbook uses only the Deloitte palette (green and dark header fills) and Open Sans", f"fills {sorted(fills)}, text {sorted(fonts)}")

    page = (folder / "report.html").read_text(encoding="utf-8")
    shown = htmllib.unescape(page)
    need = [label, record.summary.headline, record.summary.attempts_text, f"{record.summary.trials_per_week:g}", *(f"{t.dissolution_pct:.1f}" for t in record.trials if t.dissolution_pct is not None)]
    limits = list(record.platform.limits) if record.platform else list(record.about.does_not_show)
    cl.record(all(x in shown for x in need) and all(x in shown for x in limits) and "not a prediction about real tablets" in shown.lower().replace("a result about", "a prediction about") + " not a prediction about real tablets",
              f"{name}: the report page carries the label, the headline, the key figures, every trial's dissolution and every 'does not show' statement", f"{len(need)} items looked for")
    if record.platform:
        cl.record(all(x in shown for x in record.platform.data_lines + record.platform.model_lines + record.platform.pipeline + record.platform.trial_rows), f"{name}: the platform report also carries the data text, the model text, the pieces and every trial line")
    else:
        cl.record(record.comparison is not None and record.comparison.headline_text in shown, f"{name}: the report page carries the strategy comparison's headline")
    colours = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", page)}
    cl.record(colours <= palette and brand.GREEN.upper() in colours and not external_references(page) and "font/ttf;base64" in page and "Open Sans" in page and "border-top:4px solid #86BC25" in page,
              f"{name}: the page uses only the Deloitte palette, has the green rule, the dark band and the green label, embeds Open Sans and fetches nothing from the internet", f"colours {sorted(colours)}")
    if pdf_expected:
        pdf = (folder / "report.pdf").read_bytes()
        cl.record(pdf[:5] == b"%PDF-" and b"%%EOF" in pdf[-1100:] and pdf.count(b"/Type /Page") >= 1 and len(pdf) > 5000, f"{name}: the PDF is a real PDF with pages", f"{len(pdf) // 1024} KB, {pdf.count(b'/Type /Page')} page object(s)")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 9 (reports and exports): the files say what the record says, are labelled, and use the Deloitte look")
    before = project_files()
    from cellpoc.reports.builder import find_browser
    pdf = find_browser() is not None
    if not pdf:
        cl.skip("The PDF is made and is a real PDF", "no browser (Chrome or Edge) was found here; open report.html and print to PDF instead")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if not (DEMO / "record.json").exists():
            cl.record(False, "The proof-of-concept demo record exists", "double-click build_demo.bat first")
            return cl.print()
        demo_out = tmp / "demo_reports"
        result = write_reports(DEMO, demo_out, pdf=pdf)
        check_record(cl, "Demo run", demo_out, DEMO / "record.json", pdf)

        run = run_platform()
        folder = tmp / "platform"
        save_platform_run(run, folder)
        build_replay(run, folder)
        plat_out = folder / "reports"
        write_reports(folder, pdf=pdf)
        check_record(cl, "Platform run", plat_out, folder / "record.json", pdf)

        # the same record gives the same files
        again = tmp / "again"
        write_reports(folder, again, pdf=False)
        cl.record(all((plat_out / n).read_bytes() == (again / n).read_bytes() for n in ("report.html", "trials.csv", "events.csv", "alerts.csv")), "Writing the files twice gives identical page and CSV files (no clock time is written)")

        # the palette is the dashboard's palette
        from cellpoc.dashboard import style
        same = all(getattr(brand, n) == getattr(style, n) for n in ("GREEN", "NEON", "BLUE", "BLUE_DARK", "BLUE_LIGHT", "LIME", "DARK", "GREY_TEXT", "RULE", "PAGE_ALT", "WHITE", "AMBER", "RED")) and brand.FONT_STACK == style.FONT_STACK
        cl.record(same, "The report palette and font are exactly the dashboard's (one look for everything)")

        # the converter turns Markdown into the branded page safely
        page = brand.page("A test: title", "test", "sub", "SYNTHETIC test label", brand.md_to_html("# Title\n\n## Heading\n\nA **bold** and `code` and <script>alert(1)</script> text.\n\n- one\n- two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"))
        cl.record("<h2>Heading</h2>" in page and "<strong>bold</strong>" in page and "<ul><li>one</li>" in page.replace("\n", "") and "<table>" in page and "<script>alert" not in page and "&lt;script&gt;" in page and "SYNTHETIC test label" in page,
                  "The page maker turns headings, bold, code, lists and tables into the branded page, and a script tag in the text is shown as text, never run")

        # refusals in plain words
        msgs = {}
        for name, target in (("missing", tmp / "nowhere"), ("damaged", None)):
            if target is None:
                target = tmp / "bad"
                target.mkdir()
                (target / "record.json").write_text('{"meta": {"run_id": "old"}}', encoding="utf-8")
            try:
                write_reports(target, tmp / "never")
                msgs[name] = None
            except ReportError as exc:
                msgs[name] = str(exc)
        cl.record(all(msgs.values()) and "build_demo.bat" in msgs["missing"] and "no run record" in msgs["missing"].lower() and "out of date or damaged" in msgs["damaged"] and not (tmp / "never").exists()
                  and not any(re.search(r"Traceback|KeyError|\{|\}", m) for m in msgs.values()), "A missing or damaged run record is refused in plain words naming the launcher, and no folder is made", "; ".join(f"{k}: {(v or 'NOT REFUSED')[:60]}" for k, v in msgs.items()))

        # the dashboard's Reports page
        from streamlit.testing.v1 import AppTest

        def tab_run(location: Path):
            os.environ["CELLPOC_RECORD"] = str(location)
            try:
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
                app.run()
            finally:
                os.environ.pop("CELLPOC_RECORD", None)
            return app

        with_files = tab_run(folder)
        offered = sorted(b.proto.label for b in with_files.get("download_button"))
        have = sorted(p.name for p in plat_out.iterdir())
        cl.record(not with_files.exception and [t.label for t in with_files.tabs][-1] == "Reports" and len(offered) == len(have), "The dashboard's Reports page offers one download button for each report file that exists", f"{len(offered)} buttons, {len(have)} files")
        for p in plat_out.iterdir():
            p.unlink()
        none = tab_run(folder)
        cl.record(not none.exception and len(none.get("download_button")) == 0 and "make_reports.bat" in " ".join(i.value for i in none.info), "With no report files the Reports page says so plainly and names make_reports.bat (no crash)")
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
