"""Looking inside a data file just far enough to know how to read it: its text encoding, its column separator, and its column names.

Shared by the setup checker (to say whether a column the setup names really exists) and by the data reader (cellpoc.ingest), so
both agree. Nothing here changes a file. Files are only read, never executed; Excel files are read for their stored values only
(no macros, no formulas evaluated) and are refused if their packed size looks like a decompression bomb.
"""
from __future__ import annotations

import codecs
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILE_BYTES = 100_000_000           # a data file bigger than this is refused
MAX_UNPACKED_BYTES = 500_000_000       # an Excel file whose contents unpack to more than this is refused
MAX_ROWS = 2_000_000
MAX_COLUMNS = 5_000
HEADER_SAMPLE_BYTES = 2_000_000
EXCEL_SUFFIXES = {".xlsx"}
REFUSED_EXCEL = {".xlsm": "an Excel file with macros", ".xlsb": "a binary Excel file", ".xls": "an old Excel file (.xls)"}
DELIMITERS = {"comma": ",", "semicolon": ";", "tab": "\t"}
DELIMITER_NAMES = {v: k for k, v in DELIMITERS.items()}
_ODD_SPACES = re.compile(r"[   ​‌‍﻿\t\r\n\f\v]+")


# ---------------------------------------------------------------- column names
def normalise_name(name) -> str:
    """A column name as a person would read it: odd spaces and tabs become spaces, ends trimmed, runs of spaces collapsed."""
    return re.sub(r" +", " ", _ODD_SPACES.sub(" ", str(name))).strip()


def match_key(name) -> str:
    """What two column names are compared by: normalised, ignoring capital letters."""
    return normalise_name(name).casefold()


# ---------------------------------------------------------------- text encoding
class FileProblem(Exception):
    """A file cannot be read as a table. `code` names the plain-English message to show; `values` fill it in."""

    def __init__(self, code: str, **values):
        super().__init__(code)
        self.code = code
        self.values = values


@dataclass
class Decoded:
    text: str
    encoding: str                 # the encoding actually used, e.g. "utf-8", "utf-16-le", "windows-1252"
    how: str                      # "bom", "declared", "detected" or "fallback"
    bom: bool = False
    notes: list[str] = field(default_factory=list)


def _nul_share(raw: bytes) -> float:
    return raw.count(b"\x00") / max(len(raw), 1)


def decode_bytes(raw: bytes, declared: str | None = "auto") -> Decoded:
    """Turn the bytes of a text file into text. A byte-order mark wins; then the declared encoding; then detection.

    Raises FileProblem when the bytes are not text at all, or do not fit the declared encoding.
    """
    declared = (declared or "auto").strip().lower()
    if raw[:2] == b"PK":
        raise FileProblem("excel_named_csv")
    if raw[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return Decoded(raw.decode("utf-32"), "utf-32", "bom", True)
    if raw[:3] == b"\xef\xbb\xbf":
        return Decoded(raw[3:].decode("utf-8", errors="strict"), "utf-8", "bom", True) if _valid(raw[3:], "utf-8") else _bad(declared, "utf-8")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        name = "utf-16-le" if raw[:2] == b"\xff\xfe" else "utf-16-be"
        return Decoded(raw[2:].decode(name, errors="strict"), name, "bom", True) if _valid(raw[2:], name) else _bad(declared, name)
    if declared not in ("auto", ""):
        try:
            codecs.lookup(declared)
        except LookupError:
            raise FileProblem("unknown_encoding", encoding=declared) from None
        if not _valid(raw, declared):
            raise FileProblem("encoding_mismatch", encoding=declared)
        return Decoded(raw.decode(declared), declared, "declared")
    if len(raw) >= 4 and _nul_share(raw) > 0.2:
        name = "utf-16-le" if raw[1::2].count(b"\x00") > raw[0::2].count(b"\x00") else "utf-16-be"
        if _valid(raw, name):
            return Decoded(raw.decode(name), name, "detected", False, ["utf16_without_mark"])
        raise FileProblem("not_text")
    if _valid(raw, "utf-8"):
        text = raw.decode("utf-8")
        if _looks_binary(text):
            raise FileProblem("not_text")
        return Decoded(text, "utf-8", "detected")
    text = raw.decode("windows-1252", errors="replace")
    if _looks_binary(text):
        raise FileProblem("not_text")
    return Decoded(text, "windows-1252", "fallback", False, ["fallback_encoding"])


def _bad(declared: str, found: str):
    raise FileProblem("encoding_mismatch", encoding=found)


def _valid(raw: bytes, encoding: str) -> bool:
    try:
        raw.decode(encoding)
        return True
    except (UnicodeDecodeError, LookupError):
        return False


def _looks_binary(text: str) -> bool:
    if not text:
        return False
    odd = sum(1 for ch in text[:200_000] if (ord(ch) < 32 and ch not in "\t\r\n\f") or ch == "\x7f")
    return odd / min(len(text), 200_000) > 0.01


# ---------------------------------------------------------------- column separator
def detect_delimiter(text: str, declared: str | None = "auto") -> tuple[str, str]:
    """(the separator character, how it was chosen: 'declared' or 'detected')."""
    declared = (declared or "auto").strip().lower()
    if declared in DELIMITERS:
        return DELIMITERS[declared], "declared"
    sample = text[:400_000]
    best, best_score = ",", -1.0
    for candidate in DELIMITERS.values():
        widths = []
        try:
            for row in csv.reader(io.StringIO(sample, newline=""), delimiter=candidate):
                if row:
                    widths.append(len(row))
                if len(widths) >= 60:
                    break
        except csv.Error:
            continue
        if not widths:
            continue
        modal = max(set(widths), key=widths.count)
        score = (widths.count(modal) / len(widths)) * (1.0 if modal > 1 else 0.0) + (min(modal, 50) / 5000)
        if score > best_score:
            best, best_score = candidate, score
    return best, "detected"


# ---------------------------------------------------------------- header of a file
@dataclass
class Header:
    names: list[str]
    kind: str                     # "csv" or "xlsx"
    encoding: str = ""
    delimiter: str = ""


def excel_file_problem(path: Path) -> str | None:
    """Why an Excel file must not be opened (None when it is fine to read)."""
    suffix = path.suffix.lower()
    if suffix in REFUSED_EXCEL:
        return "refused_excel"
    try:
        with zipfile.ZipFile(path) as z:
            unpacked = sum(i.file_size for i in z.infolist())
            if unpacked > MAX_UNPACKED_BYTES or len(z.infolist()) > 10_000:
                return "excel_too_big"
    except (zipfile.BadZipFile, OSError):
        return "excel_unreadable"
    return None


def read_header(path: Path, data: dict) -> Header | None:
    """The column names in the first row of a file (or of the row the setup names as the header). None if it cannot be read quickly.

    Never raises: the data reader reports the reason in plain words; the setup checker just skips what it cannot look at.
    """
    try:
        header_row = data.get("header_row") if isinstance(data.get("header_row"), int) and not isinstance(data.get("header_row"), bool) else 1
        header_row = max(header_row, 1)
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        if path.suffix.lower() in EXCEL_SUFFIXES:
            return _excel_header(path, data, header_row)
        if path.suffix.lower() in REFUSED_EXCEL:
            return None
        raw = path.read_bytes()[:HEADER_SAMPLE_BYTES]
        decoded = decode_bytes(raw, data.get("encoding") if isinstance(data.get("encoding"), str) else "auto")
        delimiter, _ = detect_delimiter(decoded.text, data.get("delimiter") if isinstance(data.get("delimiter"), str) else "auto")
        rows = csv.reader(io.StringIO(decoded.text, newline=""), delimiter=delimiter)
        for number, row in enumerate(rows, start=1):
            if number == header_row:
                return Header([normalise_cell(cell) for cell in row], "csv", decoded.encoding, delimiter)
        return None
    except (OSError, FileProblem, csv.Error, UnicodeError, ValueError):
        return None


def normalise_cell(cell) -> str:
    return "" if cell is None else str(cell)


def _excel_header(path: Path, data: dict, header_row: int) -> Header | None:
    if excel_file_problem(path):
        return None
    from openpyxl import load_workbook          # imported here: only needed when an Excel file is really read

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_name = data.get("sheet") if isinstance(data.get("sheet"), str) and data.get("sheet") else None
        if sheet_name is not None and sheet_name not in workbook.sheetnames:
            return None
        sheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]
        for row in sheet.iter_rows(min_row=header_row, max_row=header_row, values_only=True):
            return Header([normalise_cell(v) for v in row], "xlsx")
        return None
    finally:
        workbook.close()
