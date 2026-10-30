"""What happens to whole rows: failed runs are set aside, replicates are combined, and every row is accounted for.

Rows are only ever removed on purpose (the setup says so) and every removal is counted and shown. RowAccount is the one place that adds
them up: rows read = rows dropped for missing values + failed runs set aside + replicate rows combined + rows left in the table.
Its headline text is what the quality report must show first, so a dropped row can never hide in a detailed log.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from cellpoc.setup.tablefile import match_key

from .findings import Finding, make

FAILED_POLICIES = ("exclude_from_models_keep_in_failure_statistics", "exclude", "keep")
POLICY_WORDS = {"exclude_from_models_keep_in_failure_statistics": "kept in a separate table for failure statistics, out of the model table",
                "exclude": "excluded (not kept anywhere)"}


@dataclass
class RowAccount:
    rows_read: int = 0
    blank_skipped: int = 0
    dropped_missing: int = 0
    failed_set_aside: int = 0
    failed_policy: str = ""
    replicates_merged: int = 0
    rows_out: int = 0

    @property
    def balanced(self) -> bool:
        return self.rows_read == self.dropped_missing + self.failed_set_aside + self.replicates_merged + self.rows_out

    @property
    def changed(self) -> bool:
        return bool(self.dropped_missing or self.failed_set_aside or self.replicates_merged)

    def headline(self) -> str:
        """The plain-text block the quality report opens with. Anything removed is shown in capitals with its count, never left to a log."""
        lines = [f"ROW ACCOUNTING: {self.rows_read:,} rows read -> {self.rows_out:,} rows in the table"]
        if self.dropped_missing:
            lines.append(f"  ** {self.dropped_missing:,} ROWS DROPPED because a value the setup requires was missing (the setup's drop_row rule)")
        if self.failed_set_aside:
            lines.append(f"  ** {self.failed_set_aside:,} FAILED RUNS set aside ({POLICY_WORDS.get(self.failed_policy, self.failed_policy)})")
        if self.replicates_merged:
            lines.append(f"  {self.replicates_merged:,} replicate rows combined into their group's row")
        if self.blank_skipped:
            lines.append(f"  {self.blank_skipped:,} blank rows in the file were skipped")
        if not self.changed:
            lines.append("  Every row read is in the table.")
        lines.append("  The counts add up." if self.balanced else "  WARNING: the counts do not add up.")
        return "\n".join(lines)


# ---------------------------------------------------------------- failed runs
def failure_flags(texts: list[str], failed_value: str) -> list[bool]:
    """True for each cell equal to the failed value (compared ignoring capital letters and spaces around)."""
    target = failed_value.strip().casefold()
    return [bool(target) and t.strip().casefold() == target for t in texts]


def status_counts(texts: list[str]) -> str:
    counts = Counter(t.strip() if t.strip() else "(empty)" for t in texts)
    shown = ", ".join(f"{k} {v:,}" for k, v in counts.most_common(6))
    return shown + (", ..." if len(counts) > 6 else "")


def failure_statistics(failed: pd.DataFrame, total: int) -> dict:
    """Counts of failed runs by reason, by batch and by month, kept so failures can be studied even though the rows leave the model table."""
    def counted(column: str, limit: int | None = None):
        if column not in failed.columns:
            return []
        values = failed[column].map(lambda v: "(not given)" if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT else v)
        pairs = Counter(values).most_common(limit)
        return [(str(k), int(v)) for k, v in pairs]

    months = []
    if "date" in failed.columns:
        stamps = failed["date"].dropna()
        months = sorted(Counter(stamps.dt.strftime("%Y-%m")).items())
    return {"count": len(failed), "total": total, "rate": len(failed) / total if total else 0.0,
            "by_reason": counted("failure_reason"), "by_batch": counted("batch_id", 10), "by_month": [(k, int(v)) for k, v in months]}


def apply_failed_runs(frame: pd.DataFrame, policy: str, status_column: str, failed_value: str, findings: list[Finding], name: str):
    """(the model table, the failed rows to keep or None, their statistics or None, how many rows left the model table)."""
    flagged = frame["is_failed"]
    n, total = int(flagged.sum()), len(frame)
    if not n:
        return frame.drop(columns=["is_failed"]) if policy != "keep" else frame, None, None, 0
    share = f"{100 * n / total:.1f}%"
    if policy == "keep":
        findings.append(make("I75", "kept", name, status_column, n=f"{n:,}", total=f"{total:,}", share=share, column=status_column, value=failed_value))
        return frame, None, None, 0
    failed = frame[flagged].reset_index(drop=True)
    kept = frame[~flagged].drop(columns=["is_failed"]).reset_index(drop=True)
    keep_rows = policy == "exclude_from_models_keep_in_failure_statistics"
    findings.append(make("I75", "removed", name, status_column, n=f"{n:,}", total=f"{total:,}", share=share, column=status_column, value=failed_value,
                         where=POLICY_WORDS.get(policy, policy)))
    return kept, (failed if keep_rows else None), (failure_statistics(failed, total) if keep_rows else None), n


# ---------------------------------------------------------------- replicates
def resolve_group_columns(names: list[str], frame: pd.DataFrame, aliases: dict[str, str], findings: list[Finding], file: str) -> list[str] | None:
    """Turn the setup's replicate grouping (output names, or the file's own column names) into table columns; None after reporting an unknown one."""
    by_key = {match_key(c): c for c in frame.columns}
    resolved, ok = [], True
    for entry in names:
        column = by_key.get(match_key(entry)) or aliases.get(match_key(entry))
        if column is None or column not in frame.columns:
            have = ", ".join(list(frame.columns)[:8]) + (", ..." if len(frame.columns) > 8 else "")
            findings.append(make("I72", "", file, "", name=entry, have=have))
            ok = False
        else:
            resolved.append(column)
    return resolved if ok else None


def apply_replicates(frame: pd.DataFrame, group_by: list[str], rule: str, keep_rows: bool, response_ids: list[str], findings: list[Finding], name: str):
    """(the table, the individual replicate rows or None, the pooled replicate noise per response, how many rows were combined into others)."""
    keys, seen, group_of = [], {}, []
    for position in range(len(frame)):
        parts = []
        for column in group_by:
            value = frame[column].iloc[position]
            parts.append(f"\x00missing{position}" if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT else str(value))
        key = tuple(parts)
        group_of.append(seen.setdefault(key, len(seen)))
        keys.append(key)
    frame = frame.copy()
    frame["__group"] = group_of
    sizes = frame.groupby("__group").size()
    frame["replicate_count"] = frame["__group"].map(sizes).astype(int)
    repeated = sizes[sizes > 1]
    if repeated.empty:
        findings.append(make("I74", "none", name, "", keys=" and ".join(f"'{g}'" for g in group_by)))
        return frame.drop(columns=["__group"]), None, {}, 0
    noise = _pooled_noise(frame, response_ids)
    individual = frame[frame["replicate_count"] > 1].rename(columns={"__group": "replicate_group"}).reset_index(drop=True) if keep_rows else None
    if rule == "keep_all":
        findings.append(make("I74", "kept_all", name, "", groups=f"{len(repeated):,}", rows=f"{int(repeated.sum()):,}"))
        return frame.drop(columns=["__group"]), None, noise, 0
    aggregate: dict[str, str] = {}
    disagreements: dict[str, list] = {}
    for column in frame.columns:
        if column in ("__group",):
            continue
        series = frame[column]
        if column == "replicate_count":
            aggregate[column] = "first"
        elif column == "source_row":
            aggregate[column] = "first"
        elif pd.api.types.is_bool_dtype(series):
            aggregate[column] = "any"
        elif pd.api.types.is_float_dtype(series):
            aggregate[column] = "median" if rule == "median" else "mean"
        elif pd.api.types.is_datetime64_any_dtype(series):
            aggregate[column] = "min"
        else:
            aggregate[column] = "first"
            if column == "replicate_no":
                continue                                    # the one column that is meant to differ between replicates
            for group, rows in frame[frame["replicate_count"] > 1].groupby("__group"):
                distinct = pd.unique(rows[column].dropna())
                if len(distinct) > 1:
                    disagreements.setdefault(column, []).append(str(distinct[0]) + " / " + str(distinct[1]))
    merged_frame = frame.groupby("__group", sort=True).agg(aggregate).reset_index(drop=True)
    merged_frame = merged_frame[[c for c in frame.columns if c != "__group"]]
    if "replicate_no" in merged_frame.columns:
        merged_frame = merged_frame.drop(columns=["replicate_no"])
    for column, examples in list(disagreements.items())[:5]:
        findings.append(make("I73", "", name, column, n=f"{len(examples):,}", column=column, example=repr(examples[0])))
    merged = len(frame) - len(merged_frame)
    findings.append(make("I74", "", name, "", groups=f"{len(repeated):,}", rows=f"{int(repeated.sum()):,}", rule=rule,
                         kept="kept for noise estimates" if keep_rows else "not kept"))
    return merged_frame, individual, noise, merged


def _pooled_noise(frame: pd.DataFrame, response_ids: list[str]) -> dict:
    """The scatter between replicates of the same recipe: pooled standard deviation per response, with its degrees of freedom."""
    result = {}
    for column in response_ids:
        if column not in frame.columns or not pd.api.types.is_float_dtype(frame[column]):
            continue
        groups = frame.groupby("__group")[column]
        counts = groups.count()
        sums = groups.apply(lambda s: float(((s - s.mean()) ** 2).sum()) if s.count() > 1 else 0.0)
        freedom = int((counts - 1).clip(lower=0).sum())
        if freedom > 0:
            result[column] = {"pooled_sd": math.sqrt(float(sums.sum()) / freedom), "degrees_of_freedom": freedom, "groups": int((counts > 1).sum())}
    return result
