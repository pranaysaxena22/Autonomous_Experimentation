"""The data quality report: one plain-text (Markdown) document that says what was read, what was changed, and what was assumed.

How it is laid out, and why:
  1. the title carries the data's status label, and the very next thing is the row-accounting block (rows dropped and failed runs in capitals),
     so nothing that removed a row can hide further down;
  2. the data status of every file (synthetic, illustrative, real, validated) and the rule that a result takes its weakest input;
  3. everything that needs attention (errors, then warnings);
  4. every assumption and every rule applied, with its count, written out in full (assumed units and conversions, the mg-to-percent weight check,
     two-digit years, an assumed date format, month-only dates ...), not only logged;
  5. the files, the columns (each column's unit and whether that unit is confirmed or assumed), failed runs, replicates, the weight check, dates;
  6. every message, and the fixed rules the reader always applies.
The same input always gives the same report (it contains no clock time). It may quote a few example values from the file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cellpoc.setup.files import path_is_safe, resolve_reference
from cellpoc.setup.versions import PROGRAM_VERSION

from .clean import CleanResult, Spec, read_and_clean
from .dates import TWO_DIGIT_YEAR_RULE
from .fixed_rules import FIXED_RULES
from .rows import POLICY_WORDS

STATUS_ORDER = ("synthetic", "illustrative", "real", "validated")
NO_TABLE_LINE = "ROW ACCOUNTING: no table was produced (the file could not be used: see 'What needs your attention')"


# ---------------------------------------------------------------- the data's status label
@dataclass(frozen=True)
class FileLabel:
    file: str
    status: str                 # synthetic, illustrative, real, validated, or "unstated"
    label: str
    source: str
    origin: str                 # where this label comes from
    client_data: bool | None    # True / False when the label says, None when unknown


@dataclass(frozen=True)
class DataLabel:
    files: tuple[FileLabel, ...]

    @property
    def status(self) -> str:
        """The weakest status of the files read (an unstated status counts as illustrative): a result is only as strong as its weakest input."""
        known = [f.status if f.status in STATUS_ORDER else "illustrative" for f in self.files] or ["illustrative"]
        return min(known, key=STATUS_ORDER.index)

    @property
    def short(self) -> str:
        status, files = self.status, self.files
        unstated = any(f.status not in STATUS_ORDER for f in files)
        if status == "synthetic":
            return "SYNTHETIC DATA"
        if status == "illustrative":
            return "ILLUSTRATIVE DATA (data status not stated)" if unstated else "ILLUSTRATIVE DATA"
        word = "VALIDATED" if status == "validated" else "REAL"
        if all(f.client_data is False for f in files):
            public = any("PUBLIC" in f.label.upper() for f in files)
            return f"{word} PUBLIC DATA, NOT CLIENT DATA" if public else f"{word} DATA, NOT CLIENT DATA"
        return f"{word} DATA"


def _meta(setup_data: dict, base_dir, root) -> tuple[dict, str]:
    reference = setup_data.get("meta_file")
    if isinstance(reference, str) and reference.strip() and path_is_safe(reference):
        where = resolve_reference(reference, base_dir, root)
        if where is not None:
            try:
                loaded = json.loads(where.read_bytes().decode("utf-8-sig"))
                if isinstance(loaded, dict) and loaded.get("data_status") in STATUS_ORDER:
                    return loaded, where.name
            except (OSError, ValueError):
                pass
    return {}, ""


def data_label(setup: dict, base_dir, root, file_names: list[str]) -> DataLabel:
    """The status label for every file read: the table's companion file first, then the setup's `provenance`, otherwise 'not stated'."""
    data = setup.get("data") if isinstance(setup, dict) and isinstance(setup.get("data"), dict) else {}
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) and data["provenance"].get("data_status") in STATUS_ORDER else {}
    meta, meta_name = _meta(data, base_dir, root)

    def label_of(file: str, info: dict, origin: str) -> FileLabel:
        client = info.get("contains_real_client_data")
        return FileLabel(file, info["data_status"], str(info.get("label") or ""), str(info.get("source") or ""), origin, client if isinstance(client, bool) else None)

    labels = []
    for position, name in enumerate(file_names):
        if position == 0 and meta:
            labels.append(label_of(name, meta, f"the companion file {meta_name}"))
        elif provenance:
            labels.append(label_of(name, provenance, "the setup's provenance setting"))
        elif meta:
            labels.append(label_of(name, meta, f"the companion file {meta_name} (the main file's)"))
        else:
            labels.append(FileLabel(name, "unstated", "", "", "nothing in the setup says what this data is", None))
    return DataLabel(tuple(labels))


# ---------------------------------------------------------------- small helpers
def _n(value) -> str:
    return f"{value:,}" if isinstance(value, int) else f"{value:g}"


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines + [""]


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


# ---------------------------------------------------------------- the assumptions, written out
def _assumptions(result: CleanResult, spec: Spec) -> tuple[list[str], list[str]]:
    assumed: list[str] = []
    rules: list[str] = []
    hardness = spec.data.get("hardness") if isinstance(spec.data.get("hardness"), dict) else {}
    hardness_to = _text(hardness.get("to"))
    for r in result.columns:
        if r.unit_status == "assumed" and r.role != "derived" and r.id != hardness_to:
            assumed.append(f"**ASSUMED UNIT: `{r.id}`** (file column '{r.raw_name}') is taken to be in **{r.unit or 'the stated unit'}**: {r.unit_note or 'no reason given'}. "
                           f"{_n(r.n_values - r.n_missing)} value(s) are affected.")
    inherited = [r for r in result.columns if r.role == "derived" and r.unit_status == "assumed"]
    if inherited:
        assumed.append("**ASSUMPTION INHERITED:** " + ", ".join(f"`{r.id}`" for r in inherited) + " "
                       + ("is a percentage made" if len(inherited) == 1 else "are percentages made") + " from a column whose unit is assumed, so it is assumed as well.")
    for r in result.columns:
        for c in r.conversions:
            line = f"{_n(c['n'])} value(s) of `{r.id}` (file column '{r.raw_name}') were converted from {c['unit']} to kP by dividing by {c['divide']}"
            if c["status"] == "assumed":
                assumed.append(f"**ASSUMED CONVERSION:** {line}. This conversion is an assumption, not an exact one: {c['note'] or 'no reason given'}.")
            elif c["unit"].casefold() != "kp":
                rules.append(f"Unit conversion (exact): {line}.")
    comp = result.composition
    if comp:
        total = comp["rows"]
        share = f"{100 * comp['flagged'] / total:.1f}%" if total else "0%"
        assumed.append(f"**ASSUMED WEIGHT CHECK (mg to percent):** {len(comp['amounts'])} amount column(s) in mg were converted to a percentage by dividing by `{comp['weight']}`, "
                       f"which is taken to be the tablet's true total weight. Whatever the listed amounts do not add up to is shown as a shortfall; it is **not** rescaled to 100%. "
                       f"Stated tolerance: {comp['tolerance_pct']:g}% of the weight. {_n(comp['flagged'])} of {_n(total)} rows ({share}) differ from the weight by more than that "
                       f"(largest shortfall {abs(min(comp['shortfall_pct'], 0)):.2f}%, largest overshoot {max(comp['overshoot_pct'], 0):.2f}%). "
                       "The exact gap of every row is kept in `mass_balance_gap_pct`.")
    date = next((r for r in result.columns if r.id == "date"), None)
    if date is not None:
        f = date.facts
        if f.get("assumed_format"):
            assumed.append(f"**ASSUMED DATE FORMAT:** the setup gives no date format, so dates in '{date.raw_name}' were read as year-month-day (yyyy-mm-dd).")
        else:
            rules.append(f"Dates in '{date.raw_name}' are read as `{f.get('format')}` (month names in language '{f.get('language')}'); day and month are never guessed.")
        if f.get("two_digit"):
            assumed.append(f"**TWO-DIGIT YEARS INTERPRETED:** {_n(f['two_digit'])} date(s) in '{date.raw_name}' were written with a 2-digit year and were read by this rule: "
                           f"{TWO_DIGIT_YEAR_RULE} (for example '{f['two_digit_example']}' became {f['two_digit_result']}).")
        if f.get("precision") == "month":
            assumed.append(f"**MONTH-ONLY DATES:** the dates in '{date.raw_name}' give only a month and a year, so each was set to the first day of its month "
                           f"({f.get('first')} to {f.get('last')}). The order of events inside a month is not known.")
        if f.get("unreadable"):
            rules.append(f"{_n(f['unreadable'])} date(s) in '{date.raw_name}' could not be read and were left empty.")
    for marker, count in sorted(result.marker_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        rules.append(f"Text meaning 'no value': '{marker}' was found {_n(count)} time(s) and treated as missing (the setup lists it).")
    below = spec.data.get("below_detection") if isinstance(spec.data.get("below_detection"), dict) else {}
    for r in result.columns:
        if r.n_below:
            rules.append(f"{_n(r.n_below)} value(s) of `{r.id}` were written below a detection limit and handled with the rule '{_text(below.get('rule')) or 'none'}'; "
                         f"they are flagged in `{r.id}__below_detection`.")
        if r.n_above:
            rules.append(f"{_n(r.n_above)} value(s) of `{r.id}` were written as above a limit and were treated as missing.")
        if r.n_not_numbers and r.role not in ("date",):
            rules.append(f"{_n(r.n_not_numbers)} value(s) of `{r.id}` were not numbers and were treated as missing.")
    a = result.account
    if a.failed_set_aside:
        rules.append(f"Failed runs: {_n(a.failed_set_aside)} row(s) were set aside ({POLICY_WORDS.get(a.failed_policy, a.failed_policy)}).")
    if a.dropped_missing:
        rules.append(f"Missing values: {_n(a.dropped_missing)} row(s) were dropped because a value the setup requires was missing (the setup's drop_row rule).")
    replicates = spec.data.get("replicates") if isinstance(spec.data.get("replicates"), dict) else {}
    if a.replicates_merged:
        rules.append(f"Replicates: {_n(a.replicates_merged)} row(s) were combined into their group's row (rule: {_text(replicates.get('rule'))}; grouped by "
                     f"{', '.join(str(g) for g in replicates.get('group_by', []))}); the individual rows are "
                     f"{'kept for noise estimates' if result.replicate_rows is not None else 'not kept'}.")
    if result.raw is not None:
        info = result.raw.info
        rules.append(f"Numbers in the main file use the decimal mark: {info.decimal}; the setup says '{spec.decimal}'.")
    for r in result.columns:
        if r.id == "experiment_id" and "generated" in " ".join(r.notes):
            rules.append("The file has no experiment ID column, so each row was named after its row number (for example 'row2').")
    return assumed, rules


# ---------------------------------------------------------------- the report
def build_report(result: CleanResult, setup: dict, label: DataLabel, names: list[str] | None = None) -> str:
    spec = Spec.from_setup(setup)
    names = names or [f.file for f in label.files]
    findings = result.findings
    lines: list[str] = [f"# Data quality report [{label.short}]: {', '.join(names)}", ""]
    lines += ["```", result.account.headline() if result.frame is not None else NO_TABLE_LINE, "```", ""]

    lines += ["## Data status", "", f"**This report is {label.short}.** A result is only as strong as its weakest input (the platform's rule), and the weakest input here is "
              f"**{label.status}**."]
    if label.status == "synthetic":
        lines.append("It says nothing about real tablets: the data was made by a program.")
    elif label.status in ("real", "validated") and any(f.client_data is not False for f in label.files):
        lines.append("It may be real client data: the client's data-handling policy must be approved before real data is used, and it must stay out of git and out of any upload.")
    elif label.status in ("real", "validated"):
        lines.append("The data is real but is not client data: it is used only to test ingestion and models and is never presented as a client's result.")
    else:
        lines.append("Everything is illustrative until real client data and expert review exist.")
    lines += [""]
    lines += _table(["File", "Data status", "What it is", "Where this label comes from"],
                    [[f.file, f.status, f.label or "(no label given)", f.origin + (f"; source: {f.source}" if f.source else "")] for f in label.files])

    lines += ["## What needs your attention", ""]
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    if not errors and not warnings:
        lines += ["Nothing needs attention: no errors and no warnings.", ""]
    for f in errors:
        lines.append(f"- **ERROR** `{f.rule}`: {f.message}")
    for f in warnings:
        lines.append(f"- **WARNING** `{f.rule}`: {f.message}")
    lines.append("")

    if result.frame is not None:
        assumed, rules = _assumptions(result, spec)
        lines += ["## Assumptions and rules applied", "",
                  "Everything the reader assumed is written out here with its count. **ASSUMED** means it is a convention or a guess, not a fact from the data. "
                  "**Rules** are things the setup told the reader to do.", "", "### Assumptions", ""]
        lines += [f"- {a}" for a in assumed] or ["- None: nothing was assumed."]
        lines += ["", "### Rules applied (as the setup says)", ""]
        lines += [f"- {r}" for r in rules] or ["- None."]
        lines.append("")

    lines += ["## Files read", ""]
    rows = []
    if result.raw is not None:
        infos = [("main file", result.raw.info)] + [("joined", i) for i in result.raw.joined_infos]
        for role, i in infos:
            endings = ", ".join(f"{v:,} {k.upper()}" for k, v in i.line_endings.items() if v) or "n/a"
            rows.append([i.name, role, f"{i.size_bytes:,} bytes", i.encoding or "Excel", i.delimiter or "n/a", i.decimal, endings, _n(i.rows_in_file), _n(i.columns),
                         _n(i.rows_blank), _n(i.names_tidied), _n(i.cells_trimmed)])
        lines += _table(["File", "Role", "Size", "Text encoding", "Column separator", "Decimal mark", "Line endings", "Rows read", "Columns", "Blank rows skipped",
                         "Names tidied", "Cells trimmed"], rows)
    else:
        lines += ["No file could be read.", ""]

    if result.frame is not None:
        lines += ["## Columns", "", "One row for every column of the table. **ASSUMED** in the unit column means the unit is not confirmed (the reason is under the table).", ""]
        rows = []
        for r in result.columns:
            status = "**ASSUMED**" if r.unit_status == "assumed" else r.unit_status
            span = "" if r.minimum is None else f"{r.minimum:g} to {r.maximum:g}"
            rows.append([f"`{r.id}`", r.raw_name or "(made by the reader)", f"{r.role}, {r.kind}", r.unit or "-", status, _n(r.n_values - r.n_missing), _n(r.n_missing),
                         _n(r.n_not_numbers), _n(r.n_below), _n(r.n_converted), span])
        lines += _table(["Column", "From the file's column", "Role, kind", "Unit", "Unit status", "Values", "Missing", "Not numbers", "Below limit", "Converted", "Lowest to highest"], rows)
        notes = [f"- `{r.id}`: " + ("**ASSUMED UNIT.** " + r.unit_note + " " if r.unit_status == "assumed" else "") + " ".join(r.notes) for r in result.columns if r.unit_status == "assumed" or r.notes]
        if notes:
            lines += ["Notes on columns:", ""] + notes + [""]

    if result.failure_stats:
        s = result.failure_stats
        lines += ["## Failed runs", "", f"{_n(s['count'])} of {_n(s['total'])} rows ({100 * s['rate']:.1f}%) are failed runs. They are kept in a separate table for failure statistics and are not in the model table.", ""]
        lines += _table(["Reason", "Failed runs"], [[k, _n(v)] for k, v in s["by_reason"]])
        if s["by_batch"]:
            lines += ["Batches with the most failures:", ""] + _table(["Batch", "Failed runs"], [[k, _n(v)] for k, v in s["by_batch"]])
        if s["by_month"]:
            lines += ["By month:", ""] + _table(["Month", "Failed runs"], [[k, _n(v)] for k, v in s["by_month"]])

    if result.replicate_noise or result.account.replicates_merged:
        lines += ["## Replicates", "", f"{_n(result.account.replicates_merged)} replicate row(s) were combined into one row per recipe. The scatter between replicates of the same recipe "
                  "(pooled standard deviation) is kept for noise estimates:", ""]
        lines += _table(["Response", "Pooled standard deviation", "Degrees of freedom", "Recipes with replicates"],
                        [[k, f"{v['pooled_sd']:.6g}", _n(v["degrees_of_freedom"]), _n(v["groups"])] for k, v in result.replicate_noise.items()]) if result.replicate_noise else [""]

    if result.composition and result.frame is not None and "mass_balance_gap_pct" in result.frame.columns:
        comp = result.composition
        gaps = [g for g in result.frame["mass_balance_gap_pct"].tolist() if g == g]
        buckets = [("exactly balanced (gap under 0.001%)", sum(1 for g in gaps if abs(g) < 0.001)),
                   (f"within the tolerance ({comp['tolerance_pct']:g}%) but not exact", sum(1 for g in gaps if 0.001 <= abs(g) <= comp["tolerance_pct"] + 1e-9)),
                   (f"short by more than the tolerance", sum(1 for g in gaps if g < -comp["tolerance_pct"] - 1e-9)),
                   (f"over by more than the tolerance", sum(1 for g in gaps if g > comp["tolerance_pct"] + 1e-9))]
        lines += ["## Weight check", "", f"Amounts (mg) against the total weight `{comp['weight']}`, tolerance {comp['tolerance_pct']:g}% of the weight. Gap = (sum of amounts - total weight) / total weight; "
                  "negative means the listed amounts fall short.", ""]
        lines += _table(["Rows", "Count"], [[k, _n(v)] for k, v in buckets])
        worst = sorted(comp["flagged_rows"], key=lambda item: -abs(item[1]))[:10]
        if worst:
            lines += [f"The {len(worst)} largest gaps among the {_n(comp['flagged'])} flagged rows (row in the file, exact gap):", ""]
            lines += _table(["Row in the file", "Gap"], [[_n(row), f"{gap:+.2f}%"] for row, gap in worst])

    date = next((r for r in result.columns if r.id == "date"), None) if result.frame is not None else None
    if date is not None and date.facts.get("first"):
        f = date.facts
        lines += ["## Dates", "", f"- Column: '{date.raw_name}'; format: `{f['format']}`" + ("" if not f.get("assumed_format") else " (**assumed**)") + f"; month names: {f.get('language')}.",
                  f"- Range: {f['first']} to {f['last']}; precision: {f.get('precision')}.",
                  f"- Read successfully: {_n(date.n_values)}; left empty or unreadable: {_n(date.n_missing)}."]
        if f.get("two_digit"):
            lines.append(f"- **{_n(f['two_digit'])} date(s) had a 2-digit year and were read by the rule: {TWO_DIGIT_YEAR_RULE}.** For example '{f['two_digit_example']}' became {f['two_digit_result']}.")
        lines.append("")

    lines += ["## Every message", "", f"All {len(findings)} messages the reader produced, errors first. The wording of each is listed in `docs/ingest_messages.md`.", ""]
    lines += _table(["Level", "ID", "Message"], [[f.level.upper(), f.rule + (f"/{f.variant}" if f.variant else ""), f.message] for f in findings])
    lines += ["## Fixed rules the reader applies", ""] + [f"- {rule}" for rule in FIXED_RULES] + [""]
    lines += ["---", f"Generated by the data reader (program version {PROGRAM_VERSION}). The same input always gives the same report. "
              "This report may quote a few example values from the file."]
    return "\n".join(lines).rstrip() + "\n"


def report_for_setup(setup: dict, base_dir, root) -> tuple[CleanResult, str]:
    """Read, clean and report in one call: the whole path from a setup to a report."""
    result = read_and_clean(setup, base_dir, root)
    data = setup.get("data") if isinstance(setup, dict) and isinstance(setup.get("data"), dict) else {}
    if result.raw is not None:
        names = [result.raw.info.name] + [i.name for i in result.raw.joined_infos]
    else:
        names = [Path(str(data.get("experiments_file") or "the experiments file")).name] + [Path(str(j.get("file", ""))).name for j in (data.get("joins") or []) if isinstance(j, dict)]
    return result, build_report(result, setup, data_label(setup, base_dir, root, names), names)


def write_report(text: str, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))              # Unix line endings, no byte-order mark
    return path
