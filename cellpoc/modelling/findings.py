"""Every message the modelling part can show, in one place, so the wording can be reviewed without reading code.

A finding is an error (the table cannot be modelled), a warning (something was left out or limited, and you should know) or a note
(information that every report must carry). The full message reads "<table> > <place>: <text>". docs/modelling_messages.md is generated
from this catalogue and the tests, and the health check fails if any message has no test.
"""
from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("error", "warning", "note")

# The one place this phrase is written. Wherever a stand-in for a supplier is shown (a heading, a table, a chart, a note), it carries
# exactly these words: a result is never presented as being about suppliers when the column is only a proxy.
PROXY_PHRASE = "proxy, not a confirmed supplier"

# Two sentences the user fixed word for word. They are written here once; every report and the scorecard quote them from here.
UNIFYING_STATEMENT = "Everything built so far recognizes batch-level variation well, but struggles specifically when the shift is a new supplier or a later time period."
NO_REPLAY_SENTENCE = ("Decision-usefulness replay not run; no client-specified target exists for this result. "
                      "The method is proven on synthetic data and can be applied here once real specification limits are available.")
# Required, word for word, in every report that shows results from the sealed acceptance lab (the user's wording, 2026-10-11). It is written here once; the seal check fails if an acceptance report lacks it.
ACCEPTANCE_CAVEAT = ("This lab's shape constants were adjusted twice by someone aware of Stage 3's findings, though no Stage 3 model or code was consulted. "
                     "This is not a fully blind acceptance test.")

# Fewer usable rows than this and a result is not modelled (the grouped checks need several rows in every group).
MIN_ROWS = 30
# The shape of the grouped checks. Fixed in advance and never changed after seeing a score.
MIN_TEST = 10             # fewest rows a held-out fold may have
FOLDS = 5                 # folds of whole batches (or APIs); a supplier hold-out leaves one supplier out at a time when there are at most LEAVE_ONE_OUT_MAX
LEAVE_ONE_OUT_MAX = 10
STEPS = 4                 # forward-in-time steps
FIRST_TRAIN_SHARE = 0.5   # the earliest half of the dates is always training; the later half is tested in STEPS blocks
MIN_TIMES = 6             # fewest distinct dates for forward steps

# An input this closely tracks a result (correlation, either kind) is treated as a copy of it and left out. Exact copies score 1.0000; a very strong
# honest input (for example drug load for dissolution) scores about 0.99, so the line is drawn where less than 0.2% of the result's variation is left over.
COPY_CORRELATION = 0.999


@dataclass(frozen=True)
class Rule:
    id: str
    variant: str
    level: str
    what: str            # what is checked, in words
    template: str        # the message text, with {placeholders}


@dataclass(frozen=True)
class Finding:
    rule: str
    variant: str
    level: str
    table: str
    place: str           # a result, an input, a group: what the message is about ("" = the whole table)
    text: str

    @property
    def message(self) -> str:
        return f"{self.table} > {self.place}: {self.text}" if self.place else f"{self.table}: {self.text}"


CATALOGUE: dict[tuple[str, str], Rule] = {}


def _add(rule_id: str, variant: str, level: str, what: str, template: str) -> None:
    CATALOGUE[(rule_id, variant)] = Rule(rule_id, variant, level, what, template)


# ---------------------------------------------------------------- the table cannot be modelled (errors)
_add("M01", "", "error", "the setup says what to predict",
     "this setup has no 'validation' section under 'data', so it does not say what to predict or which columns define batches, suppliers and dates. Add one.")
_add("M02", "", "error", "the data could be read",
     "the data could not be read, so there is nothing to model. See the data quality report for why.")
_add("M03", "result", "error", "a result to predict is a column of the table",
     "the result '{name}' is not a column of the cleaned table. Check its ID in the column mapping.")
_add("M03", "input", "error", "an input is a column of the table",
     "the input '{name}' is not a column of the cleaned table. Check its ID in the column mapping.")
_add("M03", "group", "error", "a group column is a column of the table",
     "the group column '{name}' is not a column of the cleaned table. Check its ID in the column mapping.")
_add("M04", "", "error", "there is something to predict from",
     "the setup lists no inputs and has no ingredients, process settings or context factors to use instead. List the inputs under 'validation'.")

# ---------------------------------------------------------------- something was left out or limited (warnings)
_add("M10", "same", "warning", "an input is not the result itself",
     "'{name}' was left out of the inputs for this result because it is the result itself.")
_add("M10", "source", "warning", "an input is not something the result is calculated from",
     "'{name}' was left out of the inputs for this result because the result is calculated from it (it would hand the model the answer).")
_add("M10", "derived", "warning", "an input is not calculated from the result",
     "'{name}' was left out of the inputs for this result because it is calculated from the result (it would hand the model the answer).")
_add("M10", "copy", "warning", "an input is not a copy of the result",
     "'{name}' was left out of the inputs for this result because it tracks the result almost exactly (correlation {correlation}, over {n} rows). It looks like a copy or a recalculation of the result.")
_add("M11", "", "warning", "every row has a value for the result",
     "{n} of {total} rows ({share}) have no value for this result and were left out for it. Nothing was filled in.")
_add("M12", "", "warning", "every row has a value for every input",
     "{n} more rows ({share} of those with a result) have no value for at least one input and were left out for this result. Inputs missing most often: {inputs}. Nothing was filled in.")
_add("M13", "", "warning", "enough rows are left to model the result",
     "only {n} rows are left for this result, fewer than the {minimum} needed to check it on whole groups, so it is not modelled.")
_add("M14", "", "warning", "the result varies",
     "every row has the same value, so there is nothing to learn and it is not modelled.")
_add("M15", "", "warning", "an input varies",
     "'{name}' has the same value in every row, so it carries no information and was left out of the inputs.")

_add("M30", "none", "warning", "a hold-out type has a column to use",
     "the setup names no column for this hold-out, so it is not run. No random rows are used in its place.")
_add("M30", "few_groups", "warning", "a hold-out type has at least two groups",
     "only {n} group(s) are left for this result, and a hold-out needs at least 2, so it is not run. No random rows are used in its place.")
_add("M30", "few_times", "warning", "forward steps have enough dates",
     "only {n} distinct date(s) are left for this result, and forward steps need at least {minimum}, so they are not run. No random rows are used in their place.")
_add("M30", "no_fold", "warning", "at least one fold is big enough",
     "no fold has at least {test} test rows and {train} training rows, so this hold-out is not run. No random rows are used in its place.")
_add("M31", "", "warning", "every row has a group value",
     "{n} rows have no value in the group column(s) and are left out of this hold-out (they cannot be put in a group). They stay in the other hold-outs.")
_add("M32", "", "warning", "every fold is big enough",
     "fold {number} was dropped: it has {test} test rows and {train} training rows, and a fold needs at least {min_test} test rows and {min_train} training rows.")

_add("M40", "", "warning", "every model can be fitted on every fold",
     "skipped on this fold because {reason}.")
_add("M41", "", "warning", "every model fits without error",
     "could not be fitted on this fold, so it has no result here.")
_add("M43", "", "warning", "a ridge penalty is chosen on whole groups inside the training rows",
     "the penalty could not be chosen by validation on whole groups inside the training rows (too few groups), so the default penalty of 1 was used on this fold.")
_add("M50", "tag", "note", "a table that cannot support an accuracy claim is not calibrated",
     "calibration not assessed: {why}.")
_add("M50", "no_model", "note", "a result no model predicts is not calibrated",
     "calibration not assessed: no model beats the baseline, so there is nothing to calibrate.")
_add("M50", "weak", "note", "a result predicted too weakly is not calibrated",
     "calibration not assessed: the best model's error is {worst} of the result's spread in its hardest hold-out type, so it explains at most about {share}% of the variation there. "
     "A calibration number for a model this weak would not matter.")
_add("M50", "small", "note", "a table with too few held-out rows is not calibrated",
     "calibration not assessed: only {n} held-out rows, fewer than the {minimum} needed for a hit rate to mean anything.")
_add("M51", "", "note", "a borderline result is carried as exploratory",
     "EXPLORATORY: borderline result (its worst error is {worst} of the result's spread, between the {carry} carry line and the {skip} skip line). It is calibrated for information only and is not part of the main findings.")
_add("M52", "", "warning", "every fold can be recalibrated",
     "{n} fold(s) could not be recalibrated ({why}); they are shown as they are.")
_add("M60", "", "warning", "the warning can set a threshold on every fold",
     "no distance threshold could be set on {n} fold(s) (too few groups or rows in the training data), so the distance check is off on them.")
_add("M61", "", "warning", "the warning's threshold is steady across folds",
     "the distance threshold {verdict} across the folds of this hold-out type: its largest value is {ratio} times its smallest (stable up to {stable}, varying up to {varying}).")
_add("M62", "", "warning", "the group warning knows how much groups normally differ",
     "only {n} training group(s) are big enough to show how much groups of this kind normally differ (at least {minimum} are needed), so these groups are compared with chance alone and are flagged more readily than they should be.")
_add("M63", "", "note", "every group is big enough to be assessed",
     "{n} held-out group(s) have fewer than {minimum} rows and were not assessed: too few recipes to say whether the group is unfamiliar.")
_add("M70", "", "note", "a target that leaves nothing to improve is not given a verdict",
     "no room to improve: picking at random already passes {random}% of the time and perfect picking would pass {perfect}%. A verdict needs a random pass rate under {line}% and a gap of at least {gap} "
     "percentage points, so no verdict is given.")
_add("M71", "", "note", "enough picks were warned before anything is said about them",
     "{n} of the {picks} picks were warned by the {status} check, fewer than the {minimum} needed, so it is not said whether warned picks did worse.")
_add("M42", "", "warning", "no model scores suspiciously well on held-out groups",
     "its R-squared on held-out groups is {r2} (above {limit}) for {hold_out}. That is too good to take at face value: CHECK FOR LEAKAGE (an input that is a copy or a recalculation of the result).")

# ---------------------------------------------------------------- facts every report must carry (notes)
_add("M33", "", "note", "how the groups are held out",
     "{method}.")
_add("M34", "", "note", "how forward steps are made",
     "{method}.")
_add("M35", "", "note", "month-only dates are stated",
     "every date is a month, so every row in a month shares one time value: a month is never split between training and test, and the order of events inside a month is unknown.")
_add("M20", "", "note", "the balance ingredient is not an input",
     "'{name}' (the balance ingredient) was left out of the inputs: the percentages add up to 100, so it is fully decided by the others. Keeping it would give the models the same information twice.")
_add("M21", "", "note", "the unlisted remainder is not an input",
     "the listed ingredients may add up to less than the tablet weight. That unlisted remainder equals 100 minus the listed percentages, so it is already implied and is not added as an input.")
_add("M22", "", "note", "rows whose amounts do not add up to the tablet weight are carried with their flag",
     "{n} rows are flagged because their listed amounts differ from the tablet weight by more than {tolerance}%. They are kept in training and in testing with their flag (column {flag}); "
     "the report shows scores with and without them.")
_add("M23", "", "note", "an assumed unit is carried with the column",
     "the unit of '{name}' is assumed, not confirmed ({why}). It is shown as '{name} (unit assumed)' in every table and report.")
_add("M24", "", "note", "a stand-in for the supplier says so",
     "the supplier groups come from '{column}': " + PROXY_PHRASE + ". {note}")
_add("M26", "", "note", "an exploratory comparison says so",
     "this comparison is exploratory only: {why}. It is never part of the main comparison or the scorecard, and every heading says so.")
_add("M25", "", "note", "columns left out on purpose are listed",
     "'{name}' is not modelled: {why}. This is a limitation for a formulation expert to review.")


def make(rule_id: str, variant: str, table: str, place: str = "", **values) -> Finding:
    rule = CATALOGUE[(rule_id, variant)]
    return Finding(rule.id, rule.variant, rule.level, table, place, rule.template.format(**values))


def has_errors(findings: list[Finding]) -> bool:
    return any(f.level == "error" for f in findings)
