"""The replay reports: one plain document per synthetic table and one summary.

The reports keep three things apart, in their own sections: results that were REPLAYED (synthetic mocks only; a borderline result carries its EXPLORATORY label in every heading), results NOT REPLAYED
because no client-specified target exists (real batch hardness and tensile strength: the fixed sentence, and no invented window), and results NOT REPLAYED because they were not carried in 3b-1.
Every heading carries the data-status label. Whenever a number about the warning appears, the shift type it holds for appears with it, and the statement of what the mocks cannot show is never left out.
No clock time.
"""
from __future__ import annotations

from .carry import BORDERLINE, CARRIED, STATUS_WORDS, CarryDecision
from .findings import NO_REPLAY_SENTENCE, UNIFYING_STATEMENT
from .models import MODELS_BY_KEY as MODELS
from .replay import BEAT, DRAWS, MIN_WARNED, NO_ROOM, NO_ROOM_GAP, NO_ROOM_RANDOM, NOT_BEAT, PICK_SHARE, Reliability, TableReplay, TargetReplay
from .validate import Validation

SYNTHETIC_LABEL = "SYNTHETIC DATA"

EXPLAIN = [
    "A **decision window** is one forward step of the Stage 3a later-dates comparison: the model was trained on rows dated before the window and on nothing else, and these reports read its saved predictions "
    "(nothing is refitted). Every window is checked again for a leak before it is used.",
    "The **targets** are the ones in the setup (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0 in the mock setups). A recipe **passes** when its measured value meets the target.",
    "Recipes are **ranked** by the model's own probability that the target is met, worked out from its predicted value and its stated 90% range as stated (not recalibrated), read as a bell-shaped spread. "
    "For all three targets together the three probabilities are multiplied, which assumes the three results are independent; they are not.",
    f"The **top {100 * PICK_SHARE:.0f}%** of each window are picked. They are compared with picking at random (the window's own pass rate) and with the perfect ranking (every passer first). "
    "**Captured share** = (picked - random) / (perfect - random): 0 is no better than random, 1 is perfect.",
    f"The **error bar** is a 95% interval for (picked rate - random rate) from resampling whole batches inside each window ({DRAWS} draws), because recipes of one batch are not independent. "
    f"**Verdict, fixed in advance:** '{BEAT}' only if the picked rate is above random and the interval's lower end is above 0; '{NOT_BEAT}' otherwise; '{NO_ROOM}' (no verdict) when random picking "
    f"already passes at least {100 * NO_ROOM_RANDOM:.0f}% of the time or perfect picking beats it by under {100 * NO_ROOM_GAP:.0f} percentage points.",
]

LIMITS = [
    "Anything about real tablets or a client: these tables are synthetic, made by `tools/make_mock_data.py`. The result is about whether the METHOD can rank recipes, not about any real product.",
    f"How well the model ranks near the margin: the picks are the {100 * PICK_SHARE:.0f}% of recipes the model was most sure of, which sit well inside the target. The synthetic mocks are also easy to rank "
    "(the easy mock especially), so a high captured share here is the best case, not an expectation.",
    "Whole recipes: a pick is one measured row, and repeat measurements of the same recipe are separate rows (in these mocks about 1.2 rows per recipe), so the number of different recipes picked is a little smaller than the number of picks.",
    "Real input drift or a real supplier change: see the section on the warning above. The mocks cannot show either.",
    "Anything for real batch hardness or tensile strength, where no client-specified target exists: the replay is not run for them and no window is invented.",
]


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def points(x: float) -> str:
    return f"{100 * x:+.1f}"


def _windows_table(t: TargetReplay) -> list[str]:
    lines = ["| Step | Dates | Recipes tested | Picked | Picks that passed | Random picking would pass | Perfect picking would pass |", "|---|---|---|---|---|---|---|"]
    for w in t.summary.windows:
        lines.append(f"| {w.number} | {w.first} to {w.last} | {w.n} | {w.picks} | {w.hits} | {w.random_expected:.1f} | {w.perfect} |")
    return lines + [""]


def _result_block(t: TargetReplay, label: str, heading_level: str = "###") -> list[str]:
    s = t.summary
    models = ", ".join(MODELS[m].label for m in dict.fromkeys(t.models.values()))
    lines = [f"{heading_level} {t.heading} [{label}]", ""]
    if t.exploratory:
        lines += ["**EXPLORATORY: this includes a borderline result (3b-1). It is shown for information and is never part of the main findings.**", ""]
    lines += [f"Model used (the Stage 3a rule's choice): {models}.", ""]
    lines += _windows_table(t)
    if s.verdict == NO_ROOM:
        lines += [f"**No verdict: {NO_ROOM}.** Picked {pct(s.picked_rate)}, random {pct(s.random_rate)}, perfect {pct(s.perfect_rate)}.", ""]
    else:
        ci = f"{points(s.interval[0])} to {points(s.interval[1])} percentage points" if s.interval else "no error bar"
        lines += [f"**Picked {pct(s.picked_rate)} against random {pct(s.random_rate)} and perfect {pct(s.perfect_rate)}.** "
                  f"Gain over random {points(s.gap)} points (95% interval {ci}); captured share {'n/a' if s.captured is None else f'{s.captured:.2f}'}. **Verdict: {s.verdict}.**", ""]
    lines += ["**Did warned picks do worse? (later dates only; each status on its own, never combined)**", "",
              "| Per-recipe status | Picks warned | Pass rate of warned picks | Pass rate of unwarned picks | Said? |", "|---|---|---|---|---|"]
    names = {"distance": "(1) Distance", "range": "(2) Numeric range", "category": "(3) Unseen supplier or product"}
    for key, w in t.warned.items():
        lines.append(f"| {names[key]} | {w.warned} of {s.picks} | {pct(w.warned_rate) if w.said else 'n/a'} | {pct(w.unwarned_rate) if w.said else 'n/a'} | "
                     + ("yes" if w.said else f"no: fewer than {MIN_WARNED} warned picks") + " |")
    lines += [""] + [f"- {f.text}" for f in t.findings] + ([""] if t.findings else [])
    if not t.same_inputs:
        lines += ["- The results do not use exactly the same inputs; the warnings above use the first result's inputs.", ""]
    return lines


def _reliability_block(r: list[Reliability], replay: TableReplay, label: str) -> list[str]:
    lines = [f"## Can the warning be trusted, and for which kind of shift? [{label}]", "",
             "The replay itself is **forward in time**, so it can only speak for the later-dates shift. The whole-batch and whole-supplier lines come from the saved Stage 3a hold-outs of the same results "
             f"(3b-2), shown beside it and never merged into one number. A kind of shift is judged only when at least {MIN_WARNED} rows were warned in every result; 'picks out the large errors' means the "
             "distance check's lift is above 1 (chance) in every result.", "",
             "| Kind of shift | Rows warned by distance (each result) | Lift (1.0 = chance, each result) | Rows warned by numeric range | Reading |", "|---|---|---|---|---|"]
    for x in r:
        lifts = ", ".join("n/a" if v is None else f"{v:.2f}" for v in x.lifts)
        reading = x.verdict + (f" (fewer than {MIN_WARNED} warned rows)" if x.verdict == "cannot be judged" else "")
        lines.append(f"| {x.heading} | {', '.join(str(n) for n in x.rows_warned)} | {lifts} | {', '.join(str(n) for n in x.range_warned)} | **{reading}** |")
    m = replay.movement
    drift = "n/a" if m.drift is None else f"{m.drift:.2f} ({m.drift_input})"
    supplier = "n/a" if m.supplier is None else f"{100 * m.supplier:.1f}% ({m.supplier_input})"
    lines += ["", f"**{UNIFYING_STATEMENT}**", "",
              "**What these synthetic tables cannot show.** In them a supplier changes the measured result, not the recipe, and recipes are not chosen differently over time. "
              f"The largest rank correlation of any input with the date is {drift}; the largest share of an input's spread explained by the supplier is {supplier}. "
              "So neither shift can be seen by a check that looks only at recipe inputs, the numeric range check never fires, and a good later-dates result here is the easy case: it says nothing about real input drift or a real supplier change, "
              "where the same warning did not reliably pick out the large errors under later dates on the real public batch data (see the warning summary).", ""]
    return lines


def build_report(validation: Validation, replay: TableReplay) -> str:
    table = validation.table
    label = table.label.short if table.label else "DATA STATUS NOT STATED"
    lines = [f"# Decision-usefulness replay [{label}]: {table.name}", "",
             f"**This report is {label}.** It asks whether a model's ranking would have chosen better recipes than chance on this synthetic table. It is not a prediction about real tablets or a client.", "",
             f"## How to read this [{label}]", ""] + [f"- {e}" for e in EXPLAIN] + [""]
    replayed =[t for t in replay.targets if not t.exploratory]
    exploratory = [t for t in replay.targets if t.exploratory]
    if replayed:
        lines += [f"## Replayed results [{label}]", ""]
        for t in replayed:
            lines += _result_block(t, label)
    if exploratory:
        lines += [f"## Replayed, but exploratory (borderline) [{label}]", "", "These include a result whose model is only borderline in 3b-1. They are never part of the main findings.", ""]
        for t in exploratory:
            lines += _result_block(t, label)
    if replay.not_replayed:
        lines += [f"## Not replayed [{label}]", ""] + [f"- **{table.column_label(r)}**: {why}." for r, why in replay.not_replayed] + [""]
    if replay.targets:                  # a table with nothing replayed has nothing to say about the warning here
        lines += _reliability_block(replay.reliability, replay, label)
    lines += [f"## What this does not show [{label}]", ""] + [f"- {x}" for x in LIMITS]
    return "\n".join(lines) + "\n"


def build_summary(validations: list[Validation], decisions: list[CarryDecision], replays: dict[str, TableReplay]) -> str:
    lines = [f"# Decision-usefulness replay: summary [{SYNTHETIC_LABEL}, replayed on the synthetic mocks only]", "",
             f"**The replay is run on synthetic data only ({SYNTHETIC_LABEL}).** It asks whether ranking recipes by a model's probability of meeting the targets would have chosen better than chance, using only data "
             "before each decision. It says nothing about real tablets or a client.", "",
             f"## How to read this [{SYNTHETIC_LABEL}]", ""] + [f"- {e}" for e in EXPLAIN] + [""]
    lines += [f"## Part A: replayed results [{SYNTHETIC_LABEL}]", "",
              "| Table | Target | Picked | Random | Perfect | Captured share | 95% interval for the gain (points) | Verdict |", "|---|---|---|---|---|---|---|---|"]
    exploratory_rows = []
    for name, rep in replays.items():
        for t in rep.targets:
            s = t.summary
            ci = f"{points(s.interval[0])} to {points(s.interval[1])}" if s.interval else "n/a"
            row = (f"| {name} | {t.heading} | {pct(s.picked_rate)} | {pct(s.random_rate)} | {pct(s.perfect_rate)} | {'n/a' if s.captured is None else f'{s.captured:.2f}'} | {ci} | **{s.verdict}** |")
            (exploratory_rows if t.exploratory else lines).append(row)
    lines += [""]
    if exploratory_rows:
        lines += [f"## Part B: replayed, but exploratory (borderline) [{SYNTHETIC_LABEL}]", "",
                  "| Table | Target | Picked | Random | Perfect | Captured share | 95% interval for the gain (points) | Verdict |", "|---|---|---|---|---|---|---|---|"] + exploratory_rows + [""]
    lines += [f"## Part C: not replayed [{SYNTHETIC_LABEL} and real public data]", ""]
    for v in validations:
        name = v.table.name
        label = v.table.label.short if v.table.label else "DATA STATUS NOT STATED"
        tag = f" [{v.table.tag}]" if v.table.tag else ""
        for d in (d for d in decisions if d.table == name):
            if name in replays and d.status in (CARRIED, BORDERLINE) and any(d.result in t.results for t in replays[name].targets):
                continue
            head = f"- **{name}, {v.table.column_label(d.result)}** [{label}]{tag} ({STATUS_WORDS[d.status]}): "
            lines.append(head + (NO_REPLAY_SENTENCE if d.status in (CARRIED, BORDERLINE) else "replay not run; it was not carried in 3b-1 (see the calibration summary)."))
    lines += [""]
    first = next(iter(replays.values()), None)
    if first is not None:
        lines += [f"## Can the warning be trusted, and for which kind of shift? [{SYNTHETIC_LABEL}]", "", f"**{UNIFYING_STATEMENT}**", "",
                  "Per table and kind of shift, from the saved hold-outs (the replay itself is later-dates only):", "",
                  "| Table | Kind of shift | Rows warned by distance (each result) | Reading |", "|---|---|---|---|"]
        for name, rep in replays.items():
            for x in rep.reliability:
                lines.append(f"| {name} | {x.heading} | {', '.join(str(n) for n in x.rows_warned)} | **{x.verdict}** |")
        lines += ["", "**What the synthetic tables cannot show:** a supplier changes the measured result and not the recipe, and recipes do not move with the date, so an input-based warning cannot see either shift here. "
                  "A good later-dates result on these tables is the easy case and says nothing about real input drift or a real supplier change.", ""]
    lines += [f"## What this does not show [{SYNTHETIC_LABEL}]", ""] + [f"- {x}" for x in LIMITS]
    return "\n".join(lines) + "\n"
