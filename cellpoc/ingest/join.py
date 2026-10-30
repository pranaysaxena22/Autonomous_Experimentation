"""Adding the columns of other files to the main table by matching key columns (for example a laboratory file and a process file of the same batches).

The main table never loses a row: every main row is kept, and a row with no match in a joined file simply has empty cells for the columns taken
from it (and is counted and reported). A joined file must have one row per key, otherwise it is refused: it would be unclear which row to use.
Keys are compared ignoring capital letters and spaces around the value.
"""
from __future__ import annotations

from collections import Counter

from cellpoc.setup.tablefile import match_key

from .findings import Finding, make
from .reader import RawTable, ReadResult


def _norm(value) -> str:
    return str(value).strip().casefold()


def merge_joins(main: ReadResult, joins: list[tuple[dict, ReadResult, str]]) -> ReadResult:
    """Add each joined file's columns to the main table. `joins` holds (the setup's join, the joined file's reading, the file's name)."""
    if main.table is None:
        return main
    table = main.table
    frame = table.frame.copy()
    original = list(table.original_names)
    findings: list[Finding] = list(main.findings)
    joined_infos = []
    main_name = table.info.name
    for join, joined, label in joins:
        findings += [f for f in joined.findings if f.level != "note"]
        if joined.table is None:
            return ReadResult(None, findings)
        joined_frame = joined.table.frame
        joined_infos.append(joined.table.info)
        pairs =[(str(p.get("main", "")), str(p.get("joined", ""))) for p in join.get("on", []) if isinstance(p, dict)]
        main_keys = {match_key(c): c for c in frame.columns}
        joined_keys = {match_key(c): c for c in joined_frame.columns}
        broken = False
        for left, right in pairs:
            if match_key(left) not in main_keys:
                findings.append(make("I82", "", main_name, "", column=left, file=main_name))
                broken = True
            if match_key(right) not in joined_keys:
                findings.append(make("I82", "", label, "", column=right, file=label))
                broken = True
        if broken or not pairs:
            return ReadResult(None, findings)
        left_columns = [main_keys[match_key(a)] for a, _ in pairs]
        right_columns = [joined_keys[match_key(b)] for _, b in pairs]
        index: dict[tuple, int] = {}
        duplicates: Counter = Counter()
        for position in range(len(joined_frame)):
            key = tuple(_norm(joined_frame[c].iloc[position]) for c in right_columns)
            if not all(key):
                continue
            if key in index:
                duplicates[key] += 1
            index.setdefault(key, position)
        if duplicates:
            example = ", ".join(next(iter(duplicates)))
            findings.append(make("I78", "", label, "", file=label, example=example, n=f"{len(duplicates):,}"))
            return ReadResult(None, findings)
        prefix = join.get("prefix") if isinstance(join.get("prefix"), str) else ""
        key_names = {match_key(c) for c in right_columns}
        added = [c for c in joined_frame.columns if match_key(c) not in key_names]
        existing = {match_key(c) for c in frame.columns}
        for column in added:
            if match_key(prefix + column) in existing:
                findings.append(make("I83", "", label, "", file=label, column=prefix + column))
                return ReadResult(None, findings)
        used: set[int] = set()
        found_rows: list[int | None] = []
        unmatched_example = ""
        for position in range(len(frame)):
            key = tuple(_norm(frame[c].iloc[position]) for c in left_columns)
            row = index.get(key) if all(key) else None
            if row is None:
                found_rows.append(None)
                unmatched_example = unmatched_example or ", ".join(key) or "(empty key)"
            else:
                found_rows.append(row)
                used.add(row)
        for column in added:
            values = joined_frame[column].tolist()
            frame[prefix + column] = [values[r] if r is not None else "" for r in found_rows]
            original.append(prefix + joined.table.original_names[list(joined_frame.columns).index(column)])
        matched = sum(1 for r in found_rows if r is not None)
        findings.append(make("I81", "", label, "", n=len(added), file=label, matched=f"{matched:,}", total=f"{len(frame):,}"))
        if matched < len(frame):
            findings.append(make("I79", "", label, "", n=f"{len(frame) - matched:,}", total=f"{len(frame):,}", file=label, example=repr(unmatched_example)))
        if len(used) < len(joined_frame):
            findings.append(make("I80", "", label, "", n=f"{len(joined_frame) - len(used):,}", file=label))
    table.info.columns = len(frame.columns)
    return ReadResult(RawTable(frame, original, table.source_rows, table.info, table.date_cells, joined_infos), findings)
