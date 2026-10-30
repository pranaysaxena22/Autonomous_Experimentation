"""Every message the data reader can show, in one place, so the wording can be reviewed without reading code.

A finding is an error (the file cannot be used), a warning (it was read, but an assumption or a repair was made that you should know
about) or a note (information). The full message reads "<file> > <column>: <text>". docs/ingest_messages.md is generated from this
catalogue and the tests, and the health check fails if any message has no test.
"""
from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("error", "warning", "note")


@dataclass(frozen=True)
class Rule:
    id: str
    variant: str
    level: str
    what: str            # what is checked, in words
    template: str        # the message text, with {placeholders}


CATALOGUE: dict[tuple[str, str], Rule] = {}


def _add(rule_id: str, variant: str, level: str, what: str, template: str) -> None:
    CATALOGUE[(rule_id, variant)] = Rule(rule_id, variant, level, what, template)


# ---------------------------------------------------------------- the file cannot be used (errors)
_add("I01", "", "error", "the file exists", "the file was not found. Check the name in the setup, or put the file in data/client/.")
_add("I02", "", "error", "the file is not too big", "the file is {mb} MB, more than the {limit} MB this program reads. Check it is the right file, or split it.")
_add("I03", "", "error", "a .csv file is really a text file",
     "this is an Excel file with a text-file name. Open it in Excel and use Save As, or give it the name ending .xlsx.")
_add("I04", "", "error", "an Excel file can be read safely",
     "this is {what}, which is not read (macros and old formats are refused). Open it in Excel and save a copy as .xlsx or as CSV.")
_add("I05", "", "error", "an Excel file can be opened",
     "the Excel file could not be opened: it may be damaged or password-protected. Open it in Excel and save a copy.")
_add("I06", "", "error", "an Excel file does not unpack to something enormous",
     "the Excel file unpacks to far more than a normal spreadsheet, so it was not opened. Check it is the right file.")
_add("I07", "", "error", "a text file is text", "this does not look like a text or CSV file (it contains binary data). Check it is the right file.")
_add("I08", "", "error", "the text encoding is one this program knows",
     "'{encoding}' is not a text encoding this program knows. Use utf-8, windows-1250, windows-1252, utf-16, or auto.")
_add("I09", "", "error", "the file is valid in its stated encoding",
     "the file is not valid {encoding} text. If it came from Excel in Central Europe try 'windows-1250'; or save it as a UTF-8 CSV; or set the encoding to 'auto'.")
_add("I10", "", "error", "the named sheet exists", "this workbook has no sheet called '{sheet}'. Its sheets are: {sheets}.")
_add("I11", "", "error", "the file has rows", "the file has no rows to read.")
_add("I12", "", "error", "the header row is inside the file", "the header row ({row}) is beyond the end of the file, which has {rows} row(s).")
_add("I13", "rows", "error", "the table is not too long", "the table has more than {limit} rows, more than this program reads.")
_add("I13", "columns", "error", "the table is not too wide", "the table has {n} columns, more than the {limit} this program reads.")
_add("I14", "", "error", "no two columns share a name",
     "two columns have the same name once spaces and capital letters are ignored: '{first}' and '{second}'. Rename one of them in the file.")
_add("I15", "", "error", "no row has more filled cells than the header has columns",
     "row {row} has {have} filled cells but the header has only {want} columns ({count} such row(s)). Look for a stray separator, or a value containing the separator that is not in quotes.")
_add("I17", "", "error", "the file can be split into columns", "the file could not be split into columns near line {line}. Check the quotes (\") around values.")

# ---------------------------------------------------------------- read, but something was assumed or repaired (warnings)
_add("I16", "", "warning", "no cell is absurdly long",
     "a cell near line {line} is very long ({n} characters): an opening quote may never have been closed, which would join many rows into one cell.")
_add("I21", "", "warning", "the text encoding was certain",
     "the file is not valid UTF-8, so it was read as Windows-1252 (Western European). If letters such as č, š or ž look wrong, set the encoding to 'windows-1250' in the setup.")
_add("I25", "", "warning", "line endings agree with the setup",
     "the setup says {declared} line endings but the file uses {found}. Both are read correctly; update the setup to remove this message.")
_add("I27", "", "warning", "every column that holds values has a name",
     "{n} column(s) have no name but hold values; they were called {names}. Give them names in the file.")
_add("I30", "", "warning", "every row has all its cells",
     "{n} row(s) have fewer cells than the header; the missing cells were treated as empty (the first is row {row}).")
_add("I33", "", "warning", "Excel formulas have a saved result",
     "{n} Excel cell(s) hold a formula with no saved result (the file was never recalculated), so they were read as empty. Open the file in Excel and save it.")
_add("I36", "", "warning", "the decimal mark agrees with the setup",
     "the setup says the decimal mark is a {declared}, but {n} cell(s) such as '{example}' use a {found}.")
_add("I37", "", "warning", "numbers use one decimal mark",
     "some numbers use a point and some a comma as the decimal mark ({points} with a point, {commas} with a comma, for example '{example}'). Check the file.")
_add("I38", "", "warning", "numbers have no thousands separators",
     "{n} cell(s) such as '{example}' look like numbers with thousands separators, which are not supported. Remove the separators in the file.")

# ---------------------------------------------------------------- information (notes)
_add("I18", "", "warning", "the declared column separator fits the file",
     "the setup says the columns are separated by a {declared}, but the file looks like it uses a {found}, so everything was read as one column. Change the setting, or set it to auto.")
_add("I20", "", "note", "the column separator was detected", "the columns are separated by a {name} (detected from the file).")
_add("I22", "", "note", "UTF-16 text without a mark is recognised", "the file is UTF-16 text without a byte-order mark; it was recognised and read.")
_add("I23", "", "note", "a byte-order mark is recognised", "the file starts with a byte-order mark ({encoding}); it was recognised and removed.")
_add("I24", "", "note", "mixed line endings are read", "the file mixes line endings ({counts}); every kind is read correctly.")
_add("I26", "", "note", "odd spaces in column names are tidied",
     "{n} column name(s) had extra or odd spaces and were tidied (for example '{old}' became '{new}'). Names are matched ignoring capital letters and spaces.")
_add("I28", "", "note", "empty columns are left out", "{n} column(s) with no name and no values were left out.")
_add("I29", "", "note", "blank rows are skipped", "{n} blank row(s) were skipped.")
_add("I31", "", "note", "rows above the header are ignored", "{n} row(s) above the header row were ignored.")
_add("I32", "", "note", "spaces around values are removed", "{n} cell(s) had spaces around the value; the spaces were removed.")
_add("I34", "", "note", "Excel dates are read as dates", "{n} Excel date cell(s) were read as real dates.")
_add("I35", "", "note", "a decimal comma is recognised", "numbers use a comma as the decimal mark ({n} cell(s) such as '{example}').")
_add("I40", "", "note", "a summary of what was read", "read {rows} row(s) and {columns} column(s) ({how}).")


# ================================================================ Stage 2c: from text to typed values
# ---- the setup and the file do not fit together (errors)
_add("I41", "", "error", "every mapped column is in the file",
     "the setup maps the column '{column}' but the file has no such column. It has: {have}.{hint}")
_add("I42", "", "error", "no two columns become the same ID", "two columns ('{first}' and '{second}') both become '{id}'. Each ID can come from one column.")
_add("I43", "", "error", "a number column holds numbers",
     "'{column}' should hold numbers but {n} of its {total} values are not numbers (for example {example}). Check the column mapping, or the decimal mark.")
_add("I44", "", "error", "missing values are allowed", "{n} value(s) are missing in {columns}, and the setup says to stop when values are missing.")
_add("I45", "", "error", "most dates can be read", "{n} of {total} dates could not be read as '{format}' (for example {example}). Check the date format in the setup.")
_add("I47", "weight_column", "error", "the total-weight column is in the table",
     "the total weight '{id}' is not a column of this table, so amounts cannot be converted to a percentage. Check the column mapping.")
_add("I47", "name_clash", "error", "a converted percentage does not reuse an existing ID",
     "converting '{amount}' to a percentage would create '{new}', which already exists. Rename one of them.")

# ---- read, but something was set to missing, assumed or kept as it was (warnings)
_add("I46", "", "warning", "every value in a number column is a number",
     "'{column}': {n} value(s) are not numbers (for example {examples}); they were treated as missing. If they mean 'no value', list them under missing_markers in the setup.")
_add("I48", "", "warning", "dates can be read",
     "{n} of {total} dates could not be read as '{format}' (for example {examples}); they were treated as missing.")
_add("I49", "", "warning", "the date format is stated", "the setup gives no date format, so dates were read as year-month-day (yyyy-mm-dd). Add one under 'date' if that is not right.")
_add("I50", "", "warning", "values are plausible", "'{column}': {n} value(s) are {why} (lowest {low}, highest {high}); they were kept as they are.")
_add("I51", "", "warning", "a unit that is assumed is marked as assumed", "'{column}': the unit ({unit}) is an assumption: {why}.")
_add("I52", "", "warning", "an assumed conversion is marked as assumed",
     "{n} value(s) of '{column}' were converted from {unit} to {target} by dividing by {divide} ({note}). This conversion is assumed, not exact.")
_add("I54", "", "warning", "values above a limit are handled",
     "'{column}': {n} value(s) written as above a limit (for example '{example}') were treated as missing.")
_add("I55", "", "warning", "values below a limit have a rule",
     "'{column}': {n} value(s) written as below a limit (for example '{example}') were treated as missing, because the setup has no below-detection rule.")
_add("I56", "", "warning", "a below-detection value agrees with its limit",
     "{n} row(s) are marked '{marker}' in {note} but '{column}' holds something other than the limit {limit} (for example {example}); the rule was applied anyway.")
_add("I57", "", "warning", "every unit has a conversion",
     "'{column}': {n} value(s) have the unit '{unit}', which has no conversion in the setup; they were treated as missing.")
_add("I68", "", "warning", "units in a column match what the setup expects",
     "'{column}': the file's values are in {declared} but the setup expects {expected}, and no conversion is defined, so the values are used as they are.")
_add("I59", "flagged", "warning", "amounts add up to the total weight",
     "{n} of {total} rows ({share}) differ from the total weight by more than {tolerance}% (largest shortfall {shortfall}%, largest overshoot {overshoot}%). "
     "The exact gap, in percent of the weight, is kept for every row in 'mass_balance_gap_pct' (negative means the listed amounts fall short).")
_add("I60", "", "warning", "every row has a usable total weight",
     "{n} row(s) have no usable total weight or a missing amount, so their percentages and weight gap were left empty (the first is row {row}).")
_add("I65", "month_only", "warning", "dates are precise enough to order events",
     "the dates are month-only ({n} different months, {first} to {last}): the order of events inside a month is not known. This matters when validating on later dates.")

# ---- information (notes)
_add("I53", "", "note", "below-detection values are flagged",
     "'{column}': {n} value(s) written below a limit were handled with the rule '{rule}' (limit {limit}); they are flagged in '{flag}'.")
_add("I58", "dropped", "warning", "rows dropped for missing values", "ROWS DROPPED: {n} row(s) were dropped because a value the setup requires was missing (the first is row {row}).")
_add("I59", "ok", "note", "amounts add up to the total weight", "all {total} rows add up to the total weight within {tolerance}% (largest gap {gap}%).")
_add("I61", "", "note", "rows are identified", "the file has no experiment ID column, so each row was named after its row number (for example '{example}').")
_add("I62", "", "note", "unused columns are listed", "{n} column(s) in the file are not used by the setup (for example {examples}).")
_add("I63", "", "note", "values converted to a percentage are listed",
     "{n} amount column(s) were converted to a percentage of the total weight '{weight}'; each new ID ends in _pct.")
_add("I64", "", "note", "text meaning 'no value' is listed", "text meaning 'no value' was found and treated as missing: {counts}.")
_add("I65", "range", "note", "the date range is shown", "dates run from {first} to {last} ({n} dates read, {precision} precision).")
_add("I66", "", "note", "columns that were not declared are listed",
     "{n} mapped column(s) are not named in the setup's lists of ingredients, settings, factors or targets; each was read as numbers when every value is one, otherwise as text: {names}.")
_add("I70", "", "note", "converted values are counted", "{n} value(s) of '{column}' were converted from {unit} to {target} by dividing by {divide}.")


# ================================================================ Stage 2d: dates with two-digit years, failed runs, replicates, joins
_add("I71", "", "warning", "two-digit years are read by a stated rule",
     "{n} date(s) were written with a 2-digit year and were read by this rule: 00 to 69 mean 2000 to 2069, and 70 to 99 mean 1970 to 1999 "
     "(for example '{example}' became {result}). If your data needs other years, write 4-digit years (yyyy) in the setup's date format.")
_add("I72", "", "error", "the replicate grouping names columns the table has",
     "the replicate grouping uses '{name}', which is not a column or ID of this table. Its columns are: {have}.")
_add("I73", "", "warning", "replicates agree on text columns",
     "{n} group(s) of replicate rows disagree on '{column}' (for example {example}); the first value was kept.")
_add("I74", "", "note", "replicates were combined",
     "{groups} group(s) of replicate rows ({rows} rows) were combined into one row each (rule: {rule}); the individual rows are {kept}.")
_add("I74", "none", "note", "no replicates were found", "no replicates were found: every row has its own {keys}.")
_add("I74", "kept_all", "note", "replicates are found and all rows kept",
     "{groups} group(s) of replicate rows ({rows} rows) were found and every row was kept (rule: keep_all); 'replicate_count' says how many rows share each key.")
_add("I75", "removed", "warning", "failed runs are set aside",
     "{n} of {total} rows ({share}) are failed runs ('{column}' is '{value}') and were set aside from the table: {where}.")
_add("I75", "kept", "note", "failed runs kept in the table",
     "{n} of {total} rows ({share}) are failed runs ('{column}' is '{value}'). The setup keeps them in the table, flagged in 'is_failed'.")
_add("I76", "", "note", "the values of the status column are listed", "the values found in '{column}': {counts}.")
_add("I77", "", "note", "a file with no failed-run settings", "the setup has no failed-run settings, so no run is treated as failed.")
_add("I78", "", "error", "a joined file has one row per key",
     "{file} has more than one row for the same key (for example {example}; {n} such key(s)), so it is not clear which row to join. Each key must appear once.")
_add("I79", "", "warning", "every row finds its match in a joined file",
     "{n} of {total} rows have no match in {file} (for example {example}); the columns taken from it are empty for those rows.")
_add("I80", "", "note", "every row of a joined file is used", "{n} row(s) of {file} matched nothing and were not used.")
_add("I81", "", "note", "joined columns are counted", "added {n} column(s) from {file}: {matched} of {total} rows matched.")
_add("I82", "", "error", "a join column is in both files", "the join column '{column}' is not in {file}. Check the join in the setup.")
_add("I83", "", "error", "a joined file adds no column with a name already taken",
     "{file} has a column '{column}' that is already in the table. Give the joined columns a prefix in the setup.")
_add("I84", "changed", "warning", "the row count changed",
     "ROW ACCOUNTING: {read} rows read; {dropped} dropped for missing values; {failed} failed runs {failed_where}; {merged} replicate rows combined; {out} rows in the table.")
_add("I84", "unchanged", "note", "every row is in the table", "ROW ACCOUNTING: {read} rows read; every row is in the table.")

@dataclass(frozen=True)
class Finding:
    rule: str
    variant: str
    level: str
    where: str        # the file name
    column: str       # a column name, or "" for the whole file
    text: str

    @property
    def message(self) -> str:
        return f"{self.where} › {self.column}: {self.text}" if self.column else f"{self.where}: {self.text}"


def make(rule_id: str, variant: str, where: str, column: str = "", /, **values) -> Finding:
    rule = CATALOGUE[(rule_id, variant)]
    return Finding(rule_id, variant, rule.level, where, column, rule.template.format(**values))


def has_errors(findings: list[Finding]) -> bool:
    return any(f.level == "error" for f in findings)
