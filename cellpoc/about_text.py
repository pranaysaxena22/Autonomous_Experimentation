"""The plain-language statements about what this simulation does and does not show.

One source for both the scenario page (docs/scenario.md) and the dashboard's last page, so
they can never disagree. Numbers come from the actual runs, never typed in by hand.
Note the wording: the trial count is always "about 29 to 30" style, never a bare figure,
because it hangs on a small timing margin (see `trial_count_phrase`).
"""
from __future__ import annotations

from .contracts import AboutRecord, ComparisonResult, RunRecord
from .settings import Settings


def trial_count_phrase(default_run: RunRecord, other_cleaning_run: RunRecord) -> str:
    """e.g. 'about 29 to 30 trials': the counts with cleaning after a skipped candidate switched on and off."""
    counts = sorted({default_run.summary.trials_attempted, other_cleaning_run.summary.trials_attempted})
    return f"about {counts[0]} to {counts[-1]} trials" if len(counts) > 1 else f"about {counts[0]} trials"


def _margin_minutes(settings: Settings, run: RunRecord) -> int:
    """Minutes left after the last trial finished."""
    return int(run.meta.duration_minutes - max(t.end_minute for t in run.trials))


def margin_sentence(settings: Settings, default_run: RunRecord, other_run: RunRecord) -> str:
    needed = settings.cell.minutes_per_trial
    clean_on, clean_off = (default_run, other_run) if settings.scripted_faults.clean_after_skip else (other_run, default_run)
    short = int(needed - _margin_minutes(settings, clean_on))
    spare = _margin_minutes(settings, clean_off)
    return (f"The number of trials depends on a margin of about {min(abs(short), spare)} minutes. "
            f"With cleaning after the skipped candidate, one more trial ({needed:g} minutes) misses fitting by {short} minutes; "
            f"without that cleaning the last trial finishes with {spare} minutes to spare. "
            "A small change to any step time, purge time or the cleaning setting moves the count between these two numbers.")


def limitations(settings: Settings, default_run: RunRecord, other_run: RunRecord) -> list[str]:
    return [
        "Ingredients are not forced to sum to 100%. Each of the five percentages is varied independently within its own range, "
        "so a recipe's ingredients can add up to more or less than 100%. A real design space would normally fix one ingredient "
        "(often the filler) as the remainder.",
        "The tablet behaviour is a made-up placeholder. The virtual lab's hidden truth is a smooth illustrative model, not real "
        "pharmaceutical data, and all values are illustrative.",
        "The hidden truth is smooth, which favours a strategy that learns a model of it. Real formulation data would be rougher, "
        "so the size of the adaptive strategy's lead is illustrative, not a prediction.",
        "A symptom of that smoothness: in the default comparison the adaptive strategy typically finds its first good recipe within "
        "one or two choices after its six starting recipes, so its median and its 75th-percentile trial coincide. A model fitted to "
        "six results is already enough to point at the good region of a smooth surface; a rougher real surface would take longer to learn.",
        margin_sentence(settings, default_run, other_run),
        "Fault timing is assumed: a failed attempt takes the step's full duration, the cell then purges and retries, and after a "
        "skipped candidate it cleans (a setting) before moving on. Different assumptions give different counts.",
        "One trial at a time. The cell never works on two trials at once; overlapping trials are a future extension.",
        "Measurement noise is the only random effect in the lab. There is no instrument drift, no reagent run-out and no recalibration.",
        "Charts work offline, fonts may not: Open Sans is used only if it is installed on the viewing computer; otherwise the browser shows Arial.",
    ]


def _comparison_note(comparison: ComparisonResult | None) -> str:
    if comparison is None or not comparison.difficulty:
        return "The comparison has not been run for this record."
    gaps = []
    for row in comparison.difficulty:
        adaptive = next(s for s in row.strategies if s.label == "Adaptive")
        others = [s.found_pct for s in row.strategies if s.label != "Adaptive"]
        gaps.append((row.level, row.good_share_pct, adaptive.found_pct - max(others)))
    detail = "; ".join(f"{level} ({share:g}% of random recipes truly good): {gap:+.0f} points" for level, share, gap in gaps)
    shrinks = all(a[2] >= b[2] for a, b in zip(gaps, gaps[1:]))
    lead = ("The advantage of learning shrinks when good recipes are common: when almost any recipe works, there is little left to learn. "
            if shrinks else "In this data the advantage of learning does not steadily shrink as good recipes become common. ")
    return (lead + "Adaptive's lead over the better of the other two strategies, in percentage points of campaigns that found "
            f"a good recipe within {comparison.trials_per_campaign} trials: {detail}.")


def build_about(settings: Settings, default_run: RunRecord, other_run: RunRecord,
                comparison: ComparisonResult | None) -> AboutRecord:
    s = default_run.summary
    count = trial_count_phrase(default_run, other_run)
    shows = [
        f"An unattended cell can run a multi-day sequence of trials on its own: {count} fit the run window "
        f"({s.attempts_text.replace(' attempted', ' attempted in this run')}), with nobody in the lab for "
        f"{s.unattended_hours:g} of {s.run_hours:g} hours.",
        "How the cell copes with problems: a fault it recovers from by itself, and a candidate it skips after a failed retry with an "
        "alert queued for the next working day.",
        "Every decision comes with a plain-language reason, and every phase of every trial (Sense, Reason, Act, Adapt) is logged with its time.",
        (f"How a strategy that learns compares with a fixed list and with random recipes over {comparison.campaigns} repeated campaigns "
         f"of {comparison.trials_per_campaign} trials, on the same seeds." if comparison else "The strategy comparison."),
        "How much more experimentation an unattended cell could fit into the same calendar than a manual baseline you can edit.",
    ]
    throughput = (f"Autonomous: {s.trials_with_result} trials with results in {s.run_hours:g} hours, scaled to a 168-hour week, is "
                  f"{s.trials_per_week:g} per week. The manual baseline ({s.manual_baseline_trials_per_week:g} per week by default) is an "
                  "assumption you can edit. Dividing the first by the second is the only calculation this dashboard performs.")
    return AboutRecord(shows, limitations(settings, default_run, other_run), _comparison_note(comparison), throughput)
