"""The modelling table: what the models will see, built from the cleaned table and the setup's `data.validation` section.

For every result to predict it decides, and records, which rows and which inputs are used:
- inputs that would hand the model the answer are left out (the result itself, columns it is calculated from or into, near-copies of it);
- a row with a missing result or a missing input is left out for that result, counted and shown, never filled in;
- the balance ingredient is left out because the percentages add up to 100;
- flags that mean "treat with care" (amounts that do not add up, an assumed unit) travel with the table into every report.
Nothing here splits rows into training and test sets: that is the grouped splitters' job (splits.py), and only they may do it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from cellpoc.ingest import CleanResult, DataLabel, data_label, read_and_clean

from .findings import COPY_CORRELATION, MIN_ROWS, PROXY_PHRASE, Finding, has_errors, make

KIND_WORDS = {"batch": "whole batches", "supplier": "whole suppliers", "date": "later dates", "api": "whole APIs"}


# ---------------------------------------------------------------- what comes out
@dataclass(frozen=True)
class GroupSpec:
    kind: str                       # batch, supplier, date or api
    columns: tuple[str, ...]        # rows sharing all of these belong to one group
    confirmed: bool | None = None   # supplier only: False means the column only stands in for the supplier
    note: str = ""

    @property
    def is_proxy(self) -> bool:
        return self.kind == "supplier" and self.confirmed is not True

    @property
    def heading(self) -> str:
        """How this hold-out is named in every heading, table and chart. A stand-in for the supplier always carries the proxy phrase."""
        names = ", ".join(self.columns) if len(self.columns) <= 3 else f"{self.columns[0]}, {self.columns[1]} and {len(self.columns) - 2} more columns that together name the group"
        where = names + (f"; {PROXY_PHRASE}" if self.is_proxy else "")
        return f"{KIND_WORDS.get(self.kind, self.kind)} ({where})"


@dataclass
class ResponseTable:
    name: str
    rows: np.ndarray                                   # positions in the frame of the rows used: result and every input present
    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    left_out_inputs: list[tuple[str, str]] = field(default_factory=list)      # (input, why: same, source, derived, copy)
    n_missing_result: int = 0
    n_missing_input: int = 0
    usable: bool = True


@dataclass
class ModellingTable:
    name: str
    label: DataLabel | None
    frame: pd.DataFrame | None
    responses: dict[str, ResponseTable] = field(default_factory=dict)
    groups: dict[str, GroupSpec] = field(default_factory=dict)
    derived_from: dict[str, tuple[str, ...]] = field(default_factory=dict)
    unit_assumed: dict[str, str] = field(default_factory=dict)                 # column -> why the unit is assumed
    flag_columns: list[str] = field(default_factory=list)
    left_out: list[tuple[str, str]] = field(default_factory=list)              # (column, why) left out on purpose
    findings: list[Finding] = field(default_factory=list)
    exploratory: str = ""                                                      # why this comparison is exploratory only (empty for the main comparison)
    robustness_only: bool = False                                              # a table that cannot support an accuracy claim (the literature table)

    @property
    def ok(self) -> bool:
        return self.frame is not None and not has_errors(self.findings)

    @property
    def tag(self) -> str:
        """What every heading of every report about this table must carry besides its data-status label ('' for the main comparison)."""
        if self.exploratory:
            return f"EXPLORATORY: {self.exploratory}"
        return "ROBUSTNESS TEST ONLY: not a claim about learning accuracy" if self.robustness_only else ""

    def column_label(self, column: str) -> str:
        """A column's name as every table and report writes it: an assumed unit is never left implicit."""
        return f"{column} (unit assumed)" if column in self.unit_assumed else column


# ---------------------------------------------------------------- building
def _dicts(value) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _closure(links: dict[str, tuple[str, ...]], start: str) -> set[str]:
    """Everything reachable from `start` by following the links (a column calculated from columns that are themselves calculated)."""
    seen: set[str] = set()
    todo = [start]
    while todo:
        for nxt in links.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def _copy_of(frame: pd.DataFrame, column: str, result: str) -> tuple[float, int] | None:
    """(correlation, rows) when a numeric column tracks the result almost exactly, by either kind of correlation."""
    pair = frame[[column, result]].dropna()
    if len(pair) < 10 or pair[column].nunique() < 2 or pair[result].nunique() < 2:
        return None
    best = max(abs(pair[column].corr(pair[result])), abs(pair[column].corr(pair[result], method="spearman")))
    return (float(best), len(pair)) if best >= COPY_CORRELATION else None


def build_table(setup: dict, clean: CleanResult, label: DataLabel | None, name: str) -> ModellingTable:
    """Turn a cleaned table into a modelling table. Every decision is a finding; nothing is changed silently."""
    table = ModellingTable(name, label, None)
    out = table.findings
    data = setup.get("data") if isinstance(setup, dict) and isinstance(setup.get("data"), dict) else {}
    validation = data.get("validation")
    if not isinstance(validation, dict):
        out.append(make("M01", "", name))
        return table
    if clean is None or clean.frame is None or not clean.ok:
        out.append(make("M02", "", name))
        return table
    frame = clean.frame.reset_index(drop=True)
    table.frame = frame
    columns = set(frame.columns)
    if isinstance(validation.get("exploratory"), str) and validation["exploratory"].strip():
        table.exploratory = validation["exploratory"].strip()
        out.append(make("M26", "", name, "", why=table.exploratory))
    table.robustness_only = "api" in (validation.get("groups") or {}) and not ({"batch", "supplier", "date"} & set(validation.get("groups") or {}))

    # ---- groups (which columns say what a batch, a supplier, a date is)
    groups = validation.get("groups") if isinstance(validation.get("groups"), dict) else {}
    for kind, spec in groups.items():
        raw = spec.get("column") if isinstance(spec, dict) else None
        names = tuple(raw) if isinstance(raw, list) else ((raw,) if isinstance(raw, str) else ())
        missing = [n for n in names if n not in columns]
        for n in missing:
            out.append(make("M03", "group", name, kind, name=n))
        if names and not missing:
            confirmed = spec.get("confirmed") if isinstance(spec.get("confirmed"), bool) else None
            table.groups[kind] = GroupSpec(kind, names, confirmed, str(spec.get("note") or ""))
    supplier = table.groups.get("supplier")
    if supplier is not None and supplier.is_proxy:
        out.append(make("M24", "", name, "supplier", column=", ".join(supplier.columns), note=supplier.note))

    # ---- what to predict, and what to predict it from
    results = [r for r in validation.get("responses", []) if isinstance(r, str)] if isinstance(validation.get("responses"), list) else []
    present_results = []
    for r in results:
        if r in columns:
            present_results.append(r)
        else:
            out.append(make("M03", "result", name, r, name=r))
    roles, section_of = {}, {}
    for section in ("ingredients", "process_factors", "context_factors"):
        for item in _dicts(setup.get(section)):
            if isinstance(item.get("id"), str):
                roles[item["id"]] = item.get("role", section)
                section_of[item["id"]] = section
    explicit = validation.get("inputs")
    if isinstance(explicit, list) and explicit:
        wanted = [x for x in explicit if isinstance(x, str)]
    else:
        wanted = list(roles)
    if not wanted:
        out.append(make("M04", "", name))
    balance = [i for i in wanted if roles.get(i) == "balance"]
    for i in balance:
        out.append(make("M20", "", name, i, name=i))
    if isinstance(data.get("composition"), dict):
        out.append(make("M21", "", name))
    candidates = []
    for i in wanted:
        if i in balance:
            continue
        if i not in columns:
            out.append(make("M03", "input", name, i, name=i))
        elif frame[i].dropna().nunique() < 2:
            out.append(make("M15", "", name, i, name=i))
        else:
            candidates.append(i)
    if has_errors(out):
        return table

    # ---- columns left out on purpose
    for item in _dicts(validation.get("left_out")):
        if isinstance(item.get("id"), str):
            table.left_out.append((item["id"], str(item.get("why") or "")))
            out.append(make("M25", "", name, item["id"], name=item["id"], why=str(item.get("why") or "not stated")))

    # ---- calculated columns: neither side may be used to predict the other
    derived = validation.get("derived_from") if isinstance(validation.get("derived_from"), dict) else {}
    table.derived_from = {k: tuple(v) for k, v in derived.items() if isinstance(v, list)}

    # ---- one table of rows and inputs for each result
    for r in present_results:
        sources = _closure(table.derived_from, r)
        downstream = {k for k in table.derived_from if r in _closure(table.derived_from, k)}
        used, left = [], []
        for c in candidates:
            why = "same" if c == r else "source" if c in sources else "derived" if c in downstream else ""
            copy = None
            if not why and pd.api.types.is_numeric_dtype(frame[c]) and pd.api.types.is_numeric_dtype(frame[r]):
                copy = _copy_of(frame, c, r)
                why = "copy" if copy else ""
            if why:
                left.append((c, why))
                values = {"name": c}
                if copy:
                    values.update(correlation=f"{copy[0]:.4f}", n=copy[1])
                out.append(make("M10", why, name, r, **values))
            else:
                used.append(c)
        has_result = frame[r].notna() & pd.api.types.is_numeric_dtype(frame[r])
        n_no_result = int((~has_result).sum())
        if n_no_result:
            out.append(make("M11", "", name, r, n=n_no_result, total=len(frame), share=f"{100 * n_no_result / len(frame):.1f}%"))
        with_result = frame[has_result]
        gaps = with_result[used].isna().sum() if used else pd.Series(dtype=int)
        complete = has_result & (frame[used].notna().all(axis=1) if used else True)
        n_no_input = int(has_result.sum() - complete.sum())
        if n_no_input:
            worst = ", ".join(f"{c} ({int(n)})" for c, n in gaps[gaps > 0].sort_values(ascending=False).head(3).items())
            out.append(make("M12", "", name, r, n=n_no_input, share=f"{100 * n_no_input / max(int(has_result.sum()), 1):.1f}%", inputs=worst))
        rows = np.flatnonzero(complete.to_numpy())
        usable = True
        if len(rows) < MIN_ROWS:
            out.append(make("M13", "", name, r, n=len(rows), minimum=MIN_ROWS))
            usable = False
        elif frame[r].iloc[rows].nunique() < 2:
            out.append(make("M14", "", name, r))
            usable = False
        # a context factor is a category (a product code of 101, 102 ... is a label, not a quantity), whatever its values look like
        numeric = [c for c in used if pd.api.types.is_numeric_dtype(frame[c]) and section_of.get(c) != "context_factors"]
        table.responses[r] = ResponseTable(r, rows, numeric, [c for c in used if c not in numeric], left, n_no_result, n_no_input, usable)

    # ---- flags that travel with the table
    composition = data.get("composition") if isinstance(data.get("composition"), dict) else {}
    if "mass_balance_flag" in columns and frame["mass_balance_flag"].any():
        table.flag_columns.append("mass_balance_flag")
        tolerance = composition.get("tolerance_pct", 2)
        out.append(make("M22", "", name, "", n=int(frame["mass_balance_flag"].sum()), tolerance=f"{tolerance:g}" if isinstance(tolerance, (int, float)) else tolerance,
                        flag="mass_balance_flag"))
    used_anywhere = set(present_results) | {c for t in table.responses.values() for c in t.numeric + t.categorical}
    for report in clean.columns:
        if report.unit_status == "assumed" and report.id in used_anywhere:
            table.unit_assumed[report.id] = report.unit_note or "no reason given"
            out.append(make("M23", "", name, report.id, name=report.id, why=report.unit_note or "no reason given"))
    return table


def build_table_for_setup(setup: dict, base_dir, root, name: str) -> ModellingTable:
    """Read, clean and build in one call: the whole path from a setup to a modelling table."""
    clean = read_and_clean(setup, base_dir, root)
    data = setup.get("data") if isinstance(setup, dict) and isinstance(setup.get("data"), dict) else {}
    if clean.raw is not None:
        files = [clean.raw.info.name] + [i.name for i in clean.raw.joined_infos]
    else:
        files = [Path(str(data.get("experiments_file") or "the experiments file")).name]
    return build_table(setup, clean, data_label(setup, base_dir, root, files), name)
