"""From a table of text to typed values: numbers, dates, units, missing values, below-detection values, and the weight check.

What the setup says is the authority; nothing here is guessed or filled in:
- text meaning "no value" is only what the setup lists (plus empty cells), and every marker found is counted;
- a cell that is not clearly a number is reported and set to missing, never turned into a number;
- units are only converted by conversions the setup declares, and a conversion or a unit marked "assumed" is reported as assumed;
- dates are read exactly as the setup's date format says (day and month are never guessed);
- amounts in mg become a percentage of the stated total weight, and the exact gap between the amounts and that weight is kept for every row.

The result carries a per-column report (what each column is, its unit and whether that is confirmed or assumed, how many values were missing,
converted or flagged), so the quality report (a later step) can say where every number came from.
"""
from __future__ import annotations

import difflib
import math
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from cellpoc.setup.tablefile import match_key

from cellpoc.setup.files import path_is_safe, resolve_reference

from .dates import ISO, PLAUSIBLE_YEARS, TWO_DIGIT_YEAR_RULE, DateFormat, parse_excel_date
from .findings import Finding, has_errors, make
from .join import merge_joins
from .parsing import Markers, parse_limit, parse_number
from .reader import RawTable, ReadOptions, ReadResult, read_setup_table, read_table
from .rows import RowAccount, apply_failed_runs, apply_replicates, failure_flags, resolve_group_columns, status_counts

ID_COLUMNS = {"experiment": "experiment_id", "replicate": "replicate_no", "batch": "batch_id", "date": "date", "status": "status", "failure_reason": "failure_reason"}
NEGATIVE_NOT_PLAUSIBLE = {"mg", "g", "min", "s", "h", "kN", "kP", "N", "m"}
DEFAULT_TOLERANCE_PCT = 2.0


# ---------------------------------------------------------------- what the setup says
def _dicts(value) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


@dataclass
class Spec:
    """The parts of a setup that cleaning needs. Built defensively: any part may be missing."""
    data: dict
    roles: dict[str, str] = field(default_factory=dict)       # platform ID -> ingredient / process / context / target / objective
    units: dict[str, str] = field(default_factory=dict)       # platform ID -> the unit the setup gives it
    required: set[str] = field(default_factory=set)           # IDs a row needs for modelling (used by the missing-value policy)

    @classmethod
    def from_setup(cls, setup) -> "Spec":
        setup = setup if isinstance(setup, dict) else {}
        spec = cls(setup.get("data") if isinstance(setup.get("data"), dict) else {})
        for section, role in (("ingredients", "ingredient"), ("process_factors", "process"), ("context_factors", "context")):
            for item in _dicts(setup.get(section)):
                if _text(item.get("id")):
                    spec.roles[item["id"]] = role
                    spec.required.add(item["id"])
                    if _text(item.get("unit")):
                        spec.units[item["id"]] = item["unit"].strip()
        targets = setup.get("targets") if isinstance(setup.get("targets"), dict) else {}
        for key, name, role in (("constraints", "response", "target"), ("objectives", "quantity", "objective")):
            for item in _dicts(targets.get(key)):
                if _text(item.get(name)):
                    spec.roles.setdefault(item[name], role)
                    if _text(item.get("unit")):
                        spec.units.setdefault(item[name], item["unit"].strip())
                    if item.get("required", True) is not False:
                        spec.required.add(item[name])
        return spec

    @property
    def decimal(self) -> str:
        return _text(self.data.get("decimal")) or "auto"

    @property
    def column_map(self) -> dict:
        return {k: v for k, v in (self.data.get("column_map") or {}).items() if isinstance(k, str) and _text(v)} if isinstance(self.data.get("column_map"), dict) else {}

    @property
    def assumed(self) -> dict[str, str]:
        return {item["id"]: _text(item.get("why")) for item in _dicts(self.data.get("assumed_units")) if _text(item.get("id"))}

    @property
    def declared_units(self) -> dict[str, str]:
        units = self.data.get("column_units")
        return {k: v.strip() for k, v in units.items() if isinstance(v, str) and v.strip()} if isinstance(units, dict) else {}


# ---------------------------------------------------------------- what comes out
@dataclass
class ColumnReport:
    id: str
    raw_name: str
    role: str                         # ingredient, process, context, target, objective, id, date, derived, other
    kind: str                         # number, text or date
    unit: str = ""
    unit_status: str = "none"         # "confirmed-by-setup", "declared", "assumed", "converted" or "none"
    unit_note: str = ""               # for an assumed unit: why, in the setup's own words
    n_values: int = 0
    n_missing: int = 0
    n_not_numbers: int = 0
    n_below: int = 0
    n_above: int = 0
    n_converted: int = 0
    minimum: float | None = None
    maximum: float | None = None
    notes: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)                 # extra facts the report states (a date column: its format, precision and 2-digit-year use)
    conversions: list = field(default_factory=list)           # unit conversions applied: {"unit", "divide", "n", "status", "note"}


@dataclass
class CleanResult:
    frame: pd.DataFrame | None
    columns: list[ColumnReport]
    findings: list[Finding]
    source_rows: list[int] = field(default_factory=list)
    dropped: list[tuple[int, str]] = field(default_factory=list)       # (row number in the file, why)
    rows_read: int = 0
    composition: dict | None = None
    raw: RawTable | None = None
    failed: pd.DataFrame | None = None                 # failed runs kept for failure statistics (when the setup says so)
    failure_stats: dict | None = None
    replicate_rows: pd.DataFrame | None = None         # the individual rows behind each combined replicate group (for noise estimates)
    replicate_noise: dict = field(default_factory=dict)
    account: RowAccount = field(default_factory=RowAccount)
    marker_counts: dict = field(default_factory=dict)          # text meaning "no value" that was found, and how often

    @property
    def ok(self) -> bool:
        return self.frame is not None and not has_errors(self.findings)

    def column(self, ident: str) -> ColumnReport:
        return next(c for c in self.columns if c.id == ident)


def read_and_clean(setup: dict, base_dir, root) -> CleanResult:
    """Read the experiments file a setup names, add the columns of any files it joins in, and clean the result, in one call."""
    data = setup.get("data") if isinstance(setup, dict) and isinstance(setup.get("data"), dict) else {}
    main = read_setup_table(setup, base_dir, root)
    joins = []
    for join in _dicts(data.get("joins")):
        reference = join.get("file")
        where = resolve_reference(reference, base_dir, root) if isinstance(reference, str) and path_is_safe(reference) else None
        if where is None:
            missing = make("I01", "", reference if isinstance(reference, str) and reference else "a file to join in")
            return clean_table(ReadResult(None, main.findings + [missing]), setup)
        joins.append((join, read_table(where, ReadOptions(decimal=_text(data.get("decimal")) or "auto")), where.name))
    return clean_table(merge_joins(main, joins), setup)


# ---------------------------------------------------------------- the cleaning
def _near(name: str, keys: dict[str, str]) -> str:
    close = difflib.get_close_matches(match_key(name), list(keys), n=1, cutoff=0.6)
    return keys[close[0]] if close else ""


def _examples(values, limit: int = 3) -> str:
    shown = [repr(v) for v in list(dict.fromkeys(values))[:limit]]
    return ", ".join(shown) + (", ..." if len(set(values)) > limit else "")


def clean_table(read: ReadResult, setup: dict) -> CleanResult:
    """Clean the table a reader returned. Reader findings are kept in front of the cleaning findings."""
    findings: list[Finding] = list(read.findings)
    if read.table is None or has_errors(findings):
        return CleanResult(None, [], findings, raw=read.table)
    raw = read.table
    spec = Spec.from_setup(setup)
    name = raw.info.name
    frame_in = raw.frame
    total = len(frame_in)
    keys = {match_key(c): c for c in frame_in.columns}

    def find(raw_name: str) -> str | None:
        return keys.get(match_key(raw_name))

    # ---- every column the setup names must exist
    hardness = spec.data.get("hardness") if isinstance(spec.data.get("hardness"), dict) else None
    below = spec.data.get("below_detection") if isinstance(spec.data.get("below_detection"), dict) else None
    id_names = {role: _text(v) for role, v in (spec.data.get("id_columns") or {}).items()} if isinstance(spec.data.get("id_columns"), dict) else {}
    named: list[tuple[str, str]] = [(k, "") for k in spec.column_map]
    named += [(n, role) for role, n in id_names.items() if n and role in ID_COLUMNS]
    if hardness:
        named += [(_text(hardness.get(k)), "") for k in ("value_column", "unit_column") if _text(hardness.get(k))]
    if below and _text(below.get("note_column")):
        named.append((_text(below["note_column"]), ""))
    failed_cfg = spec.data.get("failed_runs") if isinstance(spec.data.get("failed_runs"), dict) else None
    if failed_cfg and _text(failed_cfg.get("status_column")):
        named.append((_text(failed_cfg["status_column"]), ""))
    missing_names = []
    for raw_name, _ in named:
        if find(raw_name) is None and raw_name not in missing_names:
            missing_names.append(raw_name)
            hint = f" Did you mean '{_near(raw_name, keys)}'?" if _near(raw_name, keys) else ""
            have = ", ".join(list(frame_in.columns)[:6]) + (", ..." if len(frame_in.columns) > 6 else "")
            findings.append(make("I41", "", name, raw_name, column=raw_name, have=have, hint=hint))
    seen_ids: dict[str, str] = {}
    hardness_to = _text(hardness.get("to")) if hardness else ""
    for raw_name, ident in spec.column_map.items():
        if ident == hardness_to:
            continue
        if ident in seen_ids:
            findings.append(make("I42", "", name, raw_name, first=seen_ids[ident], second=raw_name, id=ident))
        seen_ids.setdefault(ident, raw_name)
    if has_errors(findings):
        return CleanResult(None, [], findings, raw=raw)

    markers = Markers(spec.data.get("missing_markers"))
    marker_counts: Counter = Counter()
    out: dict[str, list] = {}
    reports: list[ColumnReport] = []
    source_rows = list(raw.source_rows)
    out["source_row"] = source_rows
    cells = {c: frame_in[c].tolist() for c in frame_in.columns}

    # ---- identifying columns
    for role, ident in ID_COLUMNS.items():
        raw_name = id_names.get(role, "")
        column = find(raw_name) if raw_name else None
        if role == "date":
            continue
        if column is None:
            if role == "experiment":
                out[ident] = [f"row{r}" for r in source_rows]
                findings.append(make("I61", "", name, "", example=out[ident][0] if out[ident] else "row2"))
                reports.append(ColumnReport(ident, "", "id", "text", notes=["generated from the row number"], n_values=total))
            continue
        values = [v if v != "" else None for v in cells[column]]
        out[ident] = values
        reports.append(ColumnReport(ident, column, "id", "text", n_values=total - values.count(None), n_missing=values.count(None)))

    # ---- failed runs: which rows the status column marks as failed
    status_raw = find(_text(failed_cfg.get("status_column"))) if failed_cfg and _text(failed_cfg.get("status_column")) else None
    if status_raw is not None and _text(failed_cfg.get("failed_value")):
        out["is_failed"] = failure_flags(cells[status_raw], _text(failed_cfg["failed_value"]))
        findings.append(make("I76", "", name, status_raw, column=status_raw, counts=status_counts(cells[status_raw])))
    elif not failed_cfg:
        findings.append(make("I77", "", name))

    # ---- dates
    date_column = find(id_names.get("date", "")) if id_names.get("date") else None
    if date_column is not None:
        _dates(spec, raw, cells[date_column], date_column, out, reports, findings, name)

    # ---- mapped columns
    hardness_value_column = find(_text(hardness.get("value_column"))) if hardness else None
    below_note = find(_text(below.get("note_column"))) if below and _text(below.get("note_column")) else None
    inferred: list[str] = []
    below_rule = _text(below.get("rule")) if below else ""
    below_limit = _number(below.get("limit")) if below else None
    for raw_name, ident in spec.column_map.items():
        if ident == hardness_to:
            continue
        column = find(raw_name)
        role = spec.roles.get(ident, "other")
        wants_text = role == "context"
        report = ColumnReport(ident, column, role, "text" if wants_text else "number", n_values=total)
        if wants_text:
            values = []
            for text in cells[column]:
                m = markers.is_missing(text)
                if m is not None:
                    if m:
                        marker_counts[m] += 1
                    values.append(None)
                else:
                    values.append(text)
            report.n_missing = values.count(None)
            out[ident] = values
            reports.append(_unit_info(spec, report))
            continue
        numbers = _numbers(spec, cells[column], markers, marker_counts)
        if role == "other":
            inferred.append(ident)
            if numbers.bad and len(numbers.bad) == len([1 for t in cells[column] if markers.is_missing(t) is None]):
                out[ident] = [t if markers.is_missing(t) is None else None for t in cells[column]]       # every value is text: keep it as text
                report.kind, report.n_missing = "text", sum(1 for t in cells[column] if markers.is_missing(t) is not None)
                reports.append(_unit_info(spec, report))
                continue
        _finish_numbers(spec, report, numbers, ident, column, total, out, findings, name, below_rule, below_limit, below_note, below, cells, markers)
        reports.append(_unit_info(spec, report))
    if inferred:
        findings.append(make("I66", "", name, "", n=len(inferred), names=", ".join(inferred[:6]) + (", ..." if len(inferred) > 6 else "")))

    # ---- hardness (one unit per row, or one unit for the column) becomes kP
    if hardness and hardness_value_column is not None and hardness_to:
        _hardness(spec, hardness, hardness_value_column, hardness_to, cells, markers, marker_counts, total, out, reports, findings, name)

    if marker_counts:
        findings.append(make("I64", "", name, "", counts=", ".join(f"'{k}' {v:,}" for k, v in marker_counts.most_common())))
    used_raw = {find(n) for n, _ in named} | ({date_column} if date_column else set())
    unused = [c for c in frame_in.columns if c not in used_raw]
    if unused:
        findings.append(make("I62", "", name, "", n=len(unused), examples=", ".join(f"'{u}'" for u in unused[:4]) + (", ..." if len(unused) > 4 else "")))

    # ---- amounts in mg become a percentage of the total weight, and are checked against it
    composition = None
    if isinstance(spec.data.get("composition"), dict):
        composition = _composition(spec, out, reports, findings, name, total)

    for column_report in reports:
        if column_report.unit_status == "assumed" and column_report.role not in ("derived",) and column_report.id != hardness_to:
            findings.append(make("I51", "", name, column_report.id, column=column_report.id, unit=column_report.unit or "unit not stated", why=column_report.unit_note or "no reason given"))

    if has_errors(findings):
        return CleanResult(None, reports, findings, source_rows, [], total, composition, raw)

    frame = pd.DataFrame(out)
    account = RowAccount(rows_read=total, blank_skipped=raw.info.rows_blank)

    # ---- failed runs are dealt with first: their gaps are expected and must not be counted as 'missing values'
    failed_frame = failure_stats = None
    if "is_failed" in frame.columns:
        failed_policy = _text(failed_cfg.get("policy")) or "exclude_from_models_keep_in_failure_statistics"
        frame, failed_frame, failure_stats, removed = apply_failed_runs(frame, failed_policy, status_raw, _text(failed_cfg["failed_value"]), findings, name)
        account.failed_set_aside, account.failed_policy = removed, failed_policy

    # ---- missing values: the setup's policy
    dropped: list[tuple[int, str]] = []
    policy = _text((spec.data.get("missing_values") or {}).get("policy")) if isinstance(spec.data.get("missing_values"), dict) else ""
    needed = [i for i in (spec.required or {r.id for r in reports if r.role in ("other", "ingredient", "process", "target")}) if i in frame.columns]
    if policy in ("drop_row", "fail") and needed:
        gaps = frame[needed].isna()
        any_gap = gaps.any(axis=1)
        if policy == "fail" and any_gap.any():
            columns = [c for c in needed if gaps[c].any()]
            findings.append(make("I44", "", name, "", n=int(gaps.to_numpy().sum()), columns=", ".join(f"'{c}'" for c in columns[:5]) + (", ..." if len(columns) > 5 else "")))
            return CleanResult(None, reports, findings, source_rows, [], total, composition, raw)
        if policy == "drop_row" and any_gap.any():
            for row in frame.index[any_gap]:
                dropped.append((int(frame.at[row, "source_row"]), "a value is missing"))
            frame = frame[~any_gap].reset_index(drop=True)
            findings.append(make("I58", "dropped", name, "", n=len(dropped), row=dropped[0][0]))
    account.dropped_missing = len(dropped)

    # ---- replicates: rows of the same recipe are combined (and their scatter kept for noise estimates)
    replicate_rows, noise = None, {}
    replicate_cfg = spec.data.get("replicates") if isinstance(spec.data.get("replicates"), dict) else None
    if replicate_cfg and isinstance(replicate_cfg.get("group_by"), list) and replicate_cfg["group_by"] and _text(replicate_cfg.get("rule")):
        aliases = {match_key(raw_name): ID_COLUMNS[role] for role, raw_name in id_names.items() if raw_name and role in ID_COLUMNS}
        aliases.update({match_key(raw_name): ident for raw_name, ident in spec.column_map.items()})
        group_columns = resolve_group_columns([str(g) for g in replicate_cfg["group_by"]], frame, aliases, findings, name)
        if group_columns is None:
            return CleanResult(None, reports, findings, source_rows, dropped, total, composition, raw, account=account)
        responses = [i for i, r in spec.roles.items() if r in ("target", "objective")] + ([hardness_to] if hardness_to else [])
        frame, replicate_rows, noise, merged = apply_replicates(frame, group_columns, _text(replicate_cfg["rule"]),
                                                                replicate_cfg.get("keep_individual_rows_for_noise_estimate") is True, responses, findings, name)
        account.replicates_merged = merged
    account.rows_out = len(frame)
    if account.changed:
        findings.append(make("I84", "changed", name, "", read=f"{account.rows_read:,}", dropped=f"{account.dropped_missing:,}", failed=f"{account.failed_set_aside:,}",
                             failed_where="set aside" if account.failed_set_aside else "(none)", merged=f"{account.replicates_merged:,}", out=f"{account.rows_out:,}"))
    else:
        findings.append(make("I84", "unchanged", name, "", read=f"{account.rows_read:,}"))
    findings.sort(key=lambda f: {"error": 0, "warning": 1, "note": 2}[f.level])
    return CleanResult(frame, reports, findings, [int(r) for r in frame["source_row"]], dropped, total, composition, raw,
                       failed_frame, failure_stats, replicate_rows, noise, account, dict(marker_counts))


# ---------------------------------------------------------------- pieces
@dataclass
class Numbers:
    values: list[float]
    bad: list[str]
    below: list[tuple[int, float, str]] = field(default_factory=list)     # (row position, limit, text)
    above: list[tuple[int, str]] = field(default_factory=list)


def _numbers(spec: Spec, texts: list[str], markers: Markers, marker_counts: Counter) -> Numbers:
    nan = float("nan")
    result = Numbers([nan] * len(texts), [])
    for position, text in enumerate(texts):
        marked = markers.is_missing(text)
        if marked is not None:
            if marked:
                marker_counts[marked] += 1
            continue
        limit = parse_limit(text, spec.decimal)
        if limit:
            (result.below if limit[0] == "<" else result.above).append((position, limit[1], text) if limit[0] == "<" else (position, text))
            continue
        number = parse_number(text, spec.decimal)
        if number is None:
            result.bad.append(text)
        else:
            result.values[position] = number
    return result


def _finish_numbers(spec, report, numbers, ident, column, total, out, findings, name, below_rule, below_limit, below_note, below, cells, markers):
    values = numbers.values
    present = total - sum(1 for t in cells[column] if markers.is_missing(t) is not None)
    if numbers.bad and len(numbers.bad) > 0.5 * max(present, 1):
        findings.append(make("I43", "", name, ident, column=column, n=len(numbers.bad), total=present, example=repr(numbers.bad[0])))
    elif numbers.bad:
        findings.append(make("I46", "", name, ident, column=column, n=len(numbers.bad), examples=_examples(numbers.bad)))
    report.n_not_numbers = len(numbers.bad)
    flag_name = f"{ident}__below_detection"
    flags = None
    # values written inside the cell as '<0.05' or '>100'
    if numbers.below:
        if below_rule:
            flags = [False] * total
            for position, limit, _ in numbers.below:
                values[position] = _apply_rule(below_rule, limit)
                flags[position] = True
            findings.append(make("I53", "", name, ident, column=column, n=len(numbers.below), rule=below_rule, limit="as written in each cell", flag=flag_name))
        else:
            findings.append(make("I55", "", name, ident, column=column, n=len(numbers.below), example=numbers.below[0][2]))
    if numbers.above:
        findings.append(make("I54", "", name, ident, column=column, n=len(numbers.above), example=numbers.above[0][1]))
    report.n_above = len(numbers.above)
    # a note column that says a value is below the limit
    if below and below_note is not None and _text(below.get("quantity")) == ident and _text(below.get("marker")) and below_rule and below_limit is not None:
        marker = _text(below["marker"]).casefold()
        flags = flags or [False] * total
        rows = [i for i, t in enumerate(cells[below_note]) if t.strip().casefold() == marker]
        different = [i for i in rows if not math.isnan(values[i]) and abs(values[i] - below_limit) > 1e-12]
        for i in rows:
            values[i] = _apply_rule(below_rule, below_limit)
            flags[i] = True
        if rows:
            findings.append(make("I53", "", name, ident, column=column, n=len(rows), rule=below_rule, limit=f"{below_limit:g}", flag=flag_name))
        if different:
            findings.append(make("I56", "", name, ident, n=len(different), marker=below["marker"], note=below_note, column=column,
                                 limit=f"{below_limit:g}", example=f"{cells[column][different[0]]!r}"))
    report.n_below = sum(flags) if flags else 0
    if flags:
        out[flag_name] = flags
    out[ident] = values
    finite = [v for v in values if not math.isnan(v)]
    report.n_missing = total - len(finite)
    report.minimum, report.maximum = (min(finite), max(finite)) if finite else (None, None)
    unit = spec.declared_units.get(ident) or spec.units.get(ident) or ""
    if finite and unit == "%" and (report.minimum < 0 or report.maximum > 100):
        n = sum(1 for v in finite if v < 0 or v > 100)
        findings.append(make("I50", "", name, ident, column=ident, n=n, why="outside 0 to 100 percent", low=f"{report.minimum:g}", high=f"{report.maximum:g}"))
    elif finite and unit in NEGATIVE_NOT_PLAUSIBLE and report.minimum < 0:
        findings.append(make("I50", "", name, ident, column=ident, n=sum(1 for v in finite if v < 0), why=f"negative amounts of {unit}", low=f"{report.minimum:g}", high=f"{report.maximum:g}"))
    declared, expected = spec.declared_units.get(ident), spec.units.get(ident)
    if declared and expected and declared != expected and ident not in _converted_ids(spec):
        findings.append(make("I68", "", name, ident, column=ident, declared=declared, expected=expected))


def _converted_ids(spec: Spec) -> set[str]:
    """IDs whose unit changes on purpose (so a difference between the file's unit and the setup's unit is expected): amounts and hardness."""
    comp = spec.data.get("composition") if isinstance(spec.data.get("composition"), dict) else {}
    suffix = _text(comp.get("amount_suffix")) or "_mg"
    ids = {i for i in spec.column_map.values() if comp and i.endswith(suffix)}
    hardness = spec.data.get("hardness") if isinstance(spec.data.get("hardness"), dict) else {}
    return ids | ({_text(hardness.get("to"))} if hardness else set())


def _apply_rule(rule: str, limit: float) -> float:
    if rule == "use_limit_and_flag":
        return limit
    if rule == "use_half_limit":
        return limit / 2
    return float("nan")                          # treat_as_missing


def _unit_info(spec: Spec, report: ColumnReport) -> ColumnReport:
    ident = report.id
    report.unit = spec.declared_units.get(ident) or spec.units.get(ident) or ""
    if ident in spec.assumed:
        report.unit_status, report.unit_note = "assumed", spec.assumed[ident]
    elif ident in spec.declared_units:
        report.unit_status = "declared"
    elif ident in spec.units:
        report.unit_status = "confirmed-by-setup"
    return report


def _dates(spec, raw, texts, column, out, reports, findings, name):
    block = spec.data.get("date") if isinstance(spec.data.get("date"), dict) else None
    fmt = DateFormat.build(_text(block.get("format")), _text(block.get("language")) or "en", block.get("months") if isinstance(block.get("months"), list) else None) if block else None
    if fmt is None:
        fmt = DateFormat.build(ISO)
        findings.append(make("I49", "", name, column))
    parsed, precisions, bad, two_digit = [], [], [], []
    for position, text in enumerate(texts):
        if not text.strip():
            parsed.append(None)
            precisions.append(None)
            continue
        row = raw.source_rows[position]
        value, precision = parse_excel_date(text) if (row, column) in raw.date_cells else fmt.parse(text)
        if value is None:
            bad.append(text)
        elif fmt.two_digit_year and (row, column) not in raw.date_cells:
            two_digit.append((text.strip(), value))
        parsed.append(value)
        precisions.append(precision or None)
    if two_digit:
        findings.append(make("I71", "", name, column, n=f"{len(two_digit):,}", example=two_digit[0][0], result=two_digit[0][1].isoformat()))
    given = sum(1 for t in texts if t.strip())
    shown = block.get("format") if block else ISO
    if bad and len(bad) > 0.5 * max(given, 1):
        findings.append(make("I45", "", name, column, n=len(bad), total=given, format=shown, example=repr(bad[0])))
    elif bad:
        findings.append(make("I48", "", name, column, n=len(bad), total=given, format=shown, examples=_examples(bad)))
    out["date"] = pd.to_datetime(pd.Series(parsed, dtype=object), errors="coerce")
    out["date_precision"] = precisions
    good = [d for d in parsed if d is not None]
    report = ColumnReport("date", column, "date", "date", n_values=len(good), n_missing=len(parsed) - len(good), n_not_numbers=len(bad))
    if good:
        if min(good).year < PLAUSIBLE_YEARS[0] or max(good).year > PLAUSIBLE_YEARS[1]:
            findings.append(make("I50", "", name, "date", column="date", n=sum(1 for d in good if not PLAUSIBLE_YEARS[0] <= d.year <= PLAUSIBLE_YEARS[1]),
                                 why=f"outside the years {PLAUSIBLE_YEARS[0]} to {PLAUSIBLE_YEARS[1]}", low=min(good).isoformat(), high=max(good).isoformat()))
        precision = "month" if all(p == "month" for p in precisions if p) else ("day" if all(p == "day" for p in precisions if p) else "mixed")
        findings.append(make("I65", "range", name, "date", first=min(good).isoformat(), last=max(good).isoformat(), n=f"{len(good):,}", precision=precision))
        if precision == "month":
            months = len({(d.year, d.month) for d in good})
            findings.append(make("I65", "month_only", name, "date", n=months, first=min(good).strftime("%Y-%m"), last=max(good).strftime("%Y-%m")))
        report.notes.append(f"{precision} precision; {min(good).isoformat()} to {max(good).isoformat()}")
    if two_digit:
        report.notes.append(f"{len(two_digit):,} dates had a 2-digit year, read by the rule: {TWO_DIGIT_YEAR_RULE}")
    report.facts.update({"format": shown, "language": (block.get("language") if block else "en") or "en", "assumed_format": block is None or fmt is None,
                         "two_digit": len(two_digit), "two_digit_example": two_digit[0][0] if two_digit else "", "two_digit_result": two_digit[0][1].isoformat() if two_digit else "",
                         "unreadable": len(bad)})
    if good:
        report.facts.update({"first": min(good).isoformat(), "last": max(good).isoformat(), "precision": precision})
    reports.append(report)


def _hardness(spec, hardness, value_column, target_id, cells, markers, marker_counts, total, out, reports, findings, name):
    unit_column_name = _text(hardness.get("unit_column"))
    unit_texts = None
    if unit_column_name:
        keys = {match_key(c): c for c in cells}
        unit_texts = cells.get(keys.get(match_key(unit_column_name), ""))
    fixed = _text(hardness.get("unit"))
    conversions = {match_key(k): (k, v) for k, v in (hardness.get("conversions") or {}).items() if isinstance(v, dict)}
    values = [float("nan")] * total
    per_unit: Counter = Counter()
    unconverted: Counter = Counter()
    bad: list[str] = []
    for position, text in enumerate(cells[value_column]):
        marked = markers.is_missing(text)
        if marked is not None:
            if marked:
                marker_counts[marked] += 1
            continue
        number = parse_number(text, spec.decimal)
        if number is None:
            bad.append(text)
            continue
        unit = unit_texts[position].strip() if unit_texts is not None else fixed
        if not unit:
            unit = fixed
        entry = conversions.get(match_key(unit)) if unit else None
        divide = _number(entry[1].get("divide_by")) if entry else None
        if not unit or entry is None or not divide:
            unconverted[unit or "(no unit)"] += 1
            continue
        values[position] = number / divide
        per_unit[entry[0]] += 1
    report = ColumnReport(target_id, value_column, "target", "number", unit="kP", unit_status="converted", n_values=total)
    if bad:
        findings.append(make("I46", "", name, target_id, column=value_column, n=len(bad), examples=_examples(bad)))
    for unit, n in unconverted.items():
        findings.append(make("I57", "", name, target_id, column=value_column, n=n, unit=unit))
    for unit, n in per_unit.items():
        _, entry = conversions[match_key(unit)]
        divide = f"{entry['divide_by']:g}"
        report.conversions.append({"unit": unit, "divide": divide, "n": n, "status": _text(entry.get("status")) or "exact", "note": _text(entry.get("note"))})
        if entry.get("status") == "assumed":
            report.unit_status, report.unit_note = "assumed", _text(entry.get("note"))
            findings.append(make("I52", "", name, target_id, n=n, column=value_column, unit=unit, target="kP", divide=divide,
                                 note=_text(entry.get("note")) or "no reason given"))
        elif match_key(unit) != match_key("kP"):
            report.n_converted += n
            findings.append(make("I70", "", name, target_id, n=n, column=value_column, unit=unit, divide=divide, target="kP"))
        if entry.get("status") == "assumed":
            report.n_converted += n
    finite = [v for v in values if not math.isnan(v)]
    report.n_missing = total - len(finite)
    report.minimum, report.maximum = (min(finite), max(finite)) if finite else (None, None)
    if finite and report.minimum < 0:
        findings.append(make("I50", "", name, target_id, column=target_id, n=sum(1 for v in finite if v < 0), why="negative hardness", low=f"{report.minimum:g}", high=f"{report.maximum:g}"))
    out[target_id] = values
    reports.append(report)


def _composition(spec, out, reports, findings, name, total):
    block = spec.data["composition"]
    weight_id = _text(block.get("total_weight"))
    suffix = _text(block.get("amount_suffix")) or "_mg"
    tolerance = _number(block.get("tolerance_pct")) or DEFAULT_TOLERANCE_PCT
    if weight_id not in out:
        findings.append(make("I47", "weight_column", name, "", id=weight_id))
        return None
    amounts = [i for i in spec.column_map.values() if i.endswith(suffix) and i != weight_id and i in out]
    clash = next(((a, a[: -len(suffix)] + "_pct") for a in amounts if a[: -len(suffix)] + "_pct" in out), None)
    if clash:
        findings.append(make("I47", "name_clash", name, "", amount=clash[0], new=clash[1]))
        return None
    weights = out[weight_id]
    gaps, flags, unusable = [], [], []
    usable_total = sum(1 for w in weights if not math.isnan(w) and w > 0)
    for row in range(total):
        w = weights[row]
        parts = [out[a][row] for a in amounts]
        if math.isnan(w) or w <= 0 or any(math.isnan(p) for p in parts):
            gaps.append(float("nan"))
            flags.append(False)
            unusable.append(row)
            continue
        gap = (sum(parts) - w) / w * 100
        gaps.append(gap)
        flags.append(round(abs(gap), 9) > tolerance)
    for amount in amounts:
        new = amount[: -len(suffix)] + "_pct"
        out[new] = [(a / w * 100) if (not math.isnan(a) and not math.isnan(w) and w > 0) else float("nan") for a, w in zip(out[amount], weights)]
        source = next((r for r in reports if r.id == amount), None)
        note = "converted from mg to a percentage of the total weight"
        derived = ColumnReport(new, source.raw_name if source else "", "derived", "number", unit="%", unit_status="converted", n_values=total,
                               notes=[note])
        if source and source.unit_status == "assumed":
            derived.unit_status, derived.unit_note = "assumed", f"source unit assumed: {source.unit_note}"
        finite = [v for v in out[new] if not math.isnan(v)]
        derived.n_missing = total - len(finite)
        derived.minimum, derived.maximum = (min(finite), max(finite)) if finite else (None, None)
        reports.append(derived)
    out["mass_balance_gap_pct"] = gaps
    out["mass_balance_flag"] = flags
    reports.append(ColumnReport("mass_balance_gap_pct", "", "derived", "number", unit="%", n_values=total - len(unusable), n_missing=len(unusable),
                                notes=[f"(sum of amounts - total weight) / total weight, in percent; negative = the listed amounts fall short; tolerance {tolerance:g}%"]))
    findings.append(make("I63", "", name, "", n=len(amounts), weight=weight_id))
    if unusable:
        findings.append(make("I60", "", name, "", n=len(unusable), row=out["source_row"][unusable[0]]))
    finite_gaps = [g for g in gaps if not math.isnan(g)]
    flagged = [(out["source_row"][i], gaps[i]) for i in range(total) if flags[i]]
    summary = {"tolerance_pct": tolerance, "rows": len(finite_gaps), "flagged": len(flagged), "flagged_rows": flagged, "amounts": amounts, "weight": weight_id,
               "shortfall_pct": round(min(finite_gaps), 9) if finite_gaps else None, "overshoot_pct": round(max(finite_gaps), 9) if finite_gaps else None}
    if flagged:
        findings.append(make("I59", "flagged", name, "mass_balance_gap_pct", n=f"{len(flagged):,}", total=f"{len(finite_gaps):,}",
                             share=f"{100 * len(flagged) / len(finite_gaps):.1f}%", tolerance=f"{tolerance:g}",
                             shortfall=f"{abs(min(finite_gaps)):.2f}" if min(finite_gaps) < 0 else "0", overshoot=f"{max(max(finite_gaps), 0):.2f}"))
    elif finite_gaps:
        findings.append(make("I59", "ok", name, "mass_balance_gap_pct", total=f"{len(finite_gaps):,}", tolerance=f"{tolerance:g}",
                             gap=f"{max(abs(g) for g in finite_gaps):.2f}"))
    return summary
