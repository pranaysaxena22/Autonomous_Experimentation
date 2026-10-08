"""Stage 3 health check: the adaptive decision engine and the 40-campaign comparison.

Prints a PASS/FAIL list in plain words and writes files you can open in runs/stage3/:
  comparison.html        curves: how quickly each strategy finds a good recipe
  comparison_summary.txt the comparison in words and numbers
  campaigns.csv          every campaign, every strategy (open in Excel)
  demo_event_log.csv     the adaptive demonstration run, with the "why" behind every decision
  record.json            run record (adaptive demo run + comparison without faults)
  with-faults/record.json   the same, with the scripted faults applied to every strategy

Passing this check means the engine BEHAVES correctly. It does not assert that the engine wins:
how well each strategy does is reported, never tuned against.
"""
from __future__ import annotations

import csv
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.comparison import compare, run_campaign  # noqa: E402
from cellpoc.comparison.compare import campaign_seeds, first_trials, make_strategy  # noqa: E402
from cellpoc.contracts import Formulation, Measurement, meets_spec  # noqa: E402
from cellpoc.decision_engine import AdaptiveStrategy  # noqa: E402
from cellpoc.runner import run_demo  # noqa: E402
from cellpoc.settings import SettingsError, load_settings  # noqa: E402
from cellpoc.virtual_lab import VirtualLab, oracle  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, write_chart_page  # noqa: E402

OUT = ROOT / "runs" / "stage3"
checklist = Checklist("STAGE 3 CHECK - adaptive decision engine and the 40-campaign comparison")
record = checklist.record


def adaptive(settings, seed=None):
    return make_strategy("adaptive", settings, settings.run.random_seed if seed is None else seed)


def proposals(settings, strategy, lab_seed, skipped_trials=frozenset(), trials=30):
    return run_campaign(VirtualLab(settings, seed=lab_seed), strategy, trials, skipped_trials)


# ------------------------------------------------------------------ the engine
def check_engine(settings):
    seed = settings.run.random_seed
    n = settings.engine.initial_recipes
    run = proposals(settings, adaptive(settings), seed)

    start = run[:n]
    slices_ok = all(
        sorted(int((getattr(t.formulation, i.key) - i.min) / (i.max - i.min) * n - 1e-9) if getattr(t.formulation, i.key) < i.max
               else n - 1 for t in start) == list(range(n))
        for i in settings.design_space.ingredients)
    record(slices_ok, f"The first {n} recipes are spread evenly: each ingredient's range is cut into {n} slices and every slice is used once")

    again = proposals(settings, adaptive(settings), seed)
    record([t.formulation for t in run] == [t.formulation for t in again],
           "The same seed gives identical recipes, trial after trial")
    other_seed = proposals(settings, adaptive(settings, seed + 1), seed + 1)
    record([t.formulation for t in run] != [t.formulation for t in other_seed], "A different seed gives different recipes")

    different_lab = proposals(settings, adaptive(settings), seed + 500)
    first_same = [t.formulation for t in run[:n]] == [t.formulation for t in different_lab[:n]]
    later_differ = sum(a.formulation != b.formulation for a, b in zip(run[n:], different_lab[n:]))
    record(first_same and later_differ >= (30 - n) // 2,
           "The engine learns from results: with different readings the starting recipes match but later recipes change",
           f"{later_differ} of {30 - n} later recipes changed")

    class MadeUpLab:  # a lab that is not the virtual lab at all
        def measure(self, trial_id, formulation):
            return Measurement(trial_id, formulation, 80 + formulation.disintegrant, 8.0)
    try:
        made_up = run_campaign(MadeUpLab(), adaptive(settings), 12)
        record(len(made_up) == 12 and all(t.measurement for t in made_up),
               "The engine works with any source of measurements, not only the virtual lab (it was given a made-up one)")
    except Exception as error:  # noqa: BLE001
        record(False, "The engine works with any source of measurements, not only the virtual lab", repr(error))

    # skipped trials
    try:
        skipped = proposals(settings, adaptive(settings), seed, frozenset({19}))
        results = sum(t.measurement is not None for t in skipped)
        record(results == 29 and skipped[18].measurement is None and skipped[7].measurement is not None,
               "A skipped trial (19) is accepted without breaking the engine; trial 8 still gives a result",
               f"{results} results from 30 trials")
        same_as_skipped = skipped[19].formulation == skipped[18].formulation
        record(not same_as_skipped, "The recipe of the skipped trial is not simply proposed again on the next trial")
        harsh = proposals(settings, adaptive(settings), seed, frozenset(range(2, 22)))
        record(len(harsh) == 30 and sum(t.measurement is not None for t in harsh) == 10,
               "Even when 20 of 30 trials are skipped (almost no results to learn from) the engine keeps going",
               "10 results from 30 trials")
        none_at_all = proposals(settings, adaptive(settings), seed, frozenset(range(1, 31)))
        record(len(none_at_all) == 30, "Even with no results at all the engine still proposes recipes")
    except Exception as error:  # noqa: BLE001
        record(False, "A skipped trial does not crash the engine", repr(error))

    # the why
    reasons = [adaptive(settings).propose(t, tuple(m.measurement for m in run[:t - 1] if m.measurement)).reason
               for t in range(1, 31)]
    record(all(len(r) > 40 for r in reasons) and all("Spread-out" in r for r in reasons[:n])
           and all("Estimated chance of passing both specifications" in r for r in reasons[n:]),
           "Every decision comes with a plain-language reason (starting recipes explain the spread; later ones give the chance of passing)")
    record(any("skipped trial" in adaptive(settings).propose(25, tuple(m.measurement for m in run[:24] if m.measurement),
                                                             (run[18].formulation,)).reason for _ in [0]),
           "When trials were skipped, the reason says so")
    return run


# ------------------------------------------------------------------ the comparison
def independent_stat(firsts, trials, pct):
    """The first trial by which `pct`% of campaigns had found one - worked out differently from the real code."""
    need = math.ceil(len(firsts) * pct / 100)
    found = sorted(f for f in firsts if f is not None)
    return found[need - 1] if need <= len(found) else None


def check_comparison(settings, result, label):
    n, trials = settings.comparison.campaigns, settings.comparison.trials_per_campaign
    record(result.campaigns == n and result.trials_per_campaign == trials,
           f"{label}: {n} campaigns of {trials} trials", f"{result.campaigns} x {result.trials_per_campaign}")
    record(result.seeds == [settings.run.random_seed + i for i in range(n)] and len(set(result.seeds)) == n,
           f"{label}: the {n} seeds are the default seed and the {n - 1} after it, fixed in advance",
           f"{result.seeds[0]} ... {result.seeds[-1]}")
    keys = [s.key for s in result.strategies]
    record(keys == ["fixed-list", "adaptive", "random"] and all(len(s.first_truly_good) == n for s in result.strategies),
           f"{label}: fixed list, adaptive and random each ran every one of the {n} campaigns (same seeds, paired)")
    maths_ok = True
    for s in result.strategies:
        for stats, firsts in ((s.truly_good, s.first_truly_good), (s.measured_pass, s.first_measured_pass)):
            maths_ok &= (stats.trial_by_25pct == independent_stat(firsts, trials, 25)
                         and stats.median_trial == independent_stat(firsts, trials, 50)
                         and stats.trial_by_75pct == independent_stat(firsts, trials, 75)
                         and abs(stats.found_pct - 100 * sum(f is not None for f in firsts) / n) < 1e-9
                         and stats.cumulative_pct == sorted(stats.cumulative_pct)
                         and abs(stats.cumulative_pct[-1] - stats.found_pct) < 1e-9)
    record(maths_ok, f"{label}: median, quartiles and found-percentages match a separate recount from the raw campaign results")
    record(result.headline_measure == "truly_good" and "HEADLINE MEASURE" in result.measure_notes[0],
           f"{label}: the headline measure is stated", result.headline_label)
    paired = result.paired[0]
    record(paired.first_earlier + paired.tie + paired.second_earlier + paired.neither_found == n,
           f"{label}: the campaign-by-campaign (paired) tally accounts for all {n} campaigns", paired.sentence)


def check_difficulty(settings, result):
    from cellpoc.comparison.difficulty import LEVELS

    rows = result.difficulty
    record([r.level for r in rows] == ["Harder", "Default", "Easier"],
           "The difficulty table has three levels: harder, default, easier", ", ".join(r.level for r in rows))
    for row, (level, target, _) in zip(rows, LEVELS):
        record(abs(row.good_share_pct / 100 - target) <= max(0.004, 0.25 * target),
               f"Difficulty '{level}': the share of random recipes that are truly good is close to its target",
               f"{row.good_share_pct:.1f}% truly good (target about {target:.0%})")
    default = rows[1]
    adaptive_main = [s for s in result.strategies if s.key == "adaptive"][0].truly_good
    adaptive_row = [s for s in default.strategies if s.label == "Adaptive"][0]
    record(adaptive_row.found_pct == adaptive_main.found_pct and adaptive_row.median_trial == adaptive_main.median_trial,
           "The 'default' difficulty row is the headline comparison itself (same engine, same seeds, no faults)")


def check_pairing_and_scoring(settings):
    lab = VirtualLab(settings, seed=settings.run.random_seed)
    a = Formulation(20, 55, 4, 4.5, 1.1)
    b = Formulation(12, 62, 3, 6, 0.6)
    noise = []
    for f in (a, b):
        m = lab.measure(5, f)
        truth_d, truth_h = oracle.true_properties(f)
        noise.append((round(m.dissolution_pct - truth_d, 9), round(m.hardness_kp - truth_h, 9)))
    record(noise[0] == noise[1], "Paired: for the same seed and trial number every strategy gets the same measurement noise",
           f"noise on trial 5: dissolution {noise[0][0]:+.2f}, hardness {noise[0][1]:+.2f} for two different recipes")

    seed = campaign_seeds(settings)[0]
    for key in ("fixed-list", "adaptive", "random"):
        outcome = run_campaign(VirtualLab(settings, seed=seed), make_strategy(key, settings, seed), 30)
        measured, truly = first_trials(settings, outcome)
        direct_measured = next((t.trial for t in outcome if meets_spec(t.measurement.dissolution_pct, t.measurement.hardness_kp,
                                                                        settings.specifications)), None)
        direct_truly = next((t.trial for t in outcome if oracle.truly_meets_spec(t.formulation, settings)), None)
        record(measured == direct_measured and truly == direct_truly,
               f"The two success measures for campaign 1 ({key}) match a direct re-scoring",
               f"first measured pass: {measured}; first truly good: {truly}")


def check_faults_identical(settings):
    skipped = settings.scripted_faults.skipped_trials
    ok, detail = True, []
    for key in ("fixed-list", "adaptive", "random"):
        outcome = run_campaign(VirtualLab(settings), make_strategy(key, settings, settings.run.random_seed), 30, skipped)
        results = sum(t.measurement is not None for t in outcome)
        ok &= (results == 30 - len(skipped) and all(outcome[t - 1].measurement is None for t in skipped)
               and outcome[7].measurement is not None)
        detail.append(f"{key}: {results} results")
    record(ok, f"With faults, all three strategies lose exactly the same trial(s) {sorted(skipped)} and keep trial 8",
           "; ".join(detail))


# ------------------------------------------------------------------ outputs
def percent(x):
    return f"{x:.0f}%"


def trial_text(t):
    return str(t) if t is not None else "not in 30"


def summary_lines(result):
    trials = result.trials_per_campaign
    lines = [f"{result.campaigns} campaigns of {trials} trials. "
             + ("Scripted faults applied identically to every strategy." if result.faults_applied else "No faults applied."),
             "",
             "HEADLINE MEASURE - first trial whose recipe was truly good (scored after the fact; the engine never sees it)",
             f"{'Strategy':<12}{'25% of campaigns by':>20}{'Median (50%) by':>17}{'75% by':>10}{'Found within ' + str(trials):>18}"]
    for s in result.strategies:
        g = s.truly_good
        lines.append(f"{s.label:<12}{trial_text(g.trial_by_25pct):>20}{trial_text(g.median_trial):>17}"
                     f"{trial_text(g.trial_by_75pct):>10}{percent(g.found_pct):>18}")
    lines += ["", "SECOND MEASURE - first trial measured as passing (what the cell itself could observe)",
              f"{'Strategy':<12}{'25% of campaigns by':>20}{'Median (50%) by':>17}{'75% by':>10}{'Found within ' + str(trials):>18}"]
    for s in result.strategies:
        m = s.measured_pass
        lines.append(f"{s.label:<12}{trial_text(m.trial_by_25pct):>20}{trial_text(m.median_trial):>17}"
                     f"{trial_text(m.trial_by_75pct):>10}{percent(m.found_pct):>18}")
    lines += [""] + [p.sentence for p in result.paired] + [""] + result.measure_notes
    if result.difficulty:
        lines += ["", "SENSITIVITY TO DIFFICULTY - same comparison (no faults, same seeds, same engine) when good recipes are rarer or commoner",
                  f"{'Level':<10}{'Random recipes truly good':>27}{'Strategy':>13}{'Found within ' + str(trials):>18}{'Median trial':>14}"]
        for row in result.difficulty:
            for i, s in enumerate(row.strategies):
                lead = (f"{row.level:<10}{row.good_share_pct:>26.1f}%" if i == 0 else " " * 37)
                lines.append(f"{lead}{s.label:>13}{percent(s.found_pct):>18}{trial_text(s.median_trial):>14}")
    return lines


def write_outputs(settings, demo, demo_faults):
    OUT.mkdir(parents=True, exist_ok=True)
    result = demo.comparison

    (OUT / "comparison_summary.txt").write_text(
        "\n".join(["WITHOUT FAULTS (the headline comparison)", "=" * 60] + summary_lines(result)
                  + ["", "", "WITH SCRIPTED FAULTS", "=" * 60] + summary_lines(demo_faults.comparison)), encoding="utf-8")

    with open(OUT / "campaigns.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        head = ["Campaign", "Seed"]
        for s in result.strategies:
            head += [f"{s.label}: first trial measured passing", f"{s.label}: first trial truly good"]
        writer.writerow(head)
        for i, seed in enumerate(result.seeds):
            row = [i + 1, seed]
            for s in result.strategies:
                row += [s.first_measured_pass[i] or "not found", s.first_truly_good[i] or "not found"]
            writer.writerow(row)

    with open(OUT / "demo_event_log.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["When", "Trial", "Step", "Someone in the lab?", "Event"])
        for e in demo.events:
            writer.writerow([e.when, e.trial or "", e.station or "", "yes" if e.attended else "no", e.message])

    run_store.save(demo, OUT)
    run_store.save(demo_faults, OUT / "with-faults")
    record(run_store.load(OUT) == demo and run_store.load(OUT / "with-faults") == demo_faults,
           "Both run records (with and without faults), comparison included, read back from disk identical",
           "runs\\stage3\\record.json and runs\\stage3\\with-faults\\record.json")

    import altair as alt
    import pandas as pd

    green, font = settings.display.accent_colour, settings.display.font
    colours = alt.Scale(domain=["Adaptive", "Fixed list", "Random"], range=[green, "#404040", "#A0A0A0"])
    panels = []
    for measure, title in (("truly_good", "HEADLINE: first trial whose recipe was truly good"),
                           ("measured_pass", "Second measure: first trial measured as passing")):
        rows = [{"Strategy": s.label, "Trial": t, "% of campaigns that have found one": pct}
                for s in result.strategies for t, pct in enumerate(getattr(s, measure).cumulative_pct, start=1)]
        panels.append(alt.Chart(pd.DataFrame(rows)).mark_line(interpolate="step-after", strokeWidth=3).encode(
            x=alt.X("Trial:Q", scale=alt.Scale(domain=[1, result.trials_per_campaign])),
            y=alt.Y("% of campaigns that have found one:Q", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("Strategy:N", scale=colours), tooltip=["Strategy", "Trial", "% of campaigns that have found one"]
        ).properties(width=480, height=300, title=title))
    chart = (alt.hconcat(*panels).properties(
        title=f"{result.campaigns} campaigns of {result.trials_per_campaign} trials, paired seeds, no faults")
        .configure(font=font).configure_title(font=font, color="#333", fontSize=14))
    write_chart_page(chart, OUT / "comparison.html", settings.display.banner, green, font)
    record((OUT / "comparison.html").exists(), "The comparison chart and summary were written", str(OUT.relative_to(ROOT)))


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as error:
        record(False, "The settings file loads without problems", "\n        ".join(error.problems))
        return checklist.print()

    check_engine(settings)
    check_pairing_and_scoring(settings)
    check_faults_identical(settings)

    small_a, small_b = compare(settings, campaigns=6), compare(settings, campaigns=6)
    record(small_a == small_b, "The same seeds give identical comparison results, down to every number (checked on 6 campaigns)")

    print("Running the full comparison twice (without and with faults); this takes about a minute...", flush=True)
    demo = run_demo(settings, run_id="stage3-adaptive-demo", with_faults=False)   # also runs the difficulty levels
    demo_faults = run_demo(settings, run_id="stage3-adaptive-demo-faults", with_faults=True,
                           difficulty=demo.comparison.difficulty)
    check_difficulty(settings, demo.comparison)
    check_comparison(settings, demo.comparison, "No faults")
    check_comparison(settings, demo_faults.comparison, "With faults")
    record(demo.comparison.skipped_trials == [] and demo_faults.comparison.skipped_trials == sorted(settings.scripted_faults.skipped_trials),
           "The no-fault comparison skips nothing; the with-fault comparison skips exactly the scripted trial(s)",
           f"with faults: trial(s) {demo_faults.comparison.skipped_trials}")
    why = [e.message for e in demo.events if e.kind == "decision"]
    record(len(why) == len(demo.trials) and all("Recipe:" in w and len(w) > 80 for w in why),
           "The demonstration run logs every decision with its reason and recipe", f"{len(why)} decisions")
    record(demo.meta.strategy_name == "adaptive" and demo.summary.trials_with_result == 30,
           "The demonstration run (adaptive, default seed) completed all 30 trials in the simulated cell")

    engine_imports = architecture._imported_parts(ROOT / "cellpoc" / "decision_engine" / "adaptive.py")
    record(engine_imports <= {"contracts", "settings"},
           "The adaptive engine imports only the shared data shapes and settings: no lab, no scoring, no simulator",
           f"it imports: {', '.join(sorted(engine_imports))}")
    architecture.check(checklist)

    write_outputs(settings, demo, demo_faults)
    record_headlines(demo.comparison)
    return checklist.print()


def record_headlines(result):
    by = {s.key: s for s in result.strategies}
    trials = result.trials_per_campaign
    for key in ("adaptive", "fixed-list", "random"):
        g = by[key].truly_good
        checklist.headline(f"{by[key].label:<10} truly-good recipe found within {trials} trials in {g.found_pct:.0f}% of campaigns; "
                           f"median trial: {trial_text(g.median_trial)}")
    checklist.headline(result.paired[0].sentence)
    checklist.headline("Full tables: runs\\stage3\\comparison_summary.txt   (the headline measure is 'truly good', scored after the fact)")


if __name__ == "__main__":
    sys.exit(main())
