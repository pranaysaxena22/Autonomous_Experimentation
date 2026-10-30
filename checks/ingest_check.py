"""Health check for Stage 2 (data ingestion), so far the reading layer: getting a table out of a data file safely.

In plain words it checks that: every reader message has a test and the message document is up to date; the same table comes out of many
variants of the same file (byte-order mark, Windows or Unix or old-Mac line endings, UTF-16, semicolons, tabs, quotes, Excel); 200 random damages
to a file never crash the reader, never show technical wording and never lose a row without saying so; the mock files, freshly generated mock
files and (when present) the real public files come out with the row and column counts an independent recount gives; unsafe files are refused;
and the reader writes nothing and never touches the network.
"""
from __future__ import annotations

import csv
import hashlib
import io
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.ingest import CATALOGUE, ReadOptions, read_setup_table, read_table  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from checks import architecture, ingest_cases  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.ingest_messages_doc import DOC_PATH, build_text  # noqa: E402

MOCK = ROOT / "data" / "mock"
PUBLIC = ROOT / "data" / "public"
EDGE = " \t\u00a0\u2007\u202f\u200b\ufeff"


# ---------------------------------------------------------------- an independent recount (plain csv module, no shared code with the reader)
def recount(path: Path, delimiter: str) -> dict:
    text = path.read_bytes().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    header, after = rows[0], rows[1:]
    body = [r for r in after if any(c.strip(EDGE) for c in r)]
    return {"rows": len(body), "columns": len(header), "trimmed": sum(1 for r in after for c in r if c != c.strip(EDGE)),
            "tidied": sum(1 for h in header if re.sub(r" +", " ", h.strip(EDGE)) != h)}


def project_files() -> dict[str, tuple[int, int]]:
    skip = {".venv", ".git", "__pycache__", "runs", "chrome_profile"}
    return {p.relative_to(ROOT).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in ROOT.rglob("*")
            if p.is_file() and not (skip & set(p.relative_to(ROOT).parts))}


def frame_values(table) -> list[list[str]]:
    return table.frame.astype(str).values.tolist()


# ---------------------------------------------------------------- the checks
def message_checks(cl: Checklist, results) -> None:
    failed = [r for r in results if not r.passed]
    cl.record(not failed, f"Each of the {len(results)} reader messages is produced by a small file made to cause it, at the right level, in plain English",
              "; ".join(f"{r.case.rule} {r.case.variant}: {' / '.join(r.notes or [])[:160]}" for r in failed[:3]) if failed else f"{len(CATALOGUE)} messages in the catalogue")
    missing = ingest_cases.uncovered()
    cl.record(not missing, "Every message in the catalogue has at least one test",
              "no test for: " + ", ".join(f"{a} {b}".strip() for a, b in missing) if missing else f"{len(CATALOGUE)} of {len(CATALOGUE)} covered")
    CATALOGUE[("I99", "")] = CATALOGUE[("I01", "")]
    try:
        caught = ("I99", "") in ingest_cases.uncovered()
    finally:
        del CATALOGUE[("I99", "")]
    cl.record(caught, "Self-test: a message added without a test is caught by the coverage check", "")
    from cellpoc.ingest import Finding

    def fake(text):
        return Finding("I99", "", "error", "t.csv", "", text)

    bad = ["the schema is wrong", "got None as null", "Traceback (most recent call last)", "KeyError: 'x'", "{unfilled}", "a DataFrame had a problem"]
    cl.record(all(ingest_cases.wording_problems(fake(t)) for t in bad) and not ingest_cases.wording_problems(fake("you wrote 'null' here")),
              "Self-test: the plain-English check catches technical wording (and ignores what the person typed, quoted)", "")
    saved = DOC_PATH.read_bytes().decode("utf-8") if DOC_PATH.exists() else ""
    expected = build_text(results)
    cl.record(saved == expected and bool(re.search(r", 0 without a test\.", expected)),
              f"docs/ingest_messages.md lists every message with its test and is up to date ({len(CATALOGUE)} messages)",
              str(DOC_PATH.relative_to(ROOT)) if saved == expected else "out of date: run  .venv\\Scripts\\python.exe tools\\make_ingest_messages.py")


def known_file_checks(cl: Checklist) -> None:
    for name in ("mock_formulation_small.csv", "mock_formulation_experiments.csv", "mock_formulation_hard.csv"):
        result, count = read_table(MOCK / name), recount(MOCK / name, ",")
        info = result.table.info if result.table else None
        cl.record(bool(info) and (info.rows_kept, info.columns) == (count["rows"], count["columns"]) and info.delimiter == "comma" and not [f for f in result.findings if f.level != "note"],
                  f"{name} (synthetic mock data): {count['rows']:,} rows and {count['columns']} columns, the same as an independent recount, with no warnings",
                  f"{info.rows_kept} x {info.columns}" if info else "; ".join(f.message for f in result.findings[:2]))
    folder = PUBLIC / "batch_production"
    sources = (ROOT / "data" / "public" / "SOURCES.md").read_text(encoding="utf-8") if (ROOT / "data" / "public" / "SOURCES.md").exists() else ""
    public = [("batch_production/Laboratory.csv", ";", (1005, 55)), ("batch_production/Process.csv", ";", (1005, 35)),
              ("batch_production/Normalization.csv", ";", (25, 3)), ("formulation_literature/final Data All Exipients.csv", ",", (1982, 79))]
    if not all((PUBLIC / rel).exists() for rel, _, _ in public):
        cl.skip("The real public files (batch production and formulation literature) are read as expected",
                "SKIPPED: data/public/ files are not on this computer (they are never in git); this is not a pass")
        return
    drift = [rel for rel, _, _ in public if hashlib.sha256((PUBLIC / rel).read_bytes()).hexdigest() not in sources]
    cl.record(not drift, "The real public files are exactly the ones recorded in data/public/SOURCES.md (same fingerprints)", "changed: " + ", ".join(drift) if drift else "4 of 4 match")
    for rel, delimiter, (rows, columns) in public:
        result, count = read_table(PUBLIC / rel), recount(PUBLIC / rel, delimiter)
        info = result.table.info if result.table else None
        right = (bool(info) and (info.rows_kept, info.columns) == (rows, columns) == (count["rows"], count["columns"])
                 and info.delimiter == ("semicolon" if delimiter == ";" else "comma")
                 and info.cells_trimmed == count["trimmed"] and info.names_tidied == count["tidied"] and not [f for f in result.findings if f.level != "note"])
        cl.record(right, f"{Path(rel).name} (real public data, not client data): {rows:,} rows x {columns} columns, "
                         f"{'semicolon' if delimiter == ';' else 'comma'}-separated; spaces removed from {count['trimmed']:,} cells and {count['tidied']} column names, "
                         "as an independent recount finds",
                  f"{info.rows_kept} x {info.columns}, trimmed {info.cells_trimmed}, tidied {info.names_tidied}" if info else "; ".join(f.message for f in result.findings[:2]))


def fresh_mock_checks(cl: Checklist) -> None:
    problems, shapes = [], []
    with tempfile.TemporaryDirectory() as folder:
        for seed, difficulty in ((7001, "easy"), (7002, "hard")):
            out = Path(folder) / f"fresh_{difficulty}.csv"
            done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "make_mock_data.py"), "--n", "300", "--seed", str(seed), "--difficulty", difficulty, "--out", str(out)],
                                  capture_output=True, text=True, cwd=folder)
            if done.returncode != 0 or not out.exists():
                problems.append(f"{difficulty}: the generator failed")
                continue
            result, count = read_table(out), recount(out, ",")
            info = result.table.info if result.table else None
            if not info or (info.rows_kept, info.columns) != (count["rows"], count["columns"]):
                problems.append(f"{difficulty}: {info.rows_kept if info else '?'} rows read, recount {count['rows']}")
            else:
                shapes.append(f"{difficulty} seed {seed}: {info.rows_kept} x {info.columns}")
    cl.record(not problems, "Freshly generated mock files (new seeds, made now, never tuned to) are read with the same counts as an independent recount",
              "; ".join(problems) if problems else "; ".join(shapes))


def variant_matrix(cl: Checklist) -> None:
    source = MOCK / "mock_formulation_small.csv"
    text = source.read_bytes().decode("utf-8")
    reference = read_table(source).table
    ref_values, ref_names = frame_values(reference), [n.casefold() for n in reference.frame.columns]
    rows = list(csv.reader(io.StringIO(text, newline="")))

    def join(delimiter: str, newline: str = "\n", quote_all: bool = False, table=rows) -> str:
        out = io.StringIO()
        csv.writer(out, delimiter=delimiter, lineterminator=newline, quoting=csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL).writerows(table)
        return out.getvalue()

    def typed(cell: str):
        if re.fullmatch(r"-?\d+", cell):
            return int(cell)
        try:
            number = float(cell)                       # a whole-number-looking value such as 11.0 is kept as text: Excel would store it as 11
            return number if repr(number) == cell and not number.is_integer() else cell
        except ValueError:
            return cell

    comma_lf, comma_crlf = join(","), join(",", "\r\n")
    spaced = [[f" {rows[0][0].upper()} "] + rows[0][1:]] + rows[1:]
    variants = {
        "the original": comma_lf.encode(),
        "with a byte-order mark": b"\xef\xbb\xbf" + comma_lf.encode(),
        "Windows line endings": comma_crlf.encode(),
        "old Mac line endings (CR only)": join(",", "\r").encode(),
        "UTF-16 with a mark (little-endian)": b"\xff\xfe" + comma_lf.encode("utf-16-le"),
        "UTF-16 with a mark (big-endian)": b"\xfe\xff" + comma_lf.encode("utf-16-be"),
        "UTF-16 without a mark": comma_lf.encode("utf-16-le"),
        "semicolon-separated": join(";").encode(),
        "tab-separated": join("\t").encode(),
        "every value in quotes": join(",", quote_all=True).encode(),
        "blank lines at the end": (comma_lf + "\n\n\n").encode(),
        "an extra empty column": join(",", table=[r + [""] for r in rows]).encode(),
        "a first column name with spaces and capitals": join(",", table=spaced).encode(),
    }
    wrong = []
    for label, content in variants.items():
        result = ingest_cases.read_bytes(content)
        if not result.ok or frame_values(result.table) != ref_values or [n.casefold() for n in result.table.frame.columns] != ref_names:
            wrong.append(label)
    cl.record(not wrong, f"The same table comes out of the mock file in {len(variants)} variants (byte-order mark, three kinds of line ending, three kinds of UTF-16, semicolons, tabs, quotes, blank lines, an extra empty column, odd name spacing)",
              "different or refused: " + ", ".join(wrong) if wrong else f"{len(variants)} of {len(variants)} identical")
    workbook = ingest_cases.xlsx_bytes([[typed(c) for c in r] for r in rows])
    excel = ingest_cases.read_bytes(workbook, "t.xlsx")
    first_difference = ""
    if excel.table is not None and frame_values(excel.table) != ref_values:
        got = frame_values(excel.table)
        first_difference = next((f"row {r + 2} column {ref_names[c]}: file has {ref_values[r][c]!r}, Excel copy gave {got[r][c]!r}" for r in range(len(ref_values)) for c in range(len(ref_names)) if r < len(got) and ref_values[r][c] != got[r][c]), "different number of rows")
    cl.record(excel.ok and frame_values(excel.table) == ref_values, "The same table comes out of an Excel (.xlsx) copy of the mock file (numbers stored as numbers or as text)",
              first_difference or "; ".join(f.message for f in excel.findings if f.level == "error")[:160])
    # non-ASCII names and a Central-European encoding
    unicode_rows = [["Ime \u010d", "Te\u017ea (g)"], ["\u0161", "1.5"], ["\u017e", "2.5"]]
    unicode_text = join(",", table=unicode_rows)
    base = ingest_cases.read_bytes(unicode_text.encode("utf-8"))
    same = [("windows-1250 declared", ingest_cases.read_bytes(unicode_text.encode("cp1250"), encoding="windows-1250")),
            ("UTF-16", ingest_cases.read_bytes(b"\xff\xfe" + unicode_text.encode("utf-16-le"))),
            ("Excel", ingest_cases.read_bytes(ingest_cases.xlsx_bytes([[c if not re.fullmatch(r"[\d.]+", c) else float(c) for c in r] for r in unicode_rows]), "t.xlsx"))]
    mismatched = [label for label, r in same if not r.ok or list(r.table.frame.columns) != list(base.table.frame.columns) or frame_values(r.table) != frame_values(base.table)]
    cl.record(base.ok and list(base.table.frame.columns) == ["Ime \u010d", "Te\u017ea (g)"] and not mismatched,
              "Names and values with letters such as \u010d, \u0161, \u017e come out identically from UTF-8, windows-1250, UTF-16 and Excel files", ", ".join(mismatched))


def damage_test(cl: Checklist) -> None:
    original = (MOCK / "mock_formulation_small.csv").read_bytes()
    rng = random.Random(20261010)
    junk = [b"\x00", b'"', b",", b";", b"\t", b"\r", b"\n", b"\xff", b"\xe8", b"=1+1", b"#N/A", b"x" * 300]
    crashes, unplain, silent, errors_without_message, reads = [], [], [], [], 0
    for number in range(1, 201):
        data = bytearray(original)
        steps = []
        for _ in range(rng.choice([1, 2, 3])):
            kind = rng.choice(["delete", "insert", "flip", "truncate", "duplicate_line", "swap_delimiter", "bom", "utf16", "chop_header"])
            position = rng.randrange(len(data)) if data else 0
            if kind == "delete":
                del data[position:position + rng.randint(1, 400)]
            elif kind == "insert":
                data[position:position] = rng.choice(junk)
            elif kind == "flip" and data:
                data[position] ^= 1 << rng.randrange(8)
            elif kind == "truncate":
                data = data[:position]
            elif kind == "duplicate_line":
                lines = bytes(data).split(b"\n")
                index = rng.randrange(len(lines))
                lines.insert(index, lines[index])
                data = bytearray(b"\n".join(lines))
            elif kind == "swap_delimiter":
                data = bytearray(bytes(data).replace(b",", rng.choice([b";", b"\t", b"|"]), rng.randint(1, 80)))
            elif kind == "bom":
                data = bytearray(b"\xef\xbb\xbf" + bytes(data))
            elif kind == "utf16":
                data = bytearray(b"\xff\xfe" + bytes(data).decode("latin-1").encode("utf-16-le"))
            elif kind == "chop_header":
                data = bytearray(bytes(data).split(b"\n", 1)[-1])
            steps.append(kind)
        label = f"#{number} ({', '.join(steps)})"
        try:
            result = ingest_cases.read_bytes(bytes(data))
        except Exception as error:                  # noqa: BLE001 - this is exactly what the test looks for
            crashes.append(f"{label}: {type(error).__name__}: {error}")
            continue
        reads += 1
        for finding in result.findings:
            unplain += [f"{label} {finding.rule}: {w}" for w in ingest_cases.wording_problems(finding)]
        if result.table is None and not any(f.level == "error" for f in result.findings):
            errors_without_message.append(label)
        if result.table is not None:
            info = result.table.info
            if info.rows_in_file != info.rows_kept + info.rows_blank or len(result.table.frame) != info.rows_kept \
                    or any(len(r) != len(result.table.frame.columns) for r in frame_values(result.table)):
                silent.append(label)
    cl.record(not crashes and reads == 200, "200 random damages to the mock file (bytes deleted, inserted or flipped, cut short, separators swapped, encodings changed): the reader never crashes",
              "; ".join(crashes[:2]) if crashes else "200 files read or refused")
    cl.record(not unplain, "In all 200 damaged files every message is plain English with the file name (no schema, null, traceback and similar wording)", "; ".join(unplain[:2]))
    cl.record(not silent and not errors_without_message, "In all 200 damaged files no row is lost silently: rows read = rows kept + blank rows skipped, every row has every column, and a refused file always says why",
              "; ".join((silent + errors_without_message)[:2]))
    # the damage test must be able to notice a crash
    import cellpoc.ingest.reader as reader_module
    saved = reader_module._build

    def exploding(*args, **kwargs):
        raise RuntimeError("simulated crash")

    reader_module._build = exploding
    try:
        caught = 0
        for _ in range(3):
            try:
                ingest_cases.read_bytes(original)
            except RuntimeError:
                caught += 1
    finally:
        reader_module._build = saved
    cl.record(caught == 3, "Self-test: a crash inside the reader is visible to the damage test", f"{caught} of 3 noticed")


def safety_checks(cl: Checklist) -> None:
    formula = ingest_cases.read_bytes(ingest_cases.xlsx_bytes([["a", "b"], [1, "=1+1"], [2, "=SUM(A2:A3)"]]), "t.xlsx")
    cl.record(formula.ok and frame_values(formula.table) == [["1", ""], ["2", ""]] and any(f.rule == "I33" for f in formula.findings),
              "Excel formulas are never evaluated: a formula with no saved result is read as empty and reported", "")
    refused = {suffix: ingest_cases.read_bytes(b"PK\x03\x04not read", f"t{suffix}") for suffix in (".xlsm", ".xlsb", ".xls")}
    cl.record(all(r.table is None and any(f.rule == "I04" for f in r.findings) for r in refused.values()),
              "Excel files with macros, in the binary format, or in the old format are refused with a plain message", ", ".join(refused))
    unsafe = {}
    for reference in ("../outside.csv", "C:\\Windows\\win.ini", "/etc/passwd", "\\\\server\\share\\x.csv"):
        result = read_setup_table({"data": {"experiments_file": reference}}, None, PROJECT_ROOT)
        unsafe[reference] = result.table is None and any(f.rule == "I01" for f in result.findings)
    cl.record(all(unsafe.values()), "A setup cannot point the reader outside the project (no .., no drive letters, no network paths)", ", ".join(k for k, v in unsafe.items() if not v))
    first = read_table(MOCK / "mock_formulation_small.csv")
    second = read_table(MOCK / "mock_formulation_small.csv")
    cl.record(first.findings == second.findings and frame_values(first.table) == frame_values(second.table) and list(first.table.frame.columns) == list(second.table.frame.columns),
              "Reading the same file twice gives exactly the same table and the same messages", "")
    limits = ingest_cases.read_text(ingest_cases.BASE, max_rows=1)
    cl.record(limits.table is None and any(f.rule == "I13" for f in limits.findings), "A table longer than the row limit is refused, not truncated", "")


# ================================================================ Stage 2c: from text to typed values
import copy  # noqa: E402
from collections import Counter  # noqa: E402
import math  # noqa: E402

import yaml  # noqa: E402

from cellpoc.ingest import read_and_clean  # noqa: E402
from cellpoc.ingest.dates import DateFormat, MONTHS  # noqa: E402
from cellpoc.ingest.parsing import parse_number  # noqa: E402
from cellpoc.setup import example_setup_path, load_setup  # noqa: E402

FIXTURES = ROOT / "cellpoc" / "ingest" / "fixtures"
SLOVENIAN_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6, "jul": 7, "avg": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12}


def raw_table(path: Path, delimiter: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline=""), delimiter=delimiter))
    return [h.strip() for h in rows[0]], [[c.strip() for c in r] for r in rows[1:] if any(c.strip() for c in r)]


def same(a: list[float], b: list[float], tol: float = 1e-12) -> bool:
    return len(a) == len(b) and all((math.isnan(x) and math.isnan(y)) or abs(x - y) <= tol for x, y in zip(a, b))


def nan_or(text: str, divide: float = 1.0) -> float:
    return float("nan") if text == "" else float(text) / divide


def mock_cleaning(cl: Checklist) -> None:
    setup = load_setup(example_setup_path()).setup
    for name in ("mock_formulation_small.csv", "mock_formulation_experiments.csv", "mock_formulation_hard.csv"):
        s = copy.deepcopy(setup)
        s["data"]["experiments_file"] = f"data/mock/{name}"
        s["data"].pop("replicates", None)                         # this check is about typing, not about combining rows (see mock_rows)
        s["data"]["failed_runs"]["policy"] = "keep"
        result = read_and_clean(s, None, PROJECT_ROOT)
        header, body = raw_table(MOCK / name, ",")
        col = {h: i for i, h in enumerate(header)}
        cell = lambda r, h: r[col[h]]  # noqa: E731
        problems = []
        if not result.ok or len(result.frame) != len(body):
            cl.record(False, f"{name}: cleaned with the example setup", "; ".join(f.message for f in result.findings if f.level == "error")[:200] or "wrong number of rows")
            continue
        f = result.frame
        expected_friability = [0.05 if cell(r, "friability_note") == "<0.05" else nan_or(cell(r, "friability_pct")) for r in body]
        expected_hardness = [nan_or(cell(r, "hardness"), 9.807 if cell(r, "hardness_unit") == "N" else 1.0) for r in body]
        checks = {
            "below-detection flags": int(f["friability_pct__below_detection"].sum()) == sum(1 for r in body if cell(r, "friability_note") == "<0.05"),
            "friability values": same(f["friability_pct"].tolist(), expected_friability),
            "hardness (newtons divided by 9.807)": same(f["hardness_kp"].tolist(), expected_hardness),
            "newton count": result.column("hardness_kp").n_converted == sum(1 for r in body if cell(r, "hardness_unit") == "N"),
            "dissolution values": same(f["dissolution_30min_pct"].tolist(), [nan_or(cell(r, "dissolution_30min_pct")) for r in body]),
            "an untouched ingredient column": same(f["drug_pct"].tolist(), [float(cell(r, "drug_pct")) for r in body], 0.0),
            "failed runs carried through (set aside later)": int((f["status"] == "failed").sum()) == sum(1 for r in body if cell(r, "status") == "failed"),
            "dates": f["date"].dt.date.astype(str).min() == min(cell(r, "date") for r in body) and f["date"].dt.date.astype(str).max() == max(cell(r, "date") for r in body),
        }
        problems = [k for k, ok in checks.items() if not ok]
        flags = int(f["friability_pct__below_detection"].sum())
        converted = result.column("hardness_kp").n_converted
        cl.record(not problems, f"{name} (synthetic mock data) cleaned with the example setup: {len(body):,} rows; {flags} below-detection flags, {converted} hardness values converted from newtons, "
                                "every value equal to an independent recount", "; ".join(problems))


def laboratory_cleaning(cl: Checklist, available: bool) -> None:
    if not available:
        cl.skip("Laboratory.csv and Process.csv are cleaned as an independent recount expects", "SKIPPED: data/public/ files are not on this computer; this is not a pass")
        return
    setup = yaml.safe_load((FIXTURES / "laboratory_setup.yaml").read_text(encoding="utf-8"))
    result = read_and_clean(setup, None, PROJECT_ROOT)
    header, body = raw_table(PUBLIC / "batch_production" / "Laboratory.csv", ";")
    col = {h: i for i, h in enumerate(header)}
    expected_dates = []
    for r in body:
        month, year = r[col["start"]].split(".")
        expected_dates.append(f"{2000 + int(year)}-{SLOVENIAN_MONTHS[month]:02d}-01")
    got = result.frame["date"].dt.date.astype(str).tolist() if result.ok else []
    cl.record(result.ok and got == expected_dates and set(result.frame["date_precision"]) == {"month"},
              "Laboratory.csv (real public data, not client data): all 1,005 Slovenian month-and-year dates (nov.18, maj.19, avg.20, okt.19 ...) are read correctly, as the first of the month, marked month-only",
              f"first {got[0] if got else '?'}, last {got[-1] if got else '?'}")
    distinct = len({r[col["start"]] for r in body})
    cl.record(result.ok and sum(1 for f in result.findings if (f.rule, f.variant) == ("I65", "month_only")) == 1 and f"{distinct} different months" in next(f.text for f in result.findings if (f.rule, f.variant) == ("I65", "month_only")),
              f"The month-only warning says so ({distinct} different months), because the order of events inside a month is unknown", "")
    gaps = {name: sum(1 for r in body if r[col[raw]] == "") for raw, name in (("api_water", "api_water"), ("api_total_impurities", "api_total_impurities"),
                                                                              ("api_l_impurity", "api_l_impurity"), ("api_content", "api_content"), ("tbl_min_weight", "tbl_min_weight"))}
    cl.record(result.ok and all(int(result.frame[n].isna().sum()) == c for n, c in gaps.items()),
              "Laboratory.csv: empty cells come out as missing, never filled in (" + ", ".join(f"{n} {c}" for n, c in gaps.items()) + ")", "")
    cl.record(result.ok and same(result.frame["tbl_av_hardness"].tolist(), [float(r[col["tbl_av_hardness"]]) for r in body], 0.0)
              and result.frame["strength"].tolist() == [r[col["strength"]] for r in body],
              "Laboratory.csv: untouched numeric and text columns are identical to the file", "")

    setup = yaml.safe_load((FIXTURES / "process_setup.yaml").read_text(encoding="utf-8"))
    result = read_and_clean(setup, None, PROJECT_ROOT)
    header, body = raw_table(PUBLIC / "batch_production" / "Process.csv", ";")
    col = {h: i for i, h in enumerate(header)}
    na = {raw: sum(1 for r in body if r[col[raw]] == "#N/A") for raw in ("Drug release average (%)", "Drug release min (%)", "Residual solvent", "Total impurities", "Impurity O", "Impurity L")}
    ids = {"Drug release average (%)": "drug_release_average", "Drug release min (%)": "drug_release_min", "Residual solvent": "residual_solvent", "Total impurities": "total_impurities",
           "Impurity O": "impurity_o", "Impurity L": "impurity_l"}
    cl.record(result.ok and all(int(result.frame[ids[k]].isna().sum()) == v for k, v in na.items()) and sum(na.values()) == 108
              and any(f.rule == "I64" and "'#N/A' 108" in f.text for f in result.findings),
              "Process.csv (real public data, not client data): the 108 '#N/A' cells (18 rows in each of 6 columns) become missing because the setup lists '#N/A', and are counted in the messages",
              ", ".join(f"{k}: {v}" for k, v in na.items()))
    cl.record(result.ok and int((result.frame["weekend"] == "yes").sum()) == sum(1 for r in body if r[col["weekend"]] == "yes") and "main_compforce_mean" in result.frame.columns,
              "Process.csv: a text factor (weekend) and a column name with a space inside ('main_CompForce mean') come out right", "")
    without = copy.deepcopy(setup)
    without["data"].pop("missing_markers")
    bad = read_and_clean(without, None, PROJECT_ROOT)
    cl.record(bad.ok and any(f.rule == "I46" and "#N/A" in f.text for f in bad.findings) and int(bad.frame["drug_release_average"].isna().sum()) == na["Drug release average (%)"],
              "Without the marker in the setup, '#N/A' is not silently accepted: it is reported as 'not a number' (and left missing), with the hint to list it", "")


def literature_cleaning(cl: Checklist, available: bool) -> None:
    if not available:
        cl.skip("The formulation literature file is cleaned as an independent recount expects", "SKIPPED: data/public/ files are not on this computer; this is not a pass")
        return
    setup = yaml.safe_load((FIXTURES / "literature_setup.yaml").read_text(encoding="utf-8"))
    result = read_and_clean(setup, None, PROJECT_ROOT)
    header, body = raw_table(PUBLIC / "formulation_literature" / "final Data All Exipients.csv", ",")
    col = {h: i for i, h in enumerate(header)}
    first, last = col["Wetting time"] + 1, col["HARDNESS"]
    amounts = list(range(first, last)) + [col["DOSE"]]
    gaps = [(sum(float(r[i]) for i in amounts) - float(r[col["Weight(mg)"]])) / float(r[col["Weight(mg)"]]) * 100 for r in body]
    tolerance = 2.0
    flagged = sum(1 for g in gaps if round(abs(g), 9) > tolerance)
    if not result.ok:
        cl.record(False, "The formulation literature file is cleaned", "; ".join(f.message for f in result.findings if f.level == "error")[:200])
        return
    frame = result.frame
    cl.record(same(frame["mass_balance_gap_pct"].tolist(), gaps, 1e-9) and int(frame["mass_balance_flag"].sum()) == flagged == result.composition["flagged"],
              f"Literature table (real public data, not client data): the exact weight gap of every one of the {len(body):,} rows equals an independent calculation; {flagged} rows ({100 * flagged / len(body):.1f}%) are flagged at the stated 2% tolerance",
              f"flagged {int(frame['mass_balance_flag'].sum())} vs recount {flagged}")
    cl.record(abs(result.composition["shortfall_pct"] - min(gaps)) < 1e-9 and result.composition["overshoot_pct"] <= 1e-9 and all(frame.loc[frame["mass_balance_flag"], "mass_balance_gap_pct"].abs() > tolerance),
              f"Every flag carries its exact gap (largest shortfall {abs(min(gaps)):.2f}%, no overshoot) and no row inside the tolerance is flagged", "")
    exact = [(4, -2.0), (5, 2.0), (6, 2.0000001), (7, -2.0000001)]
    boundary = ingest_cases.clean_text("w,a,b\n" + "\n".join(f"{100},{50 + g / 2},{50 + g / 2}" for _, g in exact) + "\n",
                                       {"column_map": {"w": "w_mg", "a": "a_mg", "b": "b_mg"}, "composition": {"total_weight": "w_mg", "tolerance_pct": 2}})
    cl.record(boundary.ok and boundary.frame["mass_balance_flag"].tolist() == [False, False, True, True],
              "The tolerance boundary is exact: a gap of exactly 2.0% (short or over) passes, 2.0000001% is flagged", "")
    pct_ok = all(abs(frame[f"{ident}"].iloc[k] - float(body[k][col[raw]]) / float(body[k][col["Weight(mg)"]]) * 100) < 1e-9
                 for raw, ident in (("DOSE", "drug_pct"), ("Mannitol", "mannitol_pct")) for k in range(0, len(body), 97))
    cl.record(pct_ok and "tablet_weight_pct" not in frame.columns, "Amounts become a percentage of Weight(mg) (checked on a sample of rows), and the weight column itself is not converted", "")
    dictionary_missing = _dictionary_missing()
    assumed = sorted(r.id for r in result.columns if r.unit_status == "assumed" and r.role != "derived" and r.id != "hardness_kp")
    confirmed = [r for r in result.columns if r.id.endswith("_mg") and r.role != "derived" and r.unit_status == "declared"]
    derived_assumed = [r.id for r in result.columns if r.role == "derived" and r.unit_status == "assumed"]
    cl.record(assumed == sorted(dictionary_missing) and len(confirmed) == 58 - len(dictionary_missing) and derived_assumed == [a.replace("_mg", "_pct") for a in sorted(dictionary_missing)]
              and all("unit assumed, not confirmed by the dataset's dictionary" in result.column(a).unit_note for a in assumed),
              f"Units: the {len(confirmed)} mg columns (56 excipients, the API dose and the tablet weight) that the dataset's dictionary confirms are marked declared; the {len(assumed)} it does not confirm ({', '.join(assumed)}) are marked "
              "'unit assumed, not confirmed by the dataset's dictionary', and so is the percentage made from it", f"assumed {assumed}, expected {sorted(dictionary_missing)}")
    cl.record(sum(1 for f in result.findings if f.rule == "I51") == len(assumed), "Each assumed unit has its own warning in the messages", "")
    hardness = result.column("hardness_kp")
    cl.record(hardness.unit_status == "assumed" and "kilopond" in hardness.unit_note and hardness.n_converted == len(body) and same(frame["hardness_kp"].tolist(), [float(r[col["HARDNESS"]]) for r in body], 0.0)
              and any(f.rule == "I52" for f in result.findings),
              "Hardness in kg/cm2 is taken as kP (divided by 1) and marked as an assumed conversion for all 1,982 values, in the column report and in a warning", "")
    cl.record(frame["experiment_id"].iloc[0] == "row2" and frame["experiment_id"].is_unique and any(f.rule == "I61" for f in result.findings),
              "A file with no ID column gets IDs from its row numbers (row2, row3 ...), and says so", "")
    fixture_assumed = sorted(a["id"] for a in setup["data"]["assumed_units"])
    cl.record(fixture_assumed == sorted(dictionary_missing), "The fixture setup's list of assumed units is exactly what the dataset's dictionary leaves out (worked out independently, ignoring capitals and spaces)", str(fixture_assumed))


def _dictionary_missing() -> list[str]:
    """Amount IDs (in the fixture's naming) whose column the dataset's own dictionary does not list, ignoring capitals and spaces."""
    import zipfile

    tidy = lambda s: re.sub(r"\s+", " ", s.replace(" ", " ")).strip().casefold()  # noqa: E731
    with zipfile.ZipFile(PUBLIC / "formulation_literature" / "dataverse_files.zip") as z:
        text = z.read("Documentation/data_dictionary.tab/data_dictionary.csv").decode("utf-8", "replace")
    listed = {tidy(r[0]) for r in csv.reader(io.StringIO(text, newline="")) if r and r[0] != "Column Name"}
    header = next(csv.reader(io.StringIO((PUBLIC / "formulation_literature" / "final Data All Exipients.csv").read_bytes().decode("utf-8-sig"), newline="")))
    slug = lambda s: re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", re.sub(r"\s+", " ", s).strip().lower())).strip("_") + "_mg"  # noqa: E731
    first, last = [tidy(h) for h in header].index("wetting time") + 1, [tidy(h) for h in header].index("hardness")
    return [slug(h) for h in header[first:last] if tidy(h) not in listed]


def cleaning_rules(cl: Checklist) -> None:
    """Small tables with known answers: dates, numbers, below-detection, missing values, units."""
    # dates
    wrong = []
    for language, (short, full) in MONTHS.items():
        for number in range(12):
            for name in (short[number], full[number].upper()):
                parsed, precision = DateFormat.build("mon.yy", language).parse(f"{name}.19")
                if (parsed.month if parsed else None) != number + 1 or precision != "month":
                    wrong.append(f"{language} {name}")
    cl.record(not wrong, "All twelve month names (short and full, capitals or not) are read in English and in Slovenian, for example maj, avg, okt; the computer's language settings play no part", ", ".join(wrong[:4]))
    d = lambda text, pattern, lang="en": DateFormat.build(pattern, lang).parse(text)[0]  # noqa: E731
    cl.record(str(d("03/04/2025", "mm/dd/yyyy")) == "2025-03-04" and str(d("03/04/2025", "dd/mm/yyyy")) == "2025-04-03" and str(d("03.04.2025", "dd.mm.yyyy")) == "2025-04-03",
              "Day and month are never guessed: the same text 03/04/2025 is 4 March or 3 April depending only on the format the setup states", "")
    no_format = ingest_cases.clean_text("when,drug\n03/04/2025,1\n2025-04-03,2\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}}, **ingest_cases.DRUG)
    cl.record(no_format.ok is False or (no_format.frame["date"].isna().tolist() == [True, False] and any(f.rule == "I49" for f in no_format.findings)),
              "With no format stated, only year-month-day is read: 03/04/2025 is reported as unreadable, never guessed", "")
    years = [str(d(f"nov.{y}", "mon.yy", "sl")) for y in ("18", "69", "70", "99", "00")]
    cl.record(years == ["2018-11-01", "2069-11-01", "1970-11-01", "1999-11-01", "2000-11-01"], "Two-digit years: 00 to 69 mean 2000 to 2069 and 70 to 99 mean 1970 to 1999", ", ".join(years))
    cl.record(d("2025-02-30", "yyyy-mm-dd") is None and d("31.04.2025", "dd.mm.yyyy") is None and d("13/13/2025", "mm/dd/yyyy") is None, "Dates that do not exist (30 February, 31 April, month 13) are unreadable, not adjusted", "")
    # numbers
    cases = {"12.5": 12.5, "12,5": 12.5, "+5": 5.0, ".5": 0.5, "1e-3": 0.001, "-0.25": -0.25, "1,234.5": None, "1.234,5": None, "inf": None, "nan": None, "5.": None, "1 2": None, "": None, "12.5.1": None}
    wrong = [k for k, v in cases.items() if (lambda got: (got is None) != (v is None) or (v is not None and abs(got - v) > 1e-12))(parse_number(k, "auto"))]
    cl.record(not wrong and parse_number("12,5", "point") is None and parse_number("12.5", "comma") is None,
              "Numbers: 12.5 and 12,5 are read (12,5 only when the decimal mark allows it); 1,234.5, inf, nan and other doubtful text are refused, never turned into numbers", ", ".join(wrong))
    # below-detection rules
    outcomes = {}
    for rule in ("use_limit_and_flag", "use_half_limit", "treat_as_missing"):
        r = ingest_cases.clean_text("x\n<0.05\n0.3\n", {"column_map": {"x": "x_pct"}, "below_detection": {"rule": rule}})
        outcomes[rule] = (r.frame["x_pct"].tolist(), r.frame["x_pct__below_detection"].tolist())
    cl.record(outcomes["use_limit_and_flag"][0][0] == 0.05 and outcomes["use_half_limit"][0][0] == 0.025 and math.isnan(outcomes["treat_as_missing"][0][0])
              and all(v[1] == [True, False] and v[0][1] == 0.3 for v in outcomes.values()),
              "Below-detection values follow the setup's rule (use the limit, half the limit, or missing), are flagged, and values above the limit are untouched", str(outcomes)[:120])
    # missing-value policies
    table, data = "id,drug\nE1,1\nE2,\nE3,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"}}
    skip = ingest_cases.clean_text(table, {**data, "missing_values": {"policy": "skip_for_that_response"}}, **ingest_cases.DRUG)
    drop = ingest_cases.clean_text(table, {**data, "missing_values": {"policy": "drop_row"}}, **ingest_cases.DRUG)
    stop = ingest_cases.clean_text(table, {**data, "missing_values": {"policy": "fail"}}, **ingest_cases.DRUG)
    cl.record(len(skip.frame) == 3 and skip.frame["drug_pct"].isna().tolist() == [False, True, False] and len(drop.frame) == 2 and drop.dropped == [(3, "a value is missing")] and not stop.ok,
              "Missing-value policies: 'skip' keeps every row with the gap left empty (nothing is filled in); 'drop' removes the row and lists it; 'fail' refuses the table", "")
    # units
    n = ingest_cases.clean_text("h,u\n98.07,N\n5,kP\n6,lbf\n", {"column_map": {}, "hardness": ingest_cases.HARDNESS})
    values = n.frame["hardness_kp"].tolist()
    cl.record(values[0] == 98.07 / 9.807 and values[1] == 5.0 and math.isnan(values[2]) and any(f.rule == "I57" for f in n.findings),
              "Units: newtons are divided by exactly 9.807, kP stays as it is, and a unit with no conversion is reported and left missing (never guessed)", "")
    # nothing changed silently
    rng = random.Random(99)
    numbers = [repr(rng.uniform(-1000, 1000)) for _ in range(200)] + [str(rng.randint(-10**9, 10**9)) for _ in range(50)]
    r = ingest_cases.clean_text("v\n" + "\n".join(numbers) + "\n", {"column_map": {"v": "v_val"}})
    cl.record(r.ok and r.frame["v_val"].tolist() == [float(x) for x in numbers], "250 random numbers come out exactly equal to what was written (no rounding, no change)", "")
    # the clean step reports every column's origin
    cols = ingest_cases.clean_text("a,b\n1,x\n", {"column_map": {"a": "a_pct", "b": "b_text"}})
    cl.record(all(c.id and c.kind for c in cols.columns) and {c.id for c in cols.columns} >= {"experiment_id", "a_pct", "b_text"},
              "Every output column has a report entry (its kind, unit status and counts) for the quality report", "")


def cleaning_damage(cl: Checklist) -> None:
    original = (MOCK / "mock_formulation_small.csv").read_bytes()
    base = load_setup(example_setup_path()).setup["data"]
    rng = random.Random(20261011)
    crashes, unplain, accounting = [], [], []
    for number in range(1, 201):
        data = bytearray(original)
        for _ in range(rng.choice([1, 2, 3])):
            kind = rng.choice(["delete", "insert", "flip", "delimiter", "number", "date", "header"])
            position = rng.randrange(len(data))
            if kind == "delete":
                del data[position:position + rng.randint(1, 60)]
            elif kind == "insert":
                data[position:position] = rng.choice([b"x", b"#N/A", b"<", b">", b",", b'"', b" ", b"1,5", b"1e999", b"\xff"])
            elif kind == "flip":
                data[position] ^= 1 << rng.randrange(8)
            elif kind == "delimiter":
                data = bytearray(bytes(data).replace(b",", b";", rng.randint(1, 50)))
            elif kind == "number":
                data = bytearray(re.sub(rb"\d+\.\d+", lambda m: rng.choice([b"1,5", b"abc", b"", b"-1", b"999", b"<0.05", b">9"]), bytes(data), count=rng.randint(1, 5)))
            elif kind == "date":
                data = bytearray(re.sub(rb"2025-\d\d-\d\d", lambda m: rng.choice([b"2025-02-30", b"nov.18", b"", b"3/4/25"]), bytes(data), count=rng.randint(1, 4)))
            else:
                data = bytearray(bytes(data).replace(b"experiment_id", rng.choice([b"Experiment_ID ", b"x", b""]), 1))
        label = f"#{number}"
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "t.csv"
                path.write_bytes(bytes(data))
                read = read_table(path, ReadOptions.from_setup(base))
            result = clean_table_for(read, base)
        except Exception as error:                  # noqa: BLE001
            crashes.append(f"{label}: {type(error).__name__}: {error}")
            continue
        for finding in result.findings:
            unplain += [f"{label} {finding.rule}: {w}" for w in ingest_cases.wording_problems(finding)]
        if result.frame is not None and not (result.account.balanced and result.account.rows_out == len(result.frame)):
            accounting.append(label)
        if result.frame is None and not any(f.level == "error" for f in result.findings):
            accounting.append(label + " refused without a reason")
    cl.record(not crashes, "200 random damages to the mock file (numbers turned to text, '1,5', '<0.05', bad dates, odd separators, bytes changed), pushed through reading AND cleaning: nothing crashes",
              "; ".join(crashes[:2]) if crashes else "200 files read, cleaned or refused")
    cl.record(not unplain, "In all 200 damaged files every cleaning message is plain English with its file name", "; ".join(unplain[:2]))
    cl.record(not accounting, "In all 200 damaged files the row accounting always adds up (rows read = dropped + failed runs set aside + replicates combined + rows left), and a refused table always says why", "; ".join(accounting[:3]))


def clean_table_for(read, data):
    from cellpoc.ingest import clean_table

    return clean_table(read, {"data": data, **{k: v for k, v in load_setup(example_setup_path()).setup.items() if k in ("ingredients", "process_factors", "context_factors", "targets")}})


def mock_rows(cl: Checklist) -> None:
    """Failed runs and replicates on the three mock files, with the full example setup, against an independent recount."""
    setup = load_setup(example_setup_path()).setup
    for name in ("mock_formulation_small.csv", "mock_formulation_experiments.csv", "mock_formulation_hard.csv"):
        s = copy.deepcopy(setup)
        s["data"]["experiments_file"] = f"data/mock/{name}"
        result = read_and_clean(s, None, PROJECT_ROOT)
        header, body = raw_table(MOCK / name, ",")
        col = {h: i for i, h in enumerate(header)}
        failed = [r for r in body if r[col["status"]] == "failed"]
        groups: dict[str, list] = {}
        for r in body:
            if r[col["status"]] != "failed":
                groups.setdefault(r[col["experiment_id"]], []).append(r)
        merged = sum(len(g) for g in groups.values()) - len(groups)
        if not result.ok:
            cl.record(False, f"{name}: failed runs and replicates with the example setup", "; ".join(f.message for f in result.findings if f.level == "error")[:200])
            continue
        a, f = result.account, result.frame
        hardness = lambda r: nan_or(r[col["hardness"]], 9.807 if r[col["hardness_unit"]] == "N" else 1.0)  # noqa: E731

        def group_mean(rows, getter):
            values = [v for v in (getter(r) for r in rows) if not math.isnan(v)]
            return sum(values) / len(values) if values else float("nan")

        dissolution = lambda r: nan_or(r[col["dissolution_30min_pct"]])  # noqa: E731
        expected_diss = [group_mean(rows, dissolution) for rows in groups.values()]
        expected_hard = [group_mean(rows, hardness) for rows in groups.values()]
        ss, df = 0.0, 0
        for rows in groups.values():
            values = [v for v in (dissolution(r) for r in rows) if not math.isnan(v)]
            if len(values) > 1:
                mean = sum(values) / len(values)
                ss += sum((v - mean) ** 2 for v in values)
                df += len(values) - 1
        noise = result.replicate_noise.get("dissolution_30min_pct", {})
        reasons = Counter(r[col["failure_reason"]] or "(not given)" for r in failed)
        problems = {
            "row accounting": (a.rows_read, a.failed_set_aside, a.replicates_merged, a.dropped_missing, a.rows_out) == (len(body), len(failed), merged, 0, len(groups)) and a.balanced,
            "the table has one row per recipe": len(f) == len(groups) and f["replicate_count"].sum() == sum(len(g) for g in groups.values()),
            "combined dissolution means": same(f["dissolution_30min_pct"].tolist(), expected_diss, 1e-9),
            "combined hardness means": same(f["hardness_kp"].tolist(), expected_hard, 1e-9),
            "pooled replicate scatter of dissolution": bool(noise) and abs(noise["pooled_sd"] - math.sqrt(ss / df)) < 1e-9 and noise["degrees_of_freedom"] == df,
            "failed rows kept for failure statistics": result.failed is not None and len(result.failed) == len(failed) and dict(result.failure_stats["by_reason"]) == dict(reasons),
            "no failed run left in the model table": "failed" not in set(f["status"].dropna()),
            "individual replicate rows kept": result.replicate_rows is not None and len(result.replicate_rows) == sum(len(g) for g in groups.values() if len(g) > 1),
            "the headline names the failed runs": f"{len(failed):,} FAILED RUNS" in a.headline() if failed else True,
        }
        wrong = [k for k, ok in problems.items() if not ok]
        cl.record(not wrong, f"{name} (synthetic mock data) with failed runs and replicates: {len(body):,} rows read, {len(failed)} failed runs set aside and kept for statistics, "
                             f"{merged} replicate rows combined, {len(groups):,} rows left; every combined mean and the replicate scatter equal an independent recount", "; ".join(wrong))


def row_accounting_property(cl: Checklist) -> None:
    """120 random small tables with every combination of the failed-run, missing-value and replicate settings: the counts must always add up and match."""
    rng = random.Random(555)
    wrong = []
    for number in range(120):
        rows = [(f"E{rng.randint(1, 8)}", "" if rng.random() < 0.2 else str(rng.randint(1, 9)), "failed" if rng.random() < 0.2 else "ok") for _ in range(rng.randint(3, 25))]
        failed_policy = rng.choice(["keep", "exclude", "exclude_from_models_keep_in_failure_statistics"])
        missing_policy = rng.choice(["skip_for_that_response", "drop_row"])
        rule = rng.choice(["mean", "median", "keep_all"])
        data = {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id", "status": "state"}, "missing_values": {"policy": missing_policy},
                "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": failed_policy},
                "replicates": {"group_by": ["experiment_id"], "rule": rule, "keep_individual_rows_for_noise_estimate": rng.random() < 0.5}}
        result = ingest_cases.clean_text("id,drug,state\n" + "\n".join(",".join(r) for r in rows) + "\n", data, **ingest_cases.DRUG)
        remaining = [r for r in rows if not (failed_policy != "keep" and r[2] == "failed")]
        after_drop = [r for r in remaining if not (missing_policy == "drop_row" and r[1] == "")]
        merged = 0 if rule == "keep_all" else len(after_drop) - len({r[0] for r in after_drop})
        expected = (len(rows), len(rows) - len(remaining), len(remaining) - len(after_drop), merged, len(after_drop) - merged)
        if not result.ok:
            wrong.append(f"#{number}: refused: " + "; ".join(f.message for f in result.findings if f.level == "error")[:100])
            continue
        a = result.account
        got = (a.rows_read, a.failed_set_aside, a.dropped_missing, a.replicates_merged, a.rows_out)
        if got != expected or not a.balanced or len(result.frame) != a.rows_out:
            wrong.append(f"#{number}: counts {got} but an independent count gives {expected}")
    cl.record(not wrong, "Row accounting: in 120 random tables (every mix of failed-run policy, missing-value policy and replicate rule) the counts of rows dropped, failed runs set aside and replicate rows combined always add up and equal an independent count",
              "; ".join(wrong[:2]))


def headline_checks(cl: Checklist) -> None:
    from cellpoc.ingest import RowAccount

    changed = ingest_cases.clean_text("id,drug,state\nE1,1,ok\nE1,3,ok\nE2,,ok\nE3,4,failed\nE4,5,ok\n",
                                      {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id", "status": "state"}, "missing_values": {"policy": "drop_row"},
                                       "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": "exclude"}, "replicates": {"group_by": ["experiment_id"], "rule": "mean"}},
                                      **ingest_cases.DRUG)
    lines = changed.account.headline().splitlines()
    top = "\n".join(lines[:4])
    cl.record(lines[0].startswith("ROW ACCOUNTING: 5 rows read -> 2 rows in the table") and "1 ROWS DROPPED" in top and "1 FAILED RUNS" in top and "** " in top
              and any(f.rule == "I58" and f.level == "warning" for f in changed.findings) and any(f.rule == "I84" and f.level == "warning" for f in changed.findings),
              "The row-accounting headline puts rows DROPPED and FAILED RUNS in capitals, with their counts, in its first lines; the same facts are warnings (not notes) in the message list", lines[1] if len(lines) > 1 else "")
    clean = RowAccount(rows_read=10, rows_out=10)
    broken = RowAccount(rows_read=10, rows_out=9)
    cl.record("Every row read is in the table." in clean.headline() and clean.balanced and not broken.balanced and "WARNING: the counts do not add up" in broken.headline(),
              "A table where nothing was removed says so; a headline whose counts do not add up says that loudly", "")
    first = min((f for f in changed.findings if f.level == "warning"), key=lambda f: f.rule == "I84", default=None)
    cl.record(first is not None and any(f.rule == "I84" for f in changed.findings) and changed.findings.index(next(f for f in changed.findings if f.rule == "I84")) < len([f for f in changed.findings if f.level != "note"]),
              "The row-accounting message is listed among the warnings, ahead of every note", "")


def two_digit_year_checks(cl: Checklist) -> None:
    from cellpoc.ingest.dates import TWO_DIGIT_YEAR_PIVOT, TWO_DIGIT_YEAR_RULE

    two = ingest_cases.clean_text("when,drug\nnov.18,1\njan.70,2\ndec.69,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "mon.yy", "language": "sl"}}, **ingest_cases.DRUG)
    four = ingest_cases.clean_text("when,drug\n01.11.2018,1\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "dd.mm.yyyy"}}, **ingest_cases.DRUG)
    finding = next((f for f in two.findings if f.rule == "I71"), None)
    note = next((r.notes for r in two.columns if r.id == "date"), [])
    cl.record(finding is not None and "3 date(s)" in finding.text and TWO_DIGIT_YEAR_RULE in finding.text and "'nov.18' became 2018-11-01" in finding.text
              and any(TWO_DIGIT_YEAR_RULE in n for n in note) and finding.level == "warning",
              "Wherever a 2-digit year is interpreted the rule is stated: in a warning (with the count and an example) and in the date column's report", finding.text[:100] if finding else "no message")
    cl.record(not any(f.rule == "I71" for f in four.findings) and not any("2-digit" in n for r in four.columns for n in r.notes),
              "Dates with 4-digit years produce no 2-digit-year message", "")
    text = DOC_PATH.read_bytes().decode("utf-8")
    cl.record(TWO_DIGIT_YEAR_RULE in text and "Fixed rules the reader applies" in text and TWO_DIGIT_YEAR_PIVOT == 70,
              f"docs/ingest_messages.md states the 2-digit-year rule in its own section: {TWO_DIGIT_YEAR_RULE}", "")


def rule_semantics(cl: Checklist) -> None:
    """Replicates, failed runs and joins on tiny tables with known answers."""
    base = {"column_map": {"y": "dissolution_30min_pct"}, "id_columns": {"experiment": "id", "replicate": "rep", "batch": "batch", "date": "d", "status": "s", "failure_reason": "why"},
            "date": {"format": "yyyy-mm-dd"}}
    targets = {"targets": {"constraints": [{"response": "dissolution_30min_pct", "unit": "%", "goal": "at_least", "value": 85}], "objectives": []}}
    table = ("id,rep,batch,d,s,why,y\nA,1,B1,2025-01-01,ok,,1\nA,2,B1,2025-01-01,ok,,3\nB,1,B1,2025-01-02,ok,,5\nB,2,B1,2025-01-02,ok,,5\nB,3,B1,2025-01-02,ok,,8\n"
             "C,1,B2,2025-02-01,failed,jam,\nD,1,B2,2025-02-03,failed,jam,\nE,1,B3,2025-03-01,failed,clog,\nF,1,B3,2025-03-02,ok,,\n")
    cfg = lambda rule, keep=True, policy="exclude_from_models_keep_in_failure_statistics": {  # noqa: E731
        **base, "failed_runs": {"status_column": "s", "failed_value": "FAILED ", "policy": policy},
        "replicates": {"group_by": ["experiment_id"], "rule": rule, "keep_individual_rows_for_noise_estimate": keep}}
    mean = ingest_cases.clean_text(table, cfg("mean"), **targets)
    median = ingest_cases.clean_text(table, cfg("median"), **targets)
    values = mean.frame["dissolution_30min_pct"].tolist()
    medians = median.frame["dissolution_30min_pct"].tolist()
    cl.record(mean.ok and mean.frame["experiment_id"].tolist() == ["A", "B", "F"] and values[:2] == [2.0, 6.0] and math.isnan(values[2]) and medians[:2] == [2.0, 5.0]
              and mean.frame["replicate_count"].tolist() == [2, 3, 1] and "replicate_no" not in mean.frame.columns,
              "Replicates: groups [1,3] and [5,5,8] give means 2 and 6 (medians 2 and 5), a group with no value stays empty, replicate counts are kept, and the replicate-number column is dropped", str(values))
    pooled = mean.replicate_noise["dissolution_30min_pct"]
    cl.record(abs(pooled["pooled_sd"] - math.sqrt((2 + 6) / 3)) < 1e-12 and pooled["degrees_of_freedom"] == 3 and len(mean.replicate_rows) == 5,
              "The replicate scatter is kept for noise estimates: pooled standard deviation sqrt(8/3) on 3 degrees of freedom, and the 5 individual replicate rows", "")
    stats = mean.failure_stats
    cl.record(stats["count"] == 3 and dict(stats["by_reason"]) == {"jam": 2, "clog": 1} and dict(stats["by_month"]) == {"2025-02": 2, "2025-03": 1} and dict(stats["by_batch"]) == {"B2": 2, "B3": 1}
              and len(mean.failed) == 3 and mean.account.failed_set_aside == 3,
              "Failed runs (matched ignoring capitals and spaces) are set aside and their statistics kept: 3 failures, by reason (jam 2, clog 1), by batch and by month", "")
    kept = ingest_cases.clean_text(table, cfg("mean", policy="keep"), **targets)
    excluded = ingest_cases.clean_text(table, cfg("mean", policy="exclude"), **targets)
    cl.record(kept.account.failed_set_aside == 0 and "is_failed" in kept.frame.columns and kept.frame["is_failed"].sum() == 3 and excluded.failed is None and excluded.failure_stats is None and excluded.account.failed_set_aside == 3,
              "Failed-run policies: 'keep' leaves them in the table flagged is_failed, 'exclude' removes them and keeps nothing", "")
    every = ingest_cases.clean_text(table, cfg("keep_all"), **targets)
    cl.record(len(every.frame) == 6 and every.account.replicates_merged == 0 and every.frame["replicate_count"].tolist() == [2, 2, 3, 3, 3, 1],
              "Replicate rule 'keep_all' keeps every row and records how many rows share each recipe", "")
    unknown = ingest_cases.clean_text("id,drug,x\nA,1,2\nB,1,3\nA,2,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"},
                                                                          "replicates": {"group_by": ["experiment_id"], "rule": "mean"}}, **ingest_cases.DRUG)
    missing_key = ingest_cases.clean_text("id,drug\nA,1\n,2\n,4\nA,3\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id"},
                                                                          "replicates": {"group_by": ["experiment_id"], "rule": "mean"}}, **ingest_cases.DRUG)
    cl.record(unknown.frame["drug_pct"].tolist() == [1.5, 1.0] and len(missing_key.frame) == 3 and missing_key.account.replicates_merged == 1,
              "Rows with no recipe ID are never merged with each other (an unknown is not a match); only rows with the same ID are combined", "")
    files = {"main.csv": "id,drug\n E1 ,1\ne2,2\nE3,3\n,4\n", "other.csv": "ID,extra_value\nE1,10\nE2,20\nE9,90\n"}
    joined = ingest_cases.clean_files(files, {**ingest_cases.JOIN, "joins": [{"file": "other.csv", "prefix": "o_", "on": [{"main": "id", "joined": "id"}]}],
                                              "column_map": {"drug": "drug_pct", "o_extra_value": "extra_x"}}, **ingest_cases.DRUG)
    got = joined.frame["extra_x"].tolist()
    cl.record(joined.ok and got[0] == 10.0 and got[1] == 20.0 and math.isnan(got[2]) and math.isnan(got[3]) and len(joined.frame) == 4
              and any(f.rule == "I79" and "2 of 4" in f.text for f in joined.findings) and any(f.rule == "I80" for f in joined.findings),
              "Joins: keys match ignoring capitals and spaces; every main row is kept; rows with no match (including an empty key) get empty cells and are counted; unused joined rows are counted", str(got))


def row_checks(cl: Checklist, available: bool) -> None:
    mock_rows(cl)
    row_accounting_property(cl)
    headline_checks(cl)
    two_digit_year_checks(cl)
    rule_semantics(cl)
    if not available:
        cl.skip("Laboratory.csv joined with Process.csv and Normalization.csv", "SKIPPED: data/public/ files are not on this computer; this is not a pass")
        return
    setup = yaml.safe_load((FIXTURES / "batch_production_joined_setup.yaml").read_text(encoding="utf-8"))
    result = read_and_clean(setup, None, PROJECT_ROOT)
    lab_h, lab = raw_table(PUBLIC / "batch_production" / "Laboratory.csv", ";")
    pro_h, pro = raw_table(PUBLIC / "batch_production" / "Process.csv", ";")
    nor_h, nor = raw_table(PUBLIC / "batch_production" / "Normalization.csv", ";")
    L, P, N = ({h: i for i, h in enumerate(x)} for x in (lab_h, pro_h, nor_h))
    process_by_batch = {(r[P["batch"]], r[P["code"]]): r for r in pro}
    norm_by_code = {r[N["Product code"]]: r for r in nor}
    if not result.ok:
        cl.record(False, "Laboratory.csv joined with Process.csv and Normalization.csv", "; ".join(f.message for f in result.findings if f.level == "error")[:200])
        return
    f = result.frame
    speed = [nan_or(process_by_batch[(r[L["batch"]], r[L["code"]])][P["tbl_speed_mean"]]) for r in lab]
    release = [nan_or(process_by_batch[(r[L["batch"]], r[L["code"]])][P["Drug release average (%)"]].replace("#N/A", "")) for r in lab]
    factor = [float(norm_by_code[r[L["code"]]][N["Normalisation factor"]]) for r in lab]
    cl.record(len(f) == len(lab) == 1005 and same(f["tbl_speed_mean"].tolist(), speed, 0.0) and same(f["drug_release_average"].tolist(), release, 0.0) and same(f["normalisation_factor"].tolist(), factor, 0.0)
              and sum(1 for x in result.findings if x.rule == "I81" and "1,005 of 1,005" in x.text) == 2 and not any(x.rule == "I79" for x in result.findings),
              "Laboratory.csv joined with Process.csv (on batch and product code) and Normalization.csv (on product code), real public data: all 1,005 rows match, and every joined value equals the one found by an independent lookup",
              f"{len(f)} rows")
    differs = [i for i, r in enumerate(lab) if r[L["size"]] != norm_by_code[r[L["code"]]][N["Batch Size (tablets)"]]]
    seen = [i for i, (a, b) in enumerate(zip(f["norm_batch_size"].tolist(), f["batch_size"].tolist())) if a != b]
    ratio_ok = all(abs(f["batch_size"].iloc[i] / f["norm_batch_size"].iloc[i] - 10) < 1e-9 and f["product_code"].iloc[i] in ("14", "16") for i in seen)
    cl.record(seen == differs and len(seen) == 13 and ratio_ok and Counter(f["product_code"].iloc[i] for i in seen) == {"14": 11, "16": 2} and same(f["normalisation_factor"].tolist(), [s / 100000 for s in f["norm_batch_size"].tolist()], 1e-9),
              "A real inconsistency in the public data is visible after the join, and is exactly the one an independent comparison finds: 13 Laboratory rows (11 of product code 14 and 2 of product code 16) give the batch size as 4,800,000 where Normalization.csv says 480,000 (ten times more); every other row agrees, and the factor is always the Normalization batch size divided by 100,000",
              f"{len(seen)} rows differ")
    na = sum(1 for r in lab for _ in [0] if process_by_batch[(r[L["batch"]], r[L["code"]])][P["Drug release average (%)"]] == "#N/A")
    cl.record(int(f["drug_release_average"].isna().sum()) == na == 18 and result.account.balanced and result.account.rows_out == 1005,
              "The 18 '#N/A' values from the joined Process file come out as missing; the row accounting says all 1,005 rows are in the table", "")


def section(text: str, title: str) -> str:
    start = text.find(f"\n## {title}\n")
    if start == -1:
        return ""
    end = text.find("\n## ", start + 5)
    return text[start:end if end != -1 else None]


def report_checks(cl: Checklist, available: bool) -> None:
    """Stage 2e: the quality report. Every check below reads the actual generated report text."""
    from cellpoc.ingest import DataLabel, build_report, data_label, report_for_setup
    from cellpoc.ingest.report import FileLabel, NO_TABLE_LINE

    example = load_setup(example_setup_path()).setup
    reports = {}
    for name in ("mock_formulation_small.csv", "mock_formulation_experiments.csv", "mock_formulation_hard.csv"):
        s = copy.deepcopy(example)
        s["data"]["experiments_file"] = f"data/mock/{name}"
        reports[name] = report_for_setup(s, None, PROJECT_ROOT)
    fixtures = {}
    if available:
        for stem in ("literature", "laboratory", "process", "batch_production_joined"):
            fixtures[stem] = report_for_setup(yaml.safe_load((FIXTURES / f"{stem}_setup.yaml").read_text(encoding="utf-8")), None, PROJECT_ROOT)

    # 1. the report opens with the row-accounting headline (the real text, not the helper)
    def opens_with_headline(result, text) -> bool:
        title, _, rest = text.partition("\n\n")
        return title.startswith("# Data quality report [") and rest.startswith("```\n" + result.account.headline() + "\n```\n\n## Data status")

    wrong = [name for name, (result, text) in {**reports, **fixtures}.items() if not opens_with_headline(result, text)]
    first_result, first_text = next(iter(reports.values()))
    block = "```\n" + first_result.account.headline() + "\n```\n\n"
    moved = first_text.replace(block, "", 1).replace("\n## Every message", "\n## Row accounting\n\n" + block + "## Every message", 1)
    cl.record(opens_with_headline(first_result, first_text) and not opens_with_headline(first_result, moved) and not opens_with_headline(first_result, first_text.replace("ROW ACCOUNTING", "Row accounting", 1)),
              "Self-test: a report whose row-accounting block is moved down the page, or whose wording is changed, is caught by the 'opens with the headline' check", "")
    cl.record(not wrong and len(reports) + len(fixtures) >= 3, f"Each of the {len(reports) + len(fixtures)} generated reports opens with its title and then, immediately, the row-accounting block (RowAccount.headline(), word for word), before any other section",
              "; ".join(wrong))
    hard = reports["mock_formulation_hard.csv"][1].splitlines()
    cl.record(any(line.startswith("  ** 268 FAILED RUNS") for line in hard[:8]) and hard.index("## Data status") > hard.index("```") + 2,
              "In the hard mock file's report the 268 failed runs appear in capitals within the first lines, ahead of everything else", hard[4] if len(hard) > 4 else "")
    sample = ingest_cases.clean_text("id,drug,state\nE1,1,ok\nE1,3,ok\nE2,,ok\nE3,4,failed\nE4,5,ok\n",
                                     {"column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id", "status": "state"}, "missing_values": {"policy": "drop_row"},
                                      "failed_runs": {"status_column": "state", "failed_value": "failed", "policy": "exclude"}, "replicates": {"group_by": ["experiment_id"], "rule": "mean"}},
                                     **ingest_cases.DRUG)
    setup_sample = {"data": {"experiments_file": "t.csv", "provenance": {"data_status": "synthetic", "label": "test"}, "column_map": {"drug": "drug_pct"}, "id_columns": {"experiment": "id", "status": "state"},
                             "missing_values": {"policy": "drop_row"}}, **ingest_cases.DRUG}
    sample_text = build_report(sample, setup_sample, data_label(setup_sample, None, PROJECT_ROOT, ["t.csv"]), ["t.csv"])
    top = sample_text.splitlines()[:9]
    cl.record(any("** 1 ROWS DROPPED" in line for line in top) and any("** 1 FAILED RUNS" in line for line in top) and top[0].startswith("# Data quality report ["),
              "A report on a table where rows were dropped and failed runs set aside shows both, in capitals with counts, in its first lines (not only in a detailed log)", "\n".join(top[2:5]))
    cl.record(any("`I58`" in line and "ROWS DROPPED" in line for line in section(sample_text, "What needs your attention").splitlines())
              and "ROWS DROPPED" in section(sample_text, "Every message"),
              "The same dropped-row warning is repeated under 'What needs your attention' and in the full message list", "")
    refused = ingest_cases.clean_text("a,b\n1,2\n", {"column_map": {"nope": "drug_pct"}}, **ingest_cases.DRUG)
    synthetic_setup = {"data": {"provenance": {"data_status": "synthetic"}}}
    refused_text = build_report(refused, synthetic_setup, data_label(synthetic_setup, None, PROJECT_ROOT, ["t.csv"]), ["t.csv"])
    cl.record(NO_TABLE_LINE in refused_text.split("\n\n", 2)[1] and "**ERROR** `I41`" in refused_text and refused_text.startswith("# Data quality report [SYNTHETIC DATA]"),
              "A file that could not be used still gets a report: labelled, opening with 'no table was produced', and listing the error", "")

    # 2. data status labels
    mocks_ok = all(t.startswith("# Data quality report [SYNTHETIC DATA]: ") and "| synthetic |" in section(t, "Data status") and "the companion file experiments_example.meta.json" in section(t, "Data status")
                   for _, t in reports.values())
    cl.record(mocks_ok, "Every mock file's report is labelled SYNTHETIC DATA in its title and in its data-status table, with the label taken from the table's companion file", "")
    if available:
        bad = []
        for stem, (result, text) in fixtures.items():
            status = section(text, "Data status")
            files = [result.raw.info.name] + [i.name for i in result.raw.joined_infos]
            rows = [row for row in status.splitlines() if row.startswith("| ") and "---" not in row and "| File |" not in row]
            if not (text.startswith("# Data quality report [REAL PUBLIC DATA, NOT CLIENT DATA]: ") and all(f"| {n} | real |" in status for n in files) and "is not client data" in status
                    and len(rows) == len(files) and all("REAL PUBLIC DATA, NOT CLIENT DATA" in row for row in rows)):
                bad.append(stem)
        cl.record(not bad, "The reports on the real public data say 'REAL PUBLIC DATA, NOT CLIENT DATA' in their title and give every file read (three for the joined batch data) its own row in the data-status table",
                  ", ".join(bad))
    else:
        cl.skip("The reports on the real public data are labelled 'REAL PUBLIC DATA, NOT CLIENT DATA'", "SKIPPED: data/public/ files are not on this computer; this is not a pass")
    two = DataLabel((FileLabel("a", "synthetic", "", "", "", None), FileLabel("b", "real", "", "", "", False)))
    three = DataLabel((FileLabel("a", "real", "", "", "", False), FileLabel("b", "validated", "", "", "", False)))
    four = DataLabel((FileLabel("a", "unstated", "", "", "", None),))
    five = DataLabel((FileLabel("a", "real", "", "", "", None),))
    real_setup = {"data": {"provenance": {"data_status": "real"}}}
    reminder = build_report(sample, real_setup, data_label(real_setup, None, PROJECT_ROOT, ["t.csv"]), ["t.csv"])
    cl.record(two.status == "synthetic" and two.short == "SYNTHETIC DATA" and three.status == "real" and four.status == "illustrative" and four.short == "ILLUSTRATIVE DATA (data status not stated)"
              and five.short == "REAL DATA" and "data-handling policy must be approved" in reminder and reminder.startswith("# Data quality report [REAL DATA]"),
              "The weakest-input rule from Stage 1 holds: synthetic + real is labelled synthetic; real + validated is real; no stated status is labelled illustrative; real data that might be client data carries the data-handling reminder", "")

    # 3. every assumption is in the report, in words
    if available:
        text = fixtures["literature"][1]
        assumptions, columns, attention = section(text, "Assumptions and rules applied"), section(text, "Columns"), section(text, "What needs your attention")
        table_rows = [r for r in columns.splitlines() if r.startswith("| `")]
        assumed_rows = [r.split("|")[1].strip() for r in table_rows if "**ASSUMED**" in r]
        needed = ["**ASSUMED CONVERSION:**", "1,982 value(s) of `hardness_kp`", "from kg/cm2 to kP by dividing by 1", "taken as kilopond", "**ASSUMED WEIGHT CHECK (mg to percent):**",
                  "118 of 1,982 rows (6.0%)", "Stated tolerance: 2% of the weight", "not** rescaled to 100%", "**ASSUMED UNIT: `sodium_saccharine_mg`**", "unit assumed, not confirmed by the dataset's dictionary"]
        missing = [n for n in needed if n not in assumptions]
        cl.record(not missing and "ASSUMED UNIT: `sodium_saccharin_mg`" not in text and "ASSUMED UNIT: `dibasic_calcium_phosphate_mg`" not in text,
                  "The literature report states every assumption in its own section, in words, with counts: the kg/cm2-to-kP hardness conversion (1,982 values), the mg-to-percent weight check (118 of 1,982 rows beyond the 2% tolerance, nothing rescaled), and the one unit the dictionary does not confirm (and not the two it does)",
                  ", ".join(missing))
        cl.record(sorted(assumed_rows) == sorted(["`sodium_saccharine_mg`", "`sodium_saccharine_pct`", "`hardness_kp`"]),
                  "In the report's column table exactly three columns are marked **ASSUMED**: sodium_saccharine_mg, the percentage made from it, and hardness_kp; the 56 confirmed mg columns are not", ", ".join(assumed_rows))
        cl.record("`I52`" in attention and "`I51`" in attention and "`I59`" in attention and "assumed, not exact" in attention,
                  "The same assumptions also appear as warnings under 'What needs your attention'", "")
        weight = section(text, "Weight check")
        cl.record("-32.00%" in weight and "| 1,879 |" in weight and "exactly balanced" in weight,
                  "The weight-check section shows the exact gap of the worst rows (for example row 1,879, -32.00%) and how many rows balance exactly", "")
        lab = fixtures["laboratory"][1]
        two_digit_text = "00 to 69 mean 2000 to 2069, and 70 to 99 mean 1970 to 1999"
        cl.record(two_digit_text in section(lab, "What needs your attention") and two_digit_text in section(lab, "Assumptions and rules applied") and two_digit_text in section(lab, "Dates")
                  and "1,005 date(s)" in section(lab, "Assumptions and rules applied") and "'nov.18' became 2018-11-01" in lab and "MONTH-ONLY DATES" in lab,
                  "Laboratory.csv's report states the 2-digit-year rule in three places (what needs attention, assumptions, dates) with the count (1,005) and an example ('nov.18' became 2018-11-01), plus the month-only warning",
                  "")
    else:
        cl.skip("The literature and Laboratory reports state their assumptions in words", "SKIPPED: data/public/ files are not on this computer; this is not a pass")
    yy = ingest_cases.clean_text("when,drug\nnov.18,1\njan.70,2\n", {"column_map": {"drug": "drug_pct"}, "id_columns": {"date": "when"}, "date": {"format": "mon.yy", "language": "sl"}}, **ingest_cases.DRUG)
    yy_setup = {"data": {"provenance": {"data_status": "synthetic"}, "date": {"format": "mon.yy", "language": "sl"}, "id_columns": {"date": "when"}, "column_map": {"drug": "drug_pct"}}, **ingest_cases.DRUG}
    yy_text = build_report(yy, yy_setup, data_label(yy_setup, None, PROJECT_ROOT, ["t.csv"]), ["t.csv"])
    iso_text = reports["mock_formulation_small.csv"][1]
    cl.record("2 date(s)" in section(yy_text, "Assumptions and rules applied") and "TWO-DIGIT" in yy_text and "TWO-DIGIT" not in iso_text and "2-digit" not in iso_text,
              "A table with 2-digit years always shows the rule in its report; the mock files, whose dates have 4-digit years, never mention it", "")

    # 4. the report is a clean, repeatable document
    small_setup = copy.deepcopy(example)
    small_setup["data"]["experiments_file"] = "data/mock/mock_formulation_small.csv"
    again = report_for_setup(small_setup, None, PROJECT_ROOT)[1]
    every = [t for _, t in reports.values()] + [t for _, t in fixtures.values()]
    forbidden = re.compile(r"np\.|\bnan\b|\bNone\b|Traceback|\{|\}|\d{2}:\d{2}:\d{2}")
    messy = [t.splitlines()[0][:60] for t in every if forbidden.search(re.sub(r"'[^']*'", "''", re.sub(r"```.*?```", "", t, flags=re.S)))]
    cl.record(again == reports["mock_formulation_small.csv"][1] and not messy, "Reports are repeatable (the same input gives the same report, no clock time) and contain no code-like text (no nan, None, braces or tracebacks)", "; ".join(messy[:2]))
    broken = []
    for t in every:
        block = []
        for line in t.splitlines() + [""]:
            if line.startswith("|"):
                block.append(len(re.findall(r"(?<!\\)\|", line)))
            else:
                if block and len(set(block)) != 1:
                    broken.append(t.splitlines()[0][:50])
                block = []
    cl.record(not broken, "Every table in every report is well formed (each row has as many cells as its header)", "; ".join(broken[:2]))
    result0 = reports["mock_formulation_experiments.csv"][0]
    cl.record(f"All {len(result0.findings)} messages" in reports["mock_formulation_experiments.csv"][1] and all(f.rule in reports["mock_formulation_experiments.csv"][1] for f in result0.findings),
              "The report's full message list contains every message the reader produced", "")

    # 5. the tool that writes reports
    with tempfile.TemporaryDirectory() as folder:
        done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "make_quality_report.py"), "all", "--out", folder], capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace")
        written = sorted(Path(folder).glob("*_quality_report.md"))
        small = Path(folder) / "mock_formulation_small_quality_report.md"
        same_file = small.exists() and small.read_bytes().decode("utf-8") == reports["mock_formulation_small.csv"][1]
        opens = all(p.read_bytes().decode("utf-8").startswith("# Data quality report [") for p in written)
    expected_files = 3 + (4 if available else 0)
    cl.record(done.returncode == 0 and len(written) == expected_files and same_file and opens,
              f"tools/make_quality_report.py (the double-click make_example_reports.bat) writes {expected_files} reports and each is identical to the one built directly", f"{len(written)} written; exit code {done.returncode}")


def cleaning_checks(cl: Checklist) -> None:
    mock_cleaning(cl)
    available = all((PUBLIC / rel).exists() for rel in ("batch_production/Laboratory.csv", "batch_production/Process.csv", "formulation_literature/final Data All Exipients.csv",
                                                      "formulation_literature/dataverse_files.zip"))
    laboratory_cleaning(cl, available)
    literature_cleaning(cl, available)
    cleaning_rules(cl)
    row_checks(cl, available)
    report_checks(cl, available)
    cleaning_damage(cl)
    unlabeled = [p.name for p in FIXTURES.glob("*.yaml") if "never presented as client data" not in p.read_text(encoding="utf-8")]
    cl.record(not unlabeled and all(p.stat().st_size < 20_000 for p in FIXTURES.glob("*.yaml")),
              "The committed fixture setups hold no data (each is a few kilobytes) and say they describe real public data, never client data", ", ".join(unlabeled))


def main() -> int:
    cl = Checklist("PLATFORM STAGE 2: reading, cleaning and reporting on data files")
    before = project_files()
    results = ingest_cases.run_all()
    message_checks(cl, results)
    known_file_checks(cl)
    fresh_mock_checks(cl)
    variant_matrix(cl)
    damage_test(cl)
    safety_checks(cl)
    cleaning_checks(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project (the reader and its tests leave no files behind)", ", ".join(changed[:3]))
    architecture.check(cl)
    cl.headline("Reading only: real public files and mock files are used to test the reader and are never presented as client data.")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
