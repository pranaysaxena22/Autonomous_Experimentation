"""Writes the report files for one run record: a branded report page (HTML), the same as a PDF when a browser is installed, an Excel workbook and three CSV tables.

Everything is read from the run record, the same file the dashboard reads, so the numbers in every file are the dashboard's numbers. Every file carries the data-status label (illustrative or synthetic) and says
it is a simulation, not a prediction about real tablets. Nothing is fetched from the internet and the same record always gives the same files (no clock time is written).
"""
from __future__ import annotations

import csv
import html
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .. import run_store
from ..contracts import RunRecord
from . import brand

BROWSERS = (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
FILES = ("report.html", "report.pdf", "report.xlsx", "trials.csv", "events.csv", "alerts.csv")
NOT_A_PREDICTION = "A simulation, not a prediction about real tablets."


class ReportError(Exception):
    """The reports cannot be written. The message says what to do, in plain words."""


@dataclass
class ReportResult:
    folder: Path
    files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def label_of(record: RunRecord) -> str:
    """The data-status label every file carries."""
    if record.platform is not None:
        return record.platform.label
    return f"ILLUSTRATIVE: {record.meta.banner}. {NOT_A_PREDICTION}"


def _n(value) -> str:
    return "none" if value is None else (f"{value:g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value))


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def recipe_columns(record: RunRecord) -> list[tuple[str, str]]:
    """(key, column heading) for every ingredient, in the record's order, then any other recipe key a trial has."""
    columns = [(key, f"{label} (%)") for key, label in record.ingredient_labels.items()]
    known = {k for k, _ in columns}
    for t in record.trials:
        for key in t.recipe:
            if key not in known:
                columns.append((key, key))
                known.add(key)
    return columns


def key_figures(record: RunRecord) -> list[tuple[str, str]]:
    s = record.summary
    return [("Trials attempted", _n(s.trials_attempted)), ("Trials with a result", _n(s.trials_with_result)), ("Trials skipped (no result)", _n(s.trials_skipped)), ("Trials measured good", _n(s.trials_good)),
            ("First good trial", _n(s.first_good_trial)), ("Best trial", _n(s.best_trial)), ("Best margin", _n(s.best_margin)), ("Run length (hours)", _n(s.run_hours)),
            ("Hours with nobody in the lab", _n(s.unattended_hours)), ("Trials started with nobody in the lab", _n(s.trials_started_unattended)), ("Faults recovered by the cell", _n(s.faults_recovered)),
            ("Alerts for staff", _n(s.alerts_for_staff)), ("Autonomous trials with a result per week", _n(s.trials_per_week)), ("Manual baseline, trials per week (an assumption)", _n(s.manual_baseline_trials_per_week)),
            ("Autonomous divided by manual baseline", _n(s.speedup_vs_manual))]


def what_was_run(record: RunRecord) -> list[tuple[str, str]]:
    m = record.meta
    return [("Run", m.run_id), ("Strategy", f"{m.strategy_name}: {m.strategy_description}"), ("Random seed", _n(m.random_seed)), ("Start", m.start), ("End", m.end),
            ("Length (minutes)", _n(m.duration_minutes)), ("Faults applied", _yes(m.faults_applied))]


# ---------------------------------------------------------------- CSV
def _write_csv(path: Path, header: list[str], rows: list[list], label: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header + ["data_label"])
        for row in rows:
            w.writerow(["" if v is None else v for v in row] + [label])


def trial_rows(record: RunRecord) -> tuple[list[str], list[list]]:
    columns = recipe_columns(record)
    header = ["trial", *[h for _, h in columns], "status", "outcome", "dissolution_pct", "hardness_kp", "margin", "good_so_far", "start", "end", "why_this_recipe", "notes"]
    rows = [[t.trial, *[t.recipe.get(k) for k, _ in columns], t.status, t.outcome, t.dissolution_pct, t.hardness_kp, t.margin, t.good_so_far, t.start, t.end, t.reason, " | ".join(t.notes)] for t in record.trials]
    return header, rows


def event_rows(record: RunRecord) -> tuple[list[str], list[list]]:
    return (["minute", "when", "kind", "trial", "station", "someone_in_the_lab", "message"],
            [[e.minute, e.when, e.kind, e.trial, e.station, _yes(e.attended), e.message] for e in record.events])


def alert_rows(record: RunRecord) -> tuple[list[str], list[list]]:
    return (["when", "trial", "severity", "title", "message", "needs_a_person", "queued_for"],
            [[a.when, a.trial, a.severity, a.title, a.message, _yes(a.needs_human), a.queued_for] for a in record.alerts])


# ---------------------------------------------------------------- the report page
def _table(header: list[str], rows: list[list[str]], numeric: set[int] = frozenset()) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f'<td class="num">{html.escape(c)}</td>' if i in numeric else f"<td>{html.escape(c)}</td>" for i, c in enumerate(row)) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bullets(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in lines) + "</ul>"


def _fmt(value, places: int) -> str:
    return "" if value is None else f"{value:.{places}f}"


def report_html(record: RunRecord) -> str:
    label = label_of(record)
    columns = recipe_columns(record)
    parts = [f"<h2>What was run</h2>{_table(['Item', 'Value'], [list(r) for r in what_was_run(record)])}",
             f"<h2>Results</h2><p><strong>{html.escape(record.summary.headline)}</strong></p><p>{html.escape(record.summary.attempts_text)}.</p>{_table(['Measure', 'Value'], [list(r) for r in key_figures(record)], {1})}"]
    trials = [[str(t.trial), t.status, t.outcome, _fmt(t.dissolution_pct, 1), _fmt(t.hardness_kp, 2), _fmt(t.margin, 2), ", ".join(f"{record.ingredient_labels.get(k, k)} {t.recipe.get(k, 0):.1f}" for k, _ in columns), "; ".join(t.notes)] for t in record.trials]
    parts.append("<h2>Every trial</h2><p>Dissolution is the share dissolved after 30 minutes; hardness is in kP; the margin says how comfortably a trial met the specification (negative means it did not). A skipped trial has no result.</p>"
                 + _table(["Trial", "Status", "Outcome", "Dissolution (%)", "Hardness (kP)", "Margin", "Recipe (%)", "Faults and notes"], trials, {0, 3, 4, 5}))
    if record.alerts:
        parts.append("<h2>Faults and alerts</h2>" + _table(["When", "Trial", "Severity", "What happened", "Needs a person"], [[a.when, str(a.trial), a.severity, a.message, _yes(a.needs_human) + (f" (queued for {a.queued_for})" if a.queued_for else "")] for a in record.alerts]))
    else:
        parts.append("<h2>Faults and alerts</h2><p>No fault or alert in this run.</p>")
    if record.handovers:
        parts.append("<h2>What happened while nobody was in the lab</h2>" + "".join(f"<h3>{html.escape(h.title)}</h3><p>{html.escape(h.text)}</p>" for h in record.handovers))
    for comparison, name in ((record.comparison, "Does learning help? (no faults)"), (record.comparison_with_faults, "Does learning help? (with the scripted faults)")):
        if comparison is not None:
            parts.append(f"<h2>{name}</h2><p>{html.escape(comparison.headline_text)}</p>" + _bullets(comparison.measure_notes) + _bullets([p.sentence for p in comparison.paired]))
    if record.platform is not None:
        p = record.platform
        parts.append("<h2>How the pieces connected in this run</h2>" + _bullets(p.pipeline))
        parts.append("<h2>The data file, as the reader found it</h2>" + _bullets(p.data_lines))
        parts.append("<h2>What the modelling step made of it</h2>" + _bullets(p.model_lines))
        parts.append("<h2>What happened trial by trial (plan and executor)</h2>" + _bullets(p.trial_rows))
    shows = record.about
    parts.append("<h2>What this report does not show</h2>" + _bullets(list(record.platform.limits) if record.platform is not None else (list(shows.does_not_show) if shows else [NOT_A_PREDICTION])))
    return brand.page("Autonomous formulation cell: run report", "formulation", f"Run {record.meta.run_id}: {record.meta.start} to {record.meta.end}", label, "\n".join(parts),
                      f"{label} Written by the platform from the run record; the same numbers as the dashboard.")


# ---------------------------------------------------------------- Excel
def _sheet(wb: Workbook, title: str, label: str, header: list[str], rows: list[list], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    green, dark = PatternFill("solid", fgColor="FF" + brand.GREEN[1:]), PatternFill("solid", fgColor="FF" + brand.DARK[1:])
    ws.cell(1, 1, label).font = Font(name=brand.FONT, bold=True, color="FF" + brand.BLACK[1:])
    for c in range(1, max(len(header), 2) + 1):
        ws.cell(1, c).fill = green
    for c, h in enumerate(header, 1):
        cell = ws.cell(3, c, h)
        cell.font, cell.fill, cell.alignment = Font(name=brand.FONT, bold=True, color="FF" + brand.WHITE[1:]), dark, Alignment(wrap_text=True, vertical="top")
    for r, row in enumerate(rows, 4):
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v)
            cell.font = Font(name=brand.FONT, color="FF" + brand.DARK[1:])
            cell.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 40, vertical="top")
    for c in range(1, len(header) + 1):
        widest = max([len(str(header[c - 1]))] + [len(str(r[c - 1])) for r in rows if c - 1 < len(r) and r[c - 1] is not None])
        ws.column_dimensions[get_column_letter(c)].width = min(max(10, widest + 2), 60)
    ws.freeze_panes = "A4"
    return ws


def write_xlsx(record: RunRecord, path: Path) -> None:
    label = label_of(record)
    wb = Workbook()
    _sheet(wb, "Summary", label, ["Item", "Value"], [list(r) for r in what_was_run(record)] + [["", ""]] + [list(r) for r in key_figures(record)] + [["Headline", record.summary.headline]], first=True)
    header, rows = trial_rows(record)
    _sheet(wb, "Trials", label, header, rows)
    header, rows = event_rows(record)
    _sheet(wb, "Events", label, header, rows)
    header, rows = alert_rows(record)
    _sheet(wb, "Alerts", label, header, rows)
    _sheet(wb, "Handovers", label, ["Title", "What happened", "Trials started", "With a result", "Skipped", "Good", "Faults", "Alerts for staff"],
           [[h.title, h.text, h.trials_started, h.trials_with_result, h.trials_skipped, h.trials_good, h.faults, h.alerts_for_staff] for h in record.handovers])
    if record.platform is not None:
        p = record.platform
        _sheet(wb, "Data and model", label, ["Part", "Line"], [["How the pieces connect", x] for x in p.pipeline] + [["Data file", x] for x in p.data_lines] + [["Modelling", x] for x in p.model_lines] + [["Trial", x] for x in p.trial_rows])
    limits = list(record.platform.limits) if record.platform is not None else (list(record.about.does_not_show) if record.about else [NOT_A_PREDICTION])
    _sheet(wb, "Limitations", label, ["What this report does not show"], [[x] for x in limits])
    wb.properties.creator = "Autonomous formulation cell (simulation)"
    wb.properties.title = "Run report"
    wb.save(path)


# ---------------------------------------------------------------- PDF
def find_browser() -> str | None:
    return next((b for b in BROWSERS if Path(b).exists()), None)


def write_pdf(html_path: Path, pdf_path: Path) -> str | None:
    """Print the report page to a PDF with an installed browser (no Python library is needed). Returns a plain note when it could not be done, else None."""
    browser = find_browser()
    if browser is None:
        return "No PDF was made: Google Chrome or Microsoft Edge was not found on this computer. Open report.html in any browser and choose Print, then Save as PDF."
    pdf_path.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf_path}", html_path.as_uri()], capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        pass
    if pdf_path.exists() and pdf_path.stat().st_size > 1000:
        return None
    return "No PDF was made: the browser did not produce one here. Open report.html in any browser and choose Print, then Save as PDF."


# ---------------------------------------------------------------- everything
def write_reports(record_location: Path | str, out_folder: Path | str | None = None, pdf: bool = True) -> ReportResult:
    """Read the run record at a folder or file and write every report file into `out_folder` (default: a folder called reports next to the record)."""
    location = Path(record_location)
    path = location / run_store.store.RECORD_NAME if location.is_dir() else location
    if not path.exists():
        raise ReportError(f"There is no run record at {path}. Double-click build_demo.bat (the proof-of-concept run) or make_platform_demo.bat (a platform run) first.")
    try:
        record = run_store.load(path)
    except Exception as exc:  # noqa: BLE001 - any unreadable record is reported the same way, in plain words
        raise ReportError(f"The run record at {path} is out of date or damaged and cannot be reported on (it was probably written by an older version). Rebuild it with build_demo.bat or make_platform_demo.bat.") from exc
    folder = Path(out_folder) if out_folder else path.parent / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    result = ReportResult(folder)
    label = label_of(record)
    page = folder / "report.html"
    page.write_text(report_html(record), encoding="utf-8")
    result.files.append(page)
    for name, (header, rows) in (("trials.csv", trial_rows(record)), ("events.csv", event_rows(record)), ("alerts.csv", alert_rows(record))):
        _write_csv(folder / name, header, rows, label)
        result.files.append(folder / name)
    write_xlsx(record, folder / "report.xlsx")
    result.files.append(folder / "report.xlsx")
    if pdf:
        note = write_pdf(page, folder / "report.pdf")
        if note:
            result.notes.append(note)
        else:
            result.files.append(folder / "report.pdf")
    return result
