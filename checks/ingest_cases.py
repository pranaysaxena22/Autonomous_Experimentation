"""One test for every message the data reader can show: a small file made to cause exactly that finding.

Each case builds a tiny file in a temporary folder, reads it, and checks that the expected message appears at the expected level, in plain
English. docs/ingest_messages.md is generated from these cases, and the health check fails if any message has no case.
"""
from __future__ import annotations

import io
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from openpyxl import Workbook

from cellpoc.ingest import CATALOGUE, CleanResult, Finding, ReadOptions, ReadResult, clean_table, read_table
from cellpoc.setup import tablefile

BASE = "id,drug_pct,filler_pct,note\nE1,10.5,60,a\nE2,12.0,58,b\nE3,14.1,55,c\n"

# Words that belong to programmers; quoted text is the person's own and is not judged.
TECHNICAL = re.compile(r"\b(schema|null|nonetype|traceback|exception|keyerror|typeerror|valueerror|dataframe|pandas|openpyxl|stack trace|undefined|nan)\b|<class|\{|\}",
                       re.IGNORECASE)


def wording_problems(finding: Finding) -> list[str]:
    plain = re.sub(r"'[^']*'", "''", finding.message)
    found = []
    if TECHNICAL.search(plain):
        found.append("contains technical wording: " + finding.message)
    if not finding.text.strip() or not finding.message.startswith(finding.where):
        found.append("is empty or does not start with the file name")
    return found


def read_bytes(content: bytes, name: str = "t.csv", **options) -> ReadResult:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / name
        path.write_bytes(content)
        return read_table(path, ReadOptions(**options))


def read_text(text: str, name: str = "t.csv", **options) -> ReadResult:
    return read_bytes(text.encode("utf-8"), name, **options)


def xlsx_bytes(rows: list[list], title: str = "Data", also: tuple[str, ...] = ()) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    for extra in also:
        workbook.create_sheet(extra)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@dataclass
class Case:
    rule: str
    variant: str
    what: str
    run: Callable[[], ReadResult]


CASES: list[Case] = []


def case(rule: str, variant: str, what: str):
    def register(function: Callable[[], ReadResult]):
        CASES.append(Case(rule, variant, what, function))
        return function
    return register


# ------------------------------------------------------------------ the file cannot be used
@case("I01", "", "a file name that does not exist")
def _():
    return read_table(Path(tempfile.gettempdir()) / "no_such_file_for_the_test.csv")


@case("I02", "", "a file bigger than the limit (the limit is lowered to 10 bytes for the test)")
def _():
    return read_text(BASE, max_file_bytes=10)


@case("I03", "", "an Excel file saved with a .csv name")
def _():
    return read_bytes(xlsx_bytes([["a", "b"], [1, 2]]), "t.csv")


@case("I04", "", "an old Excel file (.xls)")
def _():
    return read_bytes(b"\xd0\xcf\x11\xe0not really excel", "t.xls")


@case("I05", "", "an .xlsx file that is not a real Excel file")
def _():
    return read_bytes(b"this is not a zip file", "t.xlsx")


@case("I06", "", "an Excel file that unpacks to more than the limit (lowered to 10 bytes for the test)")
def _():
    original = tablefile.MAX_UNPACKED_BYTES
    tablefile.MAX_UNPACKED_BYTES = 10
    try:
        return read_bytes(xlsx_bytes([["a", "b"], [1, 2]]), "t.xlsx")
    finally:
        tablefile.MAX_UNPACKED_BYTES = original


@case("I07", "", "a file of random binary bytes named .csv")
def _():
    return read_bytes(bytes(range(256)) * 20)


@case("I08", "", "a text encoding that does not exist")
def _():
    return read_text(BASE, encoding="klingon")


@case("I09", "", "a Central-European file declared as utf-8")
def _():
    return read_bytes(b"id;\xe8\n1;2\n", encoding="utf-8")


@case("I10", "", "a sheet name the workbook does not have")
def _():
    return read_bytes(xlsx_bytes([["a", "b"], [1, 2]]), "t.xlsx", sheet="Nope")


@case("I11", "", "an empty file")
def _():
    return read_bytes(b"")


@case("I12", "", "a header row number beyond the end of the file")
def _():
    return read_text("a,b\n1,2\n", header_row=5)


@case("I13", "rows", "more rows than the limit (lowered to 2 for the test)")
def _():
    return read_text(BASE, max_rows=2)


@case("I13", "columns", "more columns than the limit (lowered to 2 for the test)")
def _():
    return read_text(BASE, max_columns=2)


@case("I14", "", "two column names that differ only by a space and a capital letter")
def _():
    return read_text("a,A ,b\n1,2,3\n")


@case("I15", "", "a row with more filled cells than the header has columns")
def _():
    return read_text("a,b\n1,2,3\n")


@case("I17", "", "a cell far larger than any real value")
def _():
    return read_text("a,b\n" + "x" * 200_000 + ",1\n")


# ------------------------------------------------------------------ read, with an assumption or repair
@case("I16", "", "a very long cell (an unclosed quote would look like this)")
def _():
    return read_text("a,b\n" + "x" * 120_000 + ",1\n")


@case("I18", "", "a setup that says comma for a semicolon file")
def _():
    return read_text("a;b;c\n1;2;3\n", delimiter="comma")


@case("I21", "", "a file that is not valid UTF-8 and is not declared")
def _():
    return read_bytes(b"id,n\n1,\xe8\n")


@case("I25", "", "a setup that says Windows line endings for a file with Unix ones")
def _():
    return read_text(BASE, line_endings="crlf")


@case("I27", "", "a column with values but no name")
def _():
    return read_text("a,,c\n1,2,3\n")


@case("I30", "", "a row with fewer cells than the header")
def _():
    return read_text("a,b,c\n1,2\n3,4,5\n")


@case("I33", "", "an Excel formula whose result was never saved")
def _():
    return read_bytes(xlsx_bytes([["a", "b"], [1, "=1+1"]]), "t.xlsx")


@case("I36", "", "a setup that says decimal point for numbers written with commas")
def _():
    return read_text("a;b\n1,5;2,5\n", decimal="point")


@case("I37", "", "numbers written both ways")
def _():
    return read_text("a;b\n1,5;2.5\n")


@case("I38", "", "numbers with a thousands separator")
def _():
    return read_text("a;b\n1,234.5;3\n")


# ------------------------------------------------------------------ information
@case("I20", "", "a file whose separator is detected")
def _():
    return read_text(BASE)


@case("I22", "", "UTF-16 text with no byte-order mark")
def _():
    return read_bytes(BASE.encode("utf-16-le"))


@case("I23", "", "a file that starts with a byte-order mark")
def _():
    return read_bytes(b"\xef\xbb\xbf" + BASE.encode("utf-8"))


@case("I24", "", "a file mixing Windows and Unix line endings")
def _():
    return read_bytes(b"a,b\r\n1,2\n3,4\r\n")


@case("I26", "", "column names with extra spaces")
def _():
    return read_text(" a ,B  b\n1,2\n")


@case("I28", "", "a column with no name and no values")
def _():
    return read_text("a,b,\n1,2,\n3,4,\n")


@case("I29", "", "blank rows in the middle of the data")
def _():
    return read_text("a,b\n1,2\n\n3,4\n")


@case("I31", "", "a title row above the header (header_row set to 2)")
def _():
    return read_text("A title\na,b\n1,2\n", header_row=2)


@case("I32", "", "values with spaces around them")
def _():
    return read_text("a,b\n 1, 2 \n")


@case("I34", "", "a real Excel date cell")
def _():
    return read_bytes(xlsx_bytes([["when", "x"], [datetime(2025, 1, 6), 1]]), "t.xlsx")


@case("I35", "", "numbers written with a decimal comma")
def _():
    return read_text("a;b\n1,5;2,5\n")


@case("I40", "", "any file that was read (the summary)")
def _():
    return read_text(BASE)


# ------------------------------------------------------------------ Stage 2c: from text to typed values
def clean_text(text: str, data: dict | None = None, **setup) -> CleanResult:
    """Read a small CSV and clean it with a setup made of `data` and anything else given (ingredients, targets ...)."""
    data = {"column_map": {}, **(data or {})}
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "t.csv"
        path.write_bytes(text.encode("utf-8"))
        read = read_table(path, ReadOptions.from_setup(data))
    return clean_table(read, {"data": data, **setup})


DRUG = {"ingredients": [{"id": "drug_pct", "label": "Drug", "unit": "%"}]}


@case("I41", "", "a mapped column the file does not have (with a near match suggested)")
def _():
    return clean_text("id,dissolution_pct\n1,80\n", {"column_map": {"dissolution_pt": "dissolution_pct"}})


@case("I42", "", "two columns mapped to the same ID")
def _():
    return clean_text("a,b\n1,2\n", {"column_map": {"a": "x_pct", "b": "x_pct"}})


@case("I43", "", "a number column that is mostly text")
def _():
    return clean_text("drug\nabc\ndef\n1\n", {"column_map": {"drug": "drug_pct"}}, **DRUG)


@case("I44", "", "a missing value when the setup says to stop")
def _():
    return clean_text("id,drug\nE1,1\nE2,\nE3,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"}, "missing_values": {"policy": "fail"}}, **DRUG)


@case("I45", "", "dates that mostly cannot be read")
def _():
    return clean_text("when,drug\nx,1\ny,2\n2025-01-01,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "yyyy-mm-dd"}}, **DRUG)


@case("I47", "weight_column", "a total weight that is not in the table")
def _():
    return clean_text("a_mg\n1\n", {"column_map": {"a_mg": "a_mg"}, "composition": {"total_weight": "ghost_mg"}})


@case("I47", "name_clash", "a converted percentage whose ID already exists")
def _():
    return clean_text("w,a,b\n10,5,5\n", {"column_map": {"w": "w_mg", "a": "a_mg", "b": "a_pct"}, "composition": {"total_weight": "w_mg"}})


@case("I46", "", "a few values in a number column that are not numbers")
def _():
    return clean_text("drug\n1\n2\n3\nx\n", {"column_map": {"drug": "drug_pct"}}, **DRUG)


@case("I48", "", "a few dates that cannot be read")
def _():
    return clean_text("when,drug\n2025-01-01,1\n2025-01-02,2\n2025-02-30,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "yyyy-mm-dd"}}, **DRUG)


@case("I49", "", "dates with no date format in the setup")
def _():
    return clean_text("when,drug\n2025-01-01,1\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}}, **DRUG)


@case("I50", "", "a percentage above 100")
def _():
    return clean_text("drug\n10\n150\n", {"column_map": {"drug": "drug_pct"}}, **DRUG)


@case("I51", "", "a column whose unit is marked as assumed")
def _():
    return clean_text("a\n1\n", {"column_map": {"a": "a_mg"}, "assumed_units": [{"id": "a_mg", "why": "unit assumed, not confirmed by the dataset's dictionary"}]})


HARDNESS = {"value_column": "h", "unit_column": "u", "to": "hardness_kp", "conversions": {"kP": {"divide_by": 1}, "N": {"divide_by": 9.807}}}


@case("I52", "", "a hardness conversion marked as assumed")
def _():
    conv = {"kg/cm2": {"divide_by": 1, "status": "assumed", "note": "taken as kilopond"}, "kP": {"divide_by": 1}}
    return clean_text("h\n5\n6\n", {"column_map": {}, "hardness": {"value_column": "h", "unit": "kg/cm2", "to": "hardness_kp", "conversions": conv}})


@case("I53", "", "values written below a limit, handled by the setup's rule (inside the cell)")
def _():
    return clean_text("x\n<0.05\n0.3\n", {"column_map": {"x": "x_pct"}, "below_detection": {"rule": "use_half_limit"}})


@case("I54", "", "a value written as above a limit")
def _():
    return clean_text("x\n>100\n5\n", {"column_map": {"x": "x_pct"}})


@case("I55", "", "a value written as below a limit when the setup has no rule")
def _():
    return clean_text("x\n<0.05\n0.3\n", {"column_map": {"x": "x_pct"}})


@case("I56", "", "a row marked below the limit whose value is not the limit")
def _():
    below = {"note_column": "n", "marker": "<0.05", "quantity": "x_pct", "limit": 0.05, "rule": "use_limit_and_flag"}
    return clean_text("x,n\n0.03,<0.05\n0.4,\n", {"column_map": {"x": "x_pct"}, "below_detection": below})


@case("I57", "", "a hardness unit with no conversion")
def _():
    return clean_text("h,u\n5,kP\n6,lbf\n", {"column_map": {}, "hardness": HARDNESS})


@case("I58", "dropped", "rows dropped because a value is missing")
def _():
    return clean_text("id,drug\nE1,1\nE2,\nE3,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"}, "missing_values": {"policy": "drop_row"}}, **DRUG)


COMPOSITION = {"column_map": {"w": "w_mg", "a": "a_mg", "b": "b_mg"}, "composition": {"total_weight": "w_mg", "tolerance_pct": 2}}


@case("I59", "flagged", "amounts that fall short of the total weight by more than the tolerance")
def _():
    return clean_text("w,a,b\n100,60,30\n100,60,40\n", COMPOSITION)


@case("I59", "ok", "amounts that add up to the total weight")
def _():
    return clean_text("w,a,b\n100,60,40\n100,59,40\n", COMPOSITION)


@case("I60", "", "a row whose total weight is zero")
def _():
    return clean_text("w,a,b\n0,60,40\n100,60,40\n", COMPOSITION)


@case("I61", "", "a file with no experiment ID column")
def _():
    return clean_text("drug\n1\n", {"column_map": {"drug": "drug_pct"}}, **DRUG)


@case("I62", "", "columns in the file that the setup does not use")
def _():
    return clean_text("drug,other\n1,2\n", {"column_map": {"drug": "drug_pct"}}, **DRUG)


@case("I63", "", "amounts converted to a percentage of the total weight")
def _():
    return clean_text("w,a,b\n100,60,40\n", COMPOSITION)


@case("I64", "", "text meaning 'no value' that the setup lists")
def _():
    return clean_text("drug\n#N/A\n2\n", {"column_map": {"drug": "drug_pct"}, "missing_markers": ["#N/A"]}, **DRUG)


@case("I65", "range", "dates read, with their range")
def _():
    return clean_text("when,drug\n2025-01-01,1\n2025-01-09,2\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "yyyy-mm-dd"}}, **DRUG)


@case("I65", "month_only", "dates that only give a month and year (Slovenian month names)")
def _():
    return clean_text("when,drug\nnov.18,1\nmaj.19,2\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "mon.yy", "language": "sl"}}, **DRUG)


@case("I66", "", "mapped columns that the setup does not name")
def _():
    return clean_text("a,b\n1,x\n", {"column_map": {"a": "a_pct", "b": "b_text"}})


@case("I68", "", "a column whose unit in the file differs from the setup's, with no conversion")
def _():
    return clean_text("drug\n10\n", {"column_map": {"drug": "drug_pct"}, "column_units": {"drug_pct": "mg"}}, **DRUG)


@case("I70", "", "hardness values converted from newtons to kP")
def _():
    return clean_text("h,u\n98.07,N\n5,kP\n", {"column_map": {}, "hardness": HARDNESS})


# ------------------------------------------------------------------ Stage 2d: two-digit years, failed runs, replicates, joins
def clean_files(files: dict[str, str], data: dict, **setup) -> CleanResult:
    """Write several small files into a temporary project and read and clean the first one with its joins, the way a setup would."""
    from cellpoc.ingest import read_and_clean

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder).resolve()
        for name, text in files.items():
            (root / name).write_bytes(text.encode("utf-8"))
        main = next(iter(files))
        return read_and_clean({"data": {"experiments_file": main, **data}, **setup}, root, root)


@case("I71", "", "dates written with a 2-digit year (nov.18)")
def _():
    return clean_text("when,drug\nnov.18,1\njan.70,2\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "mon.yy", "language": "sl"}}, **DRUG)


REPEATS = {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"}, "replicates": {"group_by": ["experiment_id"], "rule": "mean", "keep_individual_rows_for_noise_estimate": True}}


@case("I72", "", "a replicate grouping that names a column the table does not have")
def _():
    return clean_text("id,drug\nE1,1\n", {**REPEATS, "replicates": {"group_by": ["nope"], "rule": "mean"}}, **DRUG)


@case("I73", "", "replicate rows that disagree on a text column")
def _():
    return clean_text("id,drug,grade\nE1,1,A\nE1,2,B\n", {**REPEATS, "column_map": {"drug": "drug_pct", "grade": "grade"}},
                      context_factors=[{"id": "grade"}], **DRUG)


@case("I74", "", "replicate rows combined into one row each")
def _():
    return clean_text("id,drug\nE1,1\nE1,3\nE2,5\n", REPEATS, **DRUG)


@case("I74", "none", "a replicate grouping where every row is its own recipe")
def _():
    return clean_text("id,drug\nE1,1\nE2,3\n", REPEATS, **DRUG)


@case("I74", "kept_all", "replicates found, every row kept (rule keep_all)")
def _():
    return clean_text("id,drug\nE1,1\nE1,3\n", {**REPEATS, "replicates": {"group_by": ["experiment_id"], "rule": "keep_all"}}, **DRUG)


FAILED = {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id", "status": "state", "failure_reason": "why"}}


@case("I75", "removed", "failed runs set aside from the table")
def _():
    return clean_text("id,drug,state,why\nE1,1,ok,\nE2,,failed,jam\n", {**FAILED, "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": "exclude_from_models_keep_in_failure_statistics"}}, **DRUG)


@case("I75", "kept", "failed runs kept in the table (policy keep)")
def _():
    return clean_text("id,drug,state,why\nE1,1,ok,\nE2,,failed,jam\n", {**FAILED, "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": "keep"}}, **DRUG)


@case("I76", "", "the values of the status column are listed")
def _():
    return clean_text("id,drug,state,why\nE1,1,ok,\nE2,2,ok,\n", {**FAILED, "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": "keep"}}, **DRUG)


@case("I77", "", "a setup with no failed-run settings")
def _():
    return clean_text("id,drug\nE1,1\n", {"column_map": {"drug": "drug_pct"}}, **DRUG)


JOIN = {"column_map": {"drug": "drug_pct", "extra_value": "extra_x"}, "id_columns": {"experiment": "id"},
        "joins": [{"file": "other.csv", "on": [{"main": "id", "joined": "id"}]}]}


@case("I78", "", "a joined file with two rows for the same key")
def _():
    return clean_files({"main.csv": "id,drug\nE1,1\n", "other.csv": "id,extra_value\nE1,5\nE1,6\n"}, JOIN, **DRUG)


@case("I79", "", "main rows with no match in the joined file")
def _():
    return clean_files({"main.csv": "id,drug\nE1,1\nE2,2\n", "other.csv": "id,extra_value\nE1,5\n"}, JOIN, **DRUG)


@case("I80", "", "rows of a joined file that match nothing")
def _():
    return clean_files({"main.csv": "id,drug\nE1,1\n", "other.csv": "id,extra_value\nE1,5\nE9,6\n"}, JOIN, **DRUG)


@case("I81", "", "columns added from a joined file")
def _():
    return clean_files({"main.csv": "id,drug\nE1,1\n", "other.csv": "id,extra_value\nE1,5\n"}, JOIN, **DRUG)


@case("I82", "", "a join column that is not in the joined file")
def _():
    bad = {**JOIN, "joins": [{"file": "other.csv", "on": [{"main": "id", "joined": "nope"}]}]}
    return clean_files({"main.csv": "id,drug\nE1,1\n", "other.csv": "id,extra_value\nE1,5\n"}, bad, **DRUG)


@case("I83", "", "a joined file with a column whose name is already taken")
def _():
    return clean_files({"main.csv": "id,drug\nE1,1\n", "other.csv": "id,drug\nE1,5\n"}, JOIN, **DRUG)


@case("I84", "changed", "a table where rows were dropped, set aside and combined")
def _():
    return clean_text("id,drug,state\nE1,1,ok\nE1,3,ok\nE2,,ok\nE3,4,failed\n",
                      {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id", "status": "state"}, "missing_values": {"policy": "drop_row"},
                       "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": "exclude"},
                       "replicates": {"group_by": ["experiment_id"], "rule": "mean"}}, **DRUG)


@case("I84", "unchanged", "a table where every row is kept")
def _():
    return clean_text("id,drug\nE1,1\nE2,2\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"}}, **DRUG)


# ------------------------------------------------------------------ running the cases
@dataclass
class CaseResult:
    case: Case
    passed: bool
    finding: Finding | None = None
    notes: list[str] | None = None


def run_case(one: Case) -> CaseResult:
    try:
        result = one.run()
    except Exception as error:                  # noqa: BLE001 - a crash is a failed case
        return CaseResult(one, False, None, [f"the reader crashed: {type(error).__name__}: {error}"])
    key = (one.rule, one.variant)
    if key not in CATALOGUE:
        return CaseResult(one, False, None, ["this message is not in the catalogue"])
    matches = [f for f in result.findings if (f.rule, f.variant) == key]
    if not matches:
        found = ", ".join(sorted({f.rule + (f"/{f.variant}" if f.variant else "") for f in result.findings})) or "nothing"
        return CaseResult(one, False, None, [f"expected {one.rule}{'/' + one.variant if one.variant else ''} but found: {found}"])
    notes = []
    if matches[0].level != CATALOGUE[key].level:
        notes.append(f"expected level {CATALOGUE[key].level} but got {matches[0].level}")
    for f in result.findings:
        notes += [f"{f.rule}: {w}" for w in wording_problems(f)]
    if isinstance(result, CleanResult):
        if result.frame is not None and not (result.account.balanced and result.account.rows_out == len(result.frame) and result.account.rows_read == result.rows_read):
            notes.append("row accounting is wrong: rows read do not equal rows dropped + failed runs set aside + replicate rows combined + rows left")
    elif result.table is not None:
        i = result.table.info
        if i.rows_in_file != i.rows_kept + i.rows_blank or len(result.table.frame) != i.rows_kept:
            notes.append("row accounting is wrong: rows read do not equal rows kept plus blank rows skipped")
    return CaseResult(one, not notes, matches[0], notes)


def run_all() -> list[CaseResult]:
    return [run_case(one) for one in CASES]


def uncovered() -> list[tuple[str, str]]:
    return sorted(set(CATALOGUE) - {(one.rule, one.variant) for one in CASES})
