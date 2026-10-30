"""Reads a data file (CSV, text, or Excel .xlsx) into a plain table of text cells, and says in plain words what it found and what it repaired.

This step only gets the table out of the file safely. It does not decide what a cell means: numbers, units, dates, missing values and
below-detection values are the next step. Nothing is ever filled in or guessed silently: every repair is a finding.

Row accounting is exact: rows read = rows kept + blank rows skipped. A value is never changed except that spaces around it are removed
(counted), and column names are tidied (counted, and the original names are kept).

Safety: files are only read. Excel files are read for their stored values (no formulas are evaluated, no macros run); macro-enabled and old
Excel formats, files whose contents unpack to something enormous, and files over the size limit are refused.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

from cellpoc.setup.files import path_is_safe, resolve_reference
from cellpoc.setup.tablefile import (DELIMITER_NAMES, EXCEL_SUFFIXES, FileProblem, MAX_COLUMNS, MAX_FILE_BYTES, MAX_ROWS, MAX_UNPACKED_BYTES,
                                     REFUSED_EXCEL, decode_bytes, detect_delimiter, excel_file_problem, match_key, normalise_name)

from .findings import Finding, has_errors, make

PROBLEM_RULES = {"excel_named_csv": "I03", "refused_excel": "I04", "excel_unreadable": "I05", "excel_too_big": "I06", "not_text": "I07",
                 "unknown_encoding": "I08", "encoding_mismatch": "I09"}
LONG_CELL = 100_000
FORMULA_PASS_MAX_BYTES = 20_000_000
_POINT = re.compile(r"^-?\d+\.\d+$")
_COMMA = re.compile(r"^-?\d+,\d+$")
# 1,234.5   1,234,567   1.234,5   1.234.567 (a lone 1,234 or 1.234 could be a decimal number, so it is not flagged)
_THOUSANDS = re.compile(r"^-?\d{1,3}(?:(?:,\d{3})+\.\d+|(?:,\d{3}){2,}|(?:\.\d{3})+,\d+|(?:\.\d{3}){2,})$")
_EDGE_SPACES = " \t   ​﻿"


@dataclass(frozen=True)
class ReadOptions:
    """How to read a file. Built from the setup's data section; the limits can be lowered (tests do this) but not raised past the defaults."""
    encoding: str = "auto"
    delimiter: str = "auto"
    decimal: str = "auto"
    sheet: str = ""
    header_row: int = 1
    line_endings: str = "any"
    max_file_bytes: int = MAX_FILE_BYTES
    max_rows: int = MAX_ROWS
    max_columns: int = MAX_COLUMNS

    @classmethod
    def from_setup(cls, data) -> "ReadOptions":
        data = data if isinstance(data, dict) else {}

        def text(key, default):
            value = data.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else default

        row = data.get("header_row")
        return cls(encoding=text("encoding", "auto"), delimiter=text("delimiter", "auto"), decimal=text("decimal", "auto"), sheet=text("sheet", ""),
                   header_row=row if isinstance(row, int) and not isinstance(row, bool) and row >= 1 else 1, line_endings=text("line_endings", "any"))


@dataclass
class FileInfo:
    name: str
    kind: str                         # "csv" or "xlsx"
    size_bytes: int
    encoding: str = ""
    encoding_how: str = ""
    bom: bool = False
    line_endings: dict = field(default_factory=dict)      # counts of "crlf", "lf", "cr"
    delimiter: str = ""               # "comma", "semicolon" or "tab"
    delimiter_how: str = ""
    decimal: str = "none"             # "point", "comma", "mixed" or "none" (what the numbers in the file use)
    sheet: str = ""
    rows_in_file: int = 0             # every row after the header, blank ones included
    rows_blank: int = 0
    rows_kept: int = 0
    rows_above_header: int = 0
    rows_padded: int = 0
    columns: int = 0
    columns_dropped_empty: int = 0
    names_tidied: int = 0
    cells_trimmed: int = 0


@dataclass
class RawTable:
    frame: pd.DataFrame               # every cell is text (or "" for empty); columns carry the tidied names
    original_names: list[str]         # the names exactly as in the file, in the same order as frame.columns
    source_rows: list[int]            # for each row of the frame, its row number in the file (the header is the header row)
    info: FileInfo
    date_cells: set[tuple[int, str]] = field(default_factory=set)   # (source row, column) pairs that were real Excel dates
    joined_infos: list = field(default_factory=list)               # what was found in each joined file (FileInfo), in the order of the setup's joins


@dataclass
class ReadResult:
    table: RawTable | None
    findings: list[Finding]

    @property
    def ok(self) -> bool:
        return self.table is not None and not has_errors(self.findings)


# ---------------------------------------------------------------- entry points
def read_table(path: Path | str, options: ReadOptions | None = None) -> ReadResult:
    """Read one file. Problems with the file are returned as findings, never raised."""
    options = options or ReadOptions()
    path = Path(path)
    name = path.name
    findings: list[Finding] = []

    def refuse(rule: str, variant: str = "", **values) -> ReadResult:
        findings.append(make(rule, variant, name, "", **values))
        return ReadResult(None, findings)

    if not path.is_file():
        return refuse("I01")
    size = path.stat().st_size
    if size > options.max_file_bytes:
        return refuse("I02", mb=f"{size / 1e6:.1f}", limit=f"{options.max_file_bytes / 1e6:.0f}")
    suffix = path.suffix.lower()
    if suffix in REFUSED_EXCEL:
        return refuse("I04", what=REFUSED_EXCEL[suffix])
    info = FileInfo(name, "xlsx" if suffix in EXCEL_SUFFIXES else "csv", size)
    marks: dict[int, set[int]] = {}
    try:
        if info.kind == "xlsx":
            rows = _excel_rows(path, options, info, findings, marks)
        else:
            rows = _text_rows(path, options, info, findings)
    except FileProblem as problem:
        values = dict(problem.values)
        if problem.code == "refused_excel":
            values.setdefault("what", "a kind of Excel file that is not read")
        return refuse(PROBLEM_RULES.get(problem.code, "I07"), **values)
    except _TooLong as error:
        return refuse("I13", error.which, limit=f"{error.limit:,}", n=error.n)
    except _Refusal as error:
        return refuse(error.rule, error.variant, **error.values)
    return _build(rows, marks, options, info, findings)


def read_setup_table(setup: dict, base_dir: Path | None, root: Path) -> ReadResult:
    """Read the experiments file a setup names, the way the setup says (file name resolved inside the project only)."""
    data = setup.get("data") if isinstance(setup, dict) else None
    reference = data.get("experiments_file") if isinstance(data, dict) else None
    where = resolve_reference(reference, base_dir, root) if isinstance(reference, str) and path_is_safe(reference) else None
    if where is None:
        return ReadResult(None, [make("I01", "", reference if isinstance(reference, str) and reference else "the experiments file")])
    return read_table(where, ReadOptions.from_setup(data))


# ---------------------------------------------------------------- getting rows out of the two kinds of file
class _TooLong(Exception):
    def __init__(self, which: str, limit: int, n: int = 0):
        self.which, self.limit, self.n = which, limit, n


class _Refusal(Exception):
    def __init__(self, rule: str, variant: str = "", **values):
        self.rule, self.variant, self.values = rule, variant, values


def _text_rows(path: Path, options: ReadOptions, info: FileInfo, findings: list[Finding]) -> list[list[str]]:
    name = info.name
    decoded = decode_bytes(path.read_bytes(), options.encoding)
    info.encoding, info.encoding_how, info.bom = decoded.encoding, decoded.how, decoded.bom
    if decoded.bom:
        findings.append(make("I23", "", name, "", encoding=decoded.encoding))
    for code in decoded.notes:
        findings.append(make("I22" if code == "utf16_without_mark" else "I21", "", name))
    text = decoded.text
    crlf = text.count("\r\n")
    info.line_endings = {"crlf": crlf, "lf": text.count("\n") - crlf, "cr": text.count("\r") - crlf}
    present = [k for k, v in info.line_endings.items() if v]
    if len(present) > 1:
        findings.append(make("I24", "", name, "", counts=", ".join(f"{info.line_endings[k]:,} {label}" for k, label in
                                                                    (("crlf", "Windows (CRLF)"), ("lf", "Unix (LF)"), ("cr", "old Mac (CR)")) if info.line_endings[k])))
    dominant = max(info.line_endings, key=info.line_endings.get) if present else ""
    if options.line_endings in ("lf", "crlf") and dominant and dominant != options.line_endings:
        findings.append(make("I25", "", name, "", declared={"lf": "Unix (LF)", "crlf": "Windows (CRLF)"}[options.line_endings],
                             found={"crlf": "Windows (CRLF)", "lf": "Unix (LF)", "cr": "old Mac (CR)"}[dominant]))
    delimiter, how = detect_delimiter(text, options.delimiter)
    info.delimiter, info.delimiter_how = DELIMITER_NAMES[delimiter], how
    if how == "detected":
        findings.append(make("I20", "", name, "", name=info.delimiter))
    rows: list[list[str]] = []
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    long_cell_line = None
    try:
        for cells in reader:
            rows.append(cells)
            if len(rows) > options.max_rows + options.header_row:
                raise _TooLong("rows", options.max_rows)
            if long_cell_line is None and any(len(cell) > LONG_CELL for cell in cells):
                long_cell_line = (reader.line_num, max(len(c) for c in cells))
    except csv.Error:
        raise _Refusal("I17", line=reader.line_num) from None
    if long_cell_line:
        findings.append(make("I16", "", name, "", line=long_cell_line[0], n=f"{long_cell_line[1]:,}"))
    if how == "declared" and rows:
        widest = max(len(r) for r in rows[: options.header_row + 50])
        other, _ = detect_delimiter(text, "auto")
        if widest == 1 and other != delimiter:
            findings.append(make("I18", "", name, "", declared=info.delimiter, found=DELIMITER_NAMES[other]))
    return rows


def _excel_text(value) -> tuple[str, bool]:
    """(the cell as text, whether it was a real Excel date)."""
    if value is None:
        return "", False
    if isinstance(value, bool):
        return ("TRUE" if value else "FALSE"), False
    if isinstance(value, int):
        return str(value), False
    if isinstance(value, float):
        return (str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)), False
    if isinstance(value, datetime):
        return (value.date().isoformat() if value.time() == time(0, 0) else value.isoformat(sep=" ")), True
    if isinstance(value, date):
        return value.isoformat(), True
    if isinstance(value, time):
        return value.isoformat(), False
    return str(value), False


def _excel_rows(path: Path, options: ReadOptions, info: FileInfo, findings: list[Finding], marks: dict[int, set[int]]) -> list[list[str]]:
    name = info.name
    problem = excel_file_problem(path)
    if problem:
        raise FileProblem(problem)
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as error:                      # noqa: BLE001 - any failure to open the file is reported in plain words
        raise FileProblem("excel_unreadable") from error
    try:
        names = workbook.sheetnames
        if options.sheet:
            if options.sheet not in names:
                raise _Refusal("I10", sheet=options.sheet, sheets=", ".join(names))
            sheet = workbook[options.sheet]
        else:
            visible = [n for n in names if workbook[n].sheet_state == "visible"] or names
            sheet = workbook[visible[0]]
        info.sheet = sheet.title
        rows: list[list[str]] = []
        for number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
            if number > options.max_rows + options.header_row:
                raise _TooLong("rows", options.max_rows)
            cells = []
            for column, value in enumerate(values):
                text, is_date = _excel_text(value)
                cells.append(text)
                if is_date:
                    marks.setdefault(number, set()).add(column)
            rows.append(cells)
        while rows and not any(cell.strip() for cell in rows[-1]):       # Excel often reports many empty rows at the end
            rows.pop()
        dates = sum(len(v) for v in marks.values())
        if dates:
            findings.append(make("I34", "", name, "", n=f"{dates:,}"))
        if info.size_bytes <= FORMULA_PASS_MAX_BYTES:
            empty_formulas = _formulas_without_value(path, sheet.title, rows)
            if empty_formulas:
                findings.append(make("I33", "", name, "", n=f"{empty_formulas:,}"))
        return rows
    finally:
        workbook.close()


def _formulas_without_value(path: Path, sheet_name: str, values: list[list[str]]) -> int:
    """How many formula cells have no saved result (they were read as empty). Formulas are looked at, never evaluated."""
    from openpyxl import load_workbook

    count = 0
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        for r, row in enumerate(workbook[sheet_name].iter_rows(), start=0):
            for c, cell in enumerate(row):
                if getattr(cell, "data_type", None) == "f" and (r >= len(values) or c >= len(values[r]) or not values[r][c].strip()):
                    count += 1
    finally:
        workbook.close()
    return count


# ---------------------------------------------------------------- from rows to a table
def _trim(cell: str) -> str:
    return cell.strip(_EDGE_SPACES)


def _build(rows: list[list[str]], marks: dict[int, set[int]], options: ReadOptions, info: FileInfo, findings: list[Finding]) -> ReadResult:
    name = info.name
    if not rows or not any(cell.strip() for row in rows for cell in row):
        findings.append(make("I11", "", name))
        return ReadResult(None, findings)
    if len(rows) < options.header_row:
        findings.append(make("I12", "", name, "", row=options.header_row, rows=len(rows)))
        return ReadResult(None, findings)
    info.rows_above_header = options.header_row - 1
    if info.rows_above_header:
        findings.append(make("I31", "", name, "", n=info.rows_above_header))
    header = [normalise_name(cell) for cell in rows[options.header_row - 1]]
    original = [cell for cell in rows[options.header_row - 1]]
    if len(header) > options.max_columns:
        findings.append(make("I13", "columns", name, "", n=f"{len(header):,}", limit=f"{options.max_columns:,}"))
        return ReadResult(None, findings)
    width = len(header)

    body: list[tuple[int, list[str]]] = []          # (row number in the file, cells)
    blank = padded = trimmed = 0
    first_short = None
    too_long: list[tuple[int, int]] = []
    for offset, cells in enumerate(rows[options.header_row:], start=options.header_row + 1):
        info.rows_in_file += 1
        cleaned = []
        for cell in cells:
            stripped = _trim(cell)
            trimmed += stripped != cell
            cleaned.append(stripped)
        if not any(cleaned):
            blank += 1
            continue
        if len(cleaned) > width:
            extra = cleaned[width:]
            if any(extra):
                too_long.append((offset, sum(1 for cell in cleaned if cell)))
                continue
            cleaned = cleaned[:width]
        elif len(cleaned) < width:
            padded += 1
            first_short = first_short or offset
            cleaned += [""] * (width - len(cleaned))
        body.append((offset, cleaned))
    if too_long:
        findings.append(make("I15", "", name, "", row=too_long[0][0], have=too_long[0][1], want=width, count=len(too_long)))
        return ReadResult(None, findings)
    info.rows_blank, info.rows_padded, info.cells_trimmed, info.rows_kept = blank, padded, trimmed, len(body)
    if blank:
        findings.append(make("I29", "", name, "", n=f"{blank:,}"))
    if padded:
        findings.append(make("I30", "", name, "", n=f"{padded:,}", row=first_short))
    if trimmed:
        findings.append(make("I32", "", name, "", n=f"{trimmed:,}"))

    # which columns to keep, and what to call them
    keep: list[int] = []
    names: list[str] = []
    unnamed: list[str] = []
    for index in range(width):
        has_values = any(row[index] for _, row in body)
        if not header[index]:
            if not has_values:
                info.columns_dropped_empty += 1
                continue
            label = f"unnamed_column_{index + 1}"
            unnamed.append(label)
            header[index] = label
        keep.append(index)
        names.append(header[index])
    seen: dict[str, str] = {}
    for column in names:
        key = match_key(column)
        if key in seen:
            findings.append(make("I14", "", name, "", first=seen[key], second=column))
            return ReadResult(None, findings)
        seen[key] = column
    if info.columns_dropped_empty:
        findings.append(make("I28", "", name, "", n=info.columns_dropped_empty))
    if unnamed:
        findings.append(make("I27", "", name, "", n=len(unnamed), names=", ".join(unnamed[:3]) + (", ..." if len(unnamed) > 3 else "")))
    changed = [(original[i], header[i]) for i in keep if original[i] != header[i] and not header[i].startswith("unnamed_column_")]
    info.names_tidied = len(changed)
    if changed:
        old, new = changed[0]
        findings.append(make("I26", "", name, "", n=len(changed), old=old, new=new))

    frame = pd.DataFrame([[row[i] for i in keep] for _, row in body], columns=names, dtype=object)
    info.columns = len(names)
    source_rows = [offset for offset, _ in body]
    kept_rows, position = set(source_rows), {c: i for i, c in enumerate(keep)}
    date_cells = {(offset, names[position[c]]) for offset, columns in marks.items() if offset in kept_rows for c in columns if c in position}
    _look_at_numbers(frame, options, info, findings)
    findings.append(make("I40", "", name, "", rows=f"{len(body):,}", columns=f"{len(names):,}", how=_how(info)))
    order = {"error": 0, "warning": 1, "note": 2}
    findings.sort(key=lambda f: order[f.level])
    return ReadResult(RawTable(frame, [original[i] for i in keep], source_rows, info, date_cells), findings)


def _how(info: FileInfo) -> str:
    if info.kind == "xlsx":
        return f"from the Excel sheet '{info.sheet}' of {info.name}"
    return f"from {info.name}: {info.encoding}, columns separated by a {info.delimiter}"


def _look_at_numbers(frame: pd.DataFrame, options: ReadOptions, info: FileInfo, findings: list[Finding]) -> None:
    """Which decimal mark the numbers use. Reported only; turning text into numbers is the next step."""
    points = commas = thousands = 0
    point_example = comma_example = thousand_example = ""
    for column in frame.columns:
        cells = frame[column].astype(str)
        p, c, t = cells.str.fullmatch(_POINT.pattern), cells.str.fullmatch(_COMMA.pattern), cells.str.fullmatch(_THOUSANDS.pattern)
        if p.any() and not point_example:
            point_example = cells[p].iloc[0]
        if c.any() and not comma_example:
            comma_example = cells[c].iloc[0]
        if t.any() and not thousand_example:
            thousand_example = cells[t].iloc[0]
        points, commas, thousands = points + int(p.sum()), commas + int(c.sum()), thousands + int(t.sum())
    info.decimal = "mixed" if points and commas else ("point" if points else ("comma" if commas else "none"))
    name = info.name
    declared = options.decimal
    if commas and not points:
        if declared == "point":
            findings.append(make("I36", "", name, "", declared="point", n=f"{commas:,}", example=comma_example, found="comma"))
        else:
            findings.append(make("I35", "", name, "", n=f"{commas:,}", example=comma_example))
    elif points and not commas and declared == "comma":
        findings.append(make("I36", "", name, "", declared="comma", n=f"{points:,}", example=point_example, found="point"))
    elif points and commas:
        findings.append(make("I37", "", name, "", points=f"{points:,}", commas=f"{commas:,}", example=comma_example))
    if thousands:
        findings.append(make("I38", "", name, "", n=f"{thousands:,}", example=thousand_example))
