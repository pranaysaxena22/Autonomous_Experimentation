"""Stage 1 health check: settings, scenario page and virtual lab.

Prints a PASS/FAIL list in plain words and writes files you can open:
  docs/scenario.md                  the one-page scenario
  runs/stage1/lab_measurements.csv  200 sample recipes, truth vs measured (open in Excel)
  runs/stage1/lab_report.html       charts (open in a browser)
"""
from __future__ import annotations

import copy
import csv
import random
import statistics
import sys
from datetime import timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.contracts import Formulation, meets_spec  # noqa: E402
from cellpoc.settings import DEFAULT_PATH, SettingsError, load_settings, settings_from_dict  # noqa: E402
from cellpoc.virtual_lab import VirtualLab  # noqa: E402
from cellpoc.virtual_lab import oracle  # noqa: E402
from checks import scenario_page  # noqa: E402

OUT = ROOT / "runs" / "stage1"
results: list[tuple[str, str, str]] = []
PASS_SHARE: list[float] = []


def record(ok: bool, what: str, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", what, detail))


def skip(what: str, detail: str) -> None:
    results.append(("SKIP", what, detail))


# ---------------------------------------------------------------- settings
def check_settings():
    try:
        settings = load_settings()
    except SettingsError as error:
        record(False, "The settings file loads without problems", "\n        ".join(error.problems))
        return None
    record(True, "The settings file loads without problems", str(DEFAULT_PATH.relative_to(ROOT)))

    s = settings
    end = s.run.start + timedelta(hours=s.run.duration_hours)
    record(s.run.start.weekday() == 4 and (s.run.start.hour, s.run.start.minute) == (18, 0),
           "The run starts on a Friday at 18:00", f"{s.run.start:%A %d %B %Y %H:%M}")
    record(end.weekday() == 2 and end.hour == 18,
           "The 120-hour run ends on Wednesday at 18:00", f"{end:%A %d %B %Y %H:%M}")
    unattended, total = scenario_page.unattended_hours(s)
    record(abs(unattended - 100) < 0.01, "The cell is unattended for 100 of the 120 hours (staff on Mon + Tue 08:00-18:00)",
           f"unattended {unattended:g} h of {total:g} h")
    per_trial = s.cell.minutes_per_trial
    record(per_trial == 240, "One trial takes 4 hours (30 + 45 + 30 + 75 + 60 minutes)", f"{per_trial:g} minutes")
    record(int(s.run.duration_hours * 60 // per_trial) == s.comparison.trials_per_campaign,
           "Running one trial at a time, 120 hours fits exactly the 30 trials in a campaign",
           f"{s.run.duration_hours * 60 / per_trial:g} trials fit; campaign size is {s.comparison.trials_per_campaign}")
    faults = s.scripted_faults
    record([e.trial for e in faults.events] == [8, 19]
           and [e.retry_succeeds for e in faults.events] == [True, False]
           and all(e.station == "dispense" for e in faults.events)
           and faults.purge_minutes == 60,
           "Scripted faults: both at the dispense step (binder clog); trial 8 recovers after a 1-hour purge, trial 19 fails its retry",
           f"purge {faults.purge_minutes:g} min")
    record(s.comparison.manual_baseline_trials_per_week == 9, "The manual baseline is 9 trials per week",
           f"{s.comparison.manual_baseline_trials_per_week:g}")
    return settings


def check_bad_settings_are_explained():
    """Break the settings on purpose, several ways, and confirm each gets a plain-English message."""
    good = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))

    def broken(mutate):
        raw = copy.deepcopy(good)
        mutate(raw)
        try:
            settings_from_dict(raw)
        except SettingsError as error:
            return " | ".join(error.problems)
        return ""

    cases = [
        ("a negative step duration", lambda r: r["cell"]["steps"][1].update(duration_minutes=-45), "greater than zero"),
        ("an ingredient whose min is above its max", lambda r: r["design_space"]["ingredients"]["binder"].update(min=9), "smaller than max"),
        ("text where a number should be", lambda r: r["design_space"]["ingredients"]["drug"].update(max="lots"), "expected a number"),
        ("a staffed day that is not a day", lambda r: r["people"].update(staffed_days=["Mon", "Funday"]), "not a day"),
        ("a fault on a step that does not exist", lambda r: r["scripted_faults"]["events"][0].update(station="polish"), "not one of the cell steps"),
        ("a fault on trial 99 of a 30-trial campaign", lambda r: r["scripted_faults"]["events"][0].update(trial=99), "beyond the 30 trials"),
        ("a missing ingredient", lambda r: r["design_space"]["ingredients"].pop("binder"), "'binder' is missing"),
        ("a start date written the wrong way", lambda r: r["run"].update(start="Friday evening"), "not a date and time"),
    ]
    for name, mutate, expected in cases:
        message = broken(mutate)
        record(expected in message, f"Settings with {name} are rejected with a clear message",
               message if message else "NOT rejected - the mistake was silently accepted")
    try:
        settings_from_dict(good)
        record(True, "The checker does not complain about the untouched settings")
    except SettingsError as error:
        record(False, "The checker does not complain about the untouched settings", str(error))


# ---------------------------------------------------------------- lab
def check_lab(settings):
    ing = settings.design_space.ingredients
    rng = random.Random(123)
    recipes = [oracle.random_formulation(settings, rng) for _ in range(20)]

    lab_a, lab_b = VirtualLab(settings), VirtualLab(settings)
    same = all(lab_a.measure(i, f) == lab_b.measure(i, f) for i, f in enumerate(recipes))
    record(same, "Same seed gives identical measurements every time")
    other = VirtualLab(settings, seed=settings.run.random_seed + 1)
    differs = any(lab_a.measure(i, f) != other.measure(i, f) for i, f in enumerate(recipes))
    record(differs, "A different seed gives different measurements")

    first = lab_a.measure(5, recipes[0])
    lab_a.measure(3, recipes[1])
    record(first == VirtualLab(settings).measure(5, recipes[0]),
           "A trial's measurement does not depend on what was measured before it")

    best, best_margin = oracle.true_best(settings)
    readings = [VirtualLab(settings).measure(i, best) for i in range(400)]
    sd_d = statistics.stdev(r.dissolution_pct for r in readings)
    sd_h = statistics.stdev(r.hardness_kp for r in readings)
    want_d, want_h = settings.noise.dissolution_sd, settings.noise.hardness_sd
    record(abs(sd_d - want_d) < 0.2 * want_d and abs(sd_h - want_h) < 0.2 * want_h,
           "Repeating one recipe 400 times scatters by the amount set in the settings",
           f"dissolution scatter {sd_d:.2f} (setting {want_d}), hardness scatter {sd_h:.2f} (setting {want_h})")

    passing = sum(meets_spec(r.dissolution_pct, r.hardness_kp, settings.specifications) for r in readings) / len(readings)
    record(passing >= 0.9, "The best recipe passes the specification in almost every measurement",
           f"{passing:.0%} of 400 measurements pass")
    bad = Formulation(drug=30, filler=40, binder=6, disintegrant=1, lubricant=2)
    bad_readings = [VirtualLab(settings).measure(i, bad) for i in range(100)]
    bad_passing = sum(meets_spec(r.dissolution_pct, r.hardness_kp, settings.specifications) for r in bad_readings)
    record(bad_passing == 0, "A deliberately poor recipe (high binder, little disintegrant, lots of lubricant) never passes",
           f"{bad_passing} of 100 pass; typical dissolution {statistics.mean(r.dissolution_pct for r in bad_readings):.0f}%")

    fraction = oracle.feasible_fraction(settings)
    record(0.02 <= fraction <= 0.05, "The good region is rare: between 2% and 5% of random recipes are truly good",
           f"{fraction:.1%} of random recipes are truly good")
    PASS_SHARE.append(fraction)

    try:
        VirtualLab(settings).measure(1, Formulation(drug=50, filler=55, binder=4, disintegrant=4, lubricant=1))
        record(False, "A recipe outside the allowed ranges is refused")
    except ValueError as error:
        record("outside the allowed range" in str(error), "A recipe outside the allowed ranges is refused", str(error))

    return recipes, best, best_margin, fraction


def check_truth_boundary():
    """The decision engine and dashboard must never touch the lab's hidden truth or the scoring oracle."""
    package = ROOT / "cellpoc"
    leaks, scanned = [], 0
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(package)
        part = rel.parts[0]
        if part == "virtual_lab":
            continue
        scanned += 1
        if "_truth" in text or "virtual_lab.oracle" in text or "import oracle" in text:
            leaks.append(f"{rel} reaches the hidden truth")
        if part in ("decision_engine", "dashboard") and "virtual_lab" in text:
            leaks.append(f"{rel} imports the virtual lab")
    record(not leaks, "Nothing outside the virtual lab can see the hidden truth",
           "; ".join(leaks) if leaks else f"{scanned} source files outside the lab scanned")
    missing = [p for p in ("decision_engine", "dashboard") if not (package / p).exists()]
    if missing:
        skip("The decision engine and dashboard never import the virtual lab",
             f"{' and '.join(missing)} not built yet; this check starts guarding them when they exist")


# ---------------------------------------------------------------- files to look at
def write_files(settings, recipes, best, best_margin):
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    lab = VirtualLab(settings)
    rows = []
    for n in range(1, 201):
        f = oracle.random_formulation(settings, rng)
        true_d, true_h = oracle.true_properties(f)
        m = lab.measure(n, f)
        rows.append({
            **{i.label + " %": round(getattr(f, i.key), 2) for i in settings.design_space.ingredients},
            "True dissolution %": round(true_d, 1), "Measured dissolution %": round(m.dissolution_pct, 1),
            "True hardness kP": round(true_h, 2), "Measured hardness kP": round(m.hardness_kp, 2),
            "Truly good?": "yes" if oracle.truly_meets_spec(f, settings) else "no",
            "Measured good?": "yes" if meets_spec(m.dissolution_pct, m.hardness_kp, settings.specifications) else "no",
        })
    with open(OUT / "lab_measurements.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    import altair as alt
    import pandas as pd

    green, grey, font = settings.display.accent_colour, "#A0A0A0", settings.display.font
    spec = settings.specifications
    df = pd.DataFrame(rows)
    df["Result"] = df["Measured good?"].map({"yes": "Measured good", "no": "Measured not good"})
    box = pd.DataFrame([{"x0": spec.hardness.minimum, "x1": spec.hardness.maximum, "y0": spec.dissolution.minimum, "y1": 100}])
    colours = alt.Scale(domain=["Measured good", "Measured not good"], range=[green, grey])
    zone = alt.Chart(box).mark_rect(opacity=0.15, color=green).encode(
        x="x0:Q", x2="x1:Q", y="y0:Q", y2="y1:Q")
    scatter = alt.Chart(df).mark_circle(size=60, opacity=0.8).encode(
        x=alt.X("Measured hardness kP:Q", scale=alt.Scale(zero=False)),
        y=alt.Y("Measured dissolution %:Q", scale=alt.Scale(zero=False)),
        color=alt.Color("Result:N", scale=colours),
        tooltip=list(rows[0]))
    chart1 = (zone + scatter).properties(
        width=520, height=340, title="200 random recipes: green box = meets specification")

    chart2 = alt.Chart(df).mark_circle(size=50, opacity=0.7, color=green).encode(
        x=alt.X("True dissolution %:Q", scale=alt.Scale(zero=False)),
        y=alt.Y("Measured dissolution %:Q", scale=alt.Scale(zero=False)),
        tooltip=["True dissolution %", "Measured dissolution %"])
    diagonal = alt.Chart(pd.DataFrame({"v": [df["True dissolution %"].min(), df["True dissolution %"].max()]})).mark_line(
        color="#555", strokeDash=[4, 4]).encode(x="v:Q", y="v:Q")
    chart2 = (diagonal + chart2).properties(
        width=250, height=250, title="Dissolution: hidden truth (across) vs measured (up). Dashed = no noise")

    readings = pd.DataFrame([{"Dissolution %": r.dissolution_pct, "Hardness kP": r.hardness_kp}
                             for r in (VirtualLab(settings).measure(i, best) for i in range(400))])
    chart3 = alt.Chart(readings).mark_circle(size=25, opacity=0.5, color=green).encode(
        x=alt.X("Hardness kP:Q", scale=alt.Scale(zero=False)),
        y=alt.Y("Dissolution %:Q", scale=alt.Scale(zero=False))).properties(
        width=250, height=250, title="The best recipe measured 400 times: the scatter is noise")

    page = (alt.vconcat(chart1, alt.hconcat(chart2, chart3)).configure(font=font)
            .configure_title(font=font, color="#333", fontSize=14))
    html_path = OUT / "lab_report.html"
    page.save(str(html_path))
    banner = (f'<div style="font-family:\'{font}\',Arial,sans-serif;background:{green};color:#000;padding:10px 16px;'
              f'font-weight:600">{settings.display.banner}</div>')
    html = html_path.read_text(encoding="utf-8").replace("<body>", "<body>" + banner, 1)
    html_path.write_text(html, encoding="utf-8")


def main() -> int:
    settings = check_settings()
    check_bad_settings_are_explained()
    if settings is None:
        print_report()
        return 1
    recipes, best, best_margin, fraction = check_lab(settings)
    check_truth_boundary()
    page = scenario_page.write(settings)
    record(page.exists(), "The scenario page was written", str(page.relative_to(ROOT)))
    write_files(settings, recipes, best, best_margin)
    record((OUT / "lab_report.html").exists() and (OUT / "lab_measurements.csv").exists(),
           "The lab report and the measurements spreadsheet were written", str(OUT.relative_to(ROOT)))
    return print_report()


def print_report() -> int:
    print()
    print("STAGE 1 CHECK - settings, scenario page, virtual lab")
    print("=" * 60)
    for status, what, detail in results:
        print(f"[{status}] {what}")
        if detail:
            print(f"        {detail}")
    if PASS_SHARE:
        print(f"HEADLINE: {PASS_SHARE[0]:.1%} of random recipes are truly good (target: about 3%, allowed 2%-5%)")
        print("-" * 60)
    failed = sum(1 for status, _, _ in results if status == "FAIL")
    passed = sum(1 for status, _, _ in results if status == "PASS")
    print("=" * 60)
    print(f"{passed} passed, {failed} failed." + ("  ALL GOOD." if not failed else "  SOMETHING NEEDS ATTENTION."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
