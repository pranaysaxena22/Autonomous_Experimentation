"""The 4-4 report: plain words, every scenario, the ones where the governed engine is not clearly better listed first, and an automatic "things that do not look good" section.

It is labelled SYNTHETIC in every heading and says what it does not show. No clock time. The numbers are the ones fixed in advance (docs/decisions.md, "Stage 4-4"): the headline is the number of truly good
recipes among the 30 trials; the verdict is 'better' / 'worse' / 'no clear difference' from the 95% interval of the paired difference; stated chances are checked against what was truly met.
"""
from __future__ import annotations

import numpy as np

from .dev_comparison import (BETTER, COMPARISON_SEEDS, EVENT_TRIAL, NO_CLEAR, SCENARIO_NAMES, STRATEGIES, TRIALS, WORSE, CampaignRecord, paired_difference, reliability, verdict)

LABEL = "SYNTHETIC DATA"
RESULT_NAMES = {"dissolution_30min_pct": "dissolution", "hardness_kp": "hardness", "friability_pct": "friability"}
INTENT = {"baseline": "everything predictable, nothing shifts", "new_supplier": "an unseen supplier takes over from trial 8", "period_shift": "the product truly changes from trial 6, with no sign in the inputs",
          "unpredictable_dissolution": "dissolution is a result Stage 3 would not carry"}
NOT_SHOWN = ["Anything about real tablets or a client: the lab is synthetic, and the engine and the lab were developed together on these four scenarios, so this is a DEVELOPMENT comparison, not a blind test (the blind test is the sealed acceptance run, which has not been run).",
             "Whether the engine would do the same on another kind of world: all four scenarios share one smooth formula family.",
             "Anything about the proof of concept's own strategies: they cannot run in this lab (they model five ingredients and two targets, with no process settings, friability or context), and their own 40-campaign comparison is unchanged.",
             "Why the governed engine is better or worse in a scenario: only that it is, by the rule fixed in advance. The governance rules were not tested one at a time."]


def not_shown(full: str, adopted: bool) -> list:
    """The "what this does not show" bullets; the original wording for the earlier governed engine, plus two plain statements for the adopted engine."""
    out = [x if not x.startswith("Why the governed engine") else f"Why {full} is better or worse in a scenario: only that it is, by the rule fixed in advance. The governance rules were not tested one at a time." for x in NOT_SHOWN]
    if adopted:
        out += ["This comparison is descriptive: no pass or fail bar was set, as in the original 4-4. It describes the ADOPTED engine on fresh seeds; the original 4-4 results describe the engine as it was before the recalibration response was adopted, and the two are not pooled.",
                "The adopted engine is the one the project developed and tested on these scenarios, so this is a development comparison, not evidence from a world it was not built against."]
    return out


def stale_of(rec: CampaignRecord) -> list:
    """Per trial, the targets the watch had marked stale. For the earlier engine that is what its decisions list; the adopted engine lists only the targets that still get the old response, so it also records the watch's own flag."""
    return rec.extra.get("watch_stale", rec.stale)


def first_good(rec: CampaignRecord) -> int | None:
    return next((t for t, g in enumerate(rec.good, 1) if g), None)


def headline(rec: CampaignRecord) -> int:
    return int(sum(rec.good))


def after_event(rec: CampaignRecord) -> int:
    start = EVENT_TRIAL.get(rec.scenario, 1)
    return int(sum(rec.good[start - 1:]))


def _by(records: list) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault((r.scenario, r.strategy), {})[r.seed] = r
    return out


def _paired(a: dict, b: dict, key) -> dict:
    seeds = sorted(set(a) & set(b))
    return paired_difference([key(a[s]) for s in seeds], [key(b[s]) for s in seeds])


def _stated(recs: list) -> dict:
    """Stated chance against what was truly met, for each target and for all targets together."""
    out = {}
    for r in recs:
        for t in range(len(r.good)):
            for k, c in r.chances[t].items():
                outcome = r.good[t] if k == "all_targets" else r.met[t].get(k)
                if outcome is not None:
                    out.setdefault(k, ([], []))
                    out[k][0].append(c)
                    out[k][1].append(float(outcome))
    return {k: reliability(*v) for k, v in out.items()}


def _pct(x) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def build_report(records: list, seconds: float | None = None, engine: str = "governed", seeds=COMPARISON_SEEDS) -> str:
    """`engine` is the strategy under test as named in the records ("governed", the earlier engine, or "recalibrated", the adopted one); `seeds` the seeds of the paired campaigns. The defaults give the original 4-4 report."""
    adopted = engine != "governed"
    short = "recalibrated" if adopted else "governed"
    full = "the adopted (recalibrated) engine" if adopted else "the governed engine"
    Cap = short.capitalize()
    by = _by(records)
    lines = [f"# The development comparison [{LABEL}]: {full} against the same models without the governance, and against random recipes", "",
             f"**This report is {LABEL}** from the development lab. {len(seeds)} paired campaigns of {TRIALS} trials per scenario (seeds {seeds[0]} to {seeds[-1]}); "
             "each campaign gives the three strategies the identical lab day. A recipe is TRULY good when the lab's noise-free results in that trial's own context meet every target; that is how everything is scored.", ""]
    problems, summary = [], []
    sections = []
    for scenario in SCENARIO_NAMES:
        g, u, rnd = by[(scenario, engine)], by[(scenario, "ungoverned")], by[(scenario, "random")]
        vs_u, vs_r = _paired(g, u, headline), _paired(g, rnd, headline)
        vu, vr = verdict(vs_u["lo"], vs_u["hi"]), verdict(vs_r["lo"], vs_r["hi"])
        summary.append((scenario, vs_u, vu, vs_r, vr))
        if vu != BETTER:
            problems.append(f"**{scenario}:** {full} is **{vu}** compared with the same models without the governance (mean difference {vs_u['mean']:+.1f} truly good recipes per campaign, 95% interval {vs_u['lo']:+.1f} to {vs_u['hi']:+.1f}).")
        if vr != BETTER:
            problems.append(f"**{scenario}:** {full} is **{vr}** compared with random recipes (mean difference {vs_r['mean']:+.1f}, 95% interval {vs_r['lo']:+.1f} to {vs_r['hi']:+.1f}).")
        gl = list(g.values())
        stale_trials = sum(1 for r in gl for s in stale_of(r) if s)
        share = stale_trials / (len(gl) * TRIALS)
        if share > 0.25:
            problems.append(f"**{scenario}:** {full} spent {_pct(share)} of its trials with at least one target stale (in {sum(1 for r in gl if any(stale_of(r)))} of {len(gl)} campaigns)." + (" (Counted from the watch itself; the adopted engine re-centres some of these rather than treating them as stale.)" if adopted else ""))
        zero = sum(1 for r in gl if headline(r) == 0)
        if zero:
            problems.append(f"**{scenario}:** {zero} of {len(gl)} {short} campaigns found no truly good recipe at all.")
        sg, su = _stated(gl), _stated(list(u.values()))
        worse = [k for k in sg if k in su and sg[k]["brier"] is not None and su[k]["brier"] is not None and sg[k]["brier"] > su[k]["brier"] + 1e-9]
        if worse:
            problems.append(f"**{scenario}:** {full}'s stated chances are less honest (higher Brier score) than the ungoverned engine's for: {', '.join(RESULT_NAMES.get(k, k) for k in worse)}.")
        sections.append((scenario, g, u, rnd, vs_u, vu, vs_r, vr, sg, su))
    lines += ["## Things that do not look good", ""] + ([f"- {p}" for p in problems] or ["- None found by the rules fixed in advance."]) + [""]
    lines += [f"## The verdicts at a glance [{LABEL}]", "", f"Per scenario, never pooled. The headline is the number of truly good recipes among the 30 trials; the difference is {full} minus the other strategy, campaign by campaign.", "",
              f"| Scenario | {Cap} vs the same models without governance | {Cap} vs random recipes |", "|---|---|---|"]
    for scenario, vs_u, vu, vs_r, vr in summary:
        lines.append(f"| {scenario} | **{vu}** ({vs_u['mean']:+.1f}; {vs_u['lo']:+.1f} to {vs_u['hi']:+.1f}; {vs_u['wins']} wins, {vs_u['ties']} ties, {vs_u['losses']} losses) | "
                     f"**{vr}** ({vs_r['mean']:+.1f}; {vs_r['lo']:+.1f} to {vs_r['hi']:+.1f}; {vs_r['wins']} wins, {vs_r['ties']} ties, {vs_r['losses']} losses) |")
    lines += [""]
    for scenario, g, u, rnd, vs_u, vu, vs_r, vr, sg, su in sections:
        lines += [f"## {scenario} [{LABEL}]: {INTENT[scenario]}", "", "| Strategy | Truly good recipes per campaign (min to max) | First truly good trial (campaigns with none) | Truly good after the event | Measurements that met every target |", "|---|---|---|---|---|"]
        for name, recs in ((short, g), ("ungoverned (same models, no governance)", u), ("random recipes", rnd)):
            rs = list(recs.values())
            h = [headline(r) for r in rs]
            f = [first_good(r) for r in rs]
            fg = [x for x in f if x is not None]
            after = f"{np.mean([after_event(r) for r in rs]):.1f}" if scenario in EVENT_TRIAL else "n/a"
            lines.append(f"| {name} | {np.mean(h):.1f} ({min(h)} to {max(h)}) | {np.mean(fg):.1f} ({len(f) - len(fg)}) | {after} | {np.mean([sum(r.measured_pass) for r in rs]):.1f} |" if fg else
                         f"| {name} | {np.mean(h):.1f} ({min(h)} to {max(h)}) | none ({len(f)}) | {after} | {np.mean([sum(r.measured_pass) for r in rs]):.1f} |")
        if scenario in EVENT_TRIAL:
            a = _paired(g, u, after_event)
            lines += ["", f"After the event (from trial {EVENT_TRIAL[scenario]}), {short} minus ungoverned: {a['mean']:+.1f} truly good recipes per campaign (95% interval {a['lo']:+.1f} to {a['hi']:+.1f}): **{verdict(a['lo'], a['hi'])}**."]
        gl = list(g.values())
        kinds: dict = {}
        for r in gl:
            for k in r.kinds:
                kinds[k] = kinds.get(k, 0) + 1
        lines += ["", f"What {full} did (per campaign, on average): " + ", ".join(f"{k.replace('_', ' ')} {v / len(gl):.1f}" for k, v in sorted(kinds.items())) +
                  (f"; trials with a stale target {sum(1 for r in gl for s in stale_of(r) if s) / len(gl):.1f}" if not adopted else
                   f"; trials with a target the watch flagged as stale {sum(1 for r in gl for s in stale_of(r) if s) / len(gl):.1f}, of which trials in which a target still got the earlier response {sum(1 for r in gl for s in r.stale if s) / len(gl):.1f} (the earlier engine's report counted only the second kind, which for it was the same thing: the adopted engine removes the targets it re-centres or finds working from the second count before the earlier response is applied to them, so the two engines' stale-trial numbers are NOT the same population)") + f"; picks warned by a per-recipe check {sum(sum(r.warned) for r in gl) / len(gl):.1f}.", "",
                  f"**Are the stated chances honest?** For each target a strategy models, the chance it stated against how often that target was truly met (the Brier score is lower for more honest chances):", "",
                  f"| Chance stated for | {Cap}: Brier (trials) | Ungoverned: Brier (trials) |", "|---|---|---|"]
        for k in sorted(set(sg) | set(su)):
            cell = lambda d: "not stated" if k not in d else f"{d[k]['brier']:.3f} ({d[k]['n']:,})"
            lines.append(f"| {RESULT_NAMES.get(k, 'all targets together')} | {cell(sg)} | {cell(su)} |")
        for k, label, table in (("all_targets", short, sg), ("all_targets", "ungoverned", su)):
            if k in table:
                lines += ["", f"Reliability of the {label} engine's chance of meeting ALL targets: " + "; ".join(f"stated {b['bin']}: truly good {_pct(b['met'])} of {b['n']:,}" for b in table[k]["bins"] if b["n"]) + "."]
        if adopted and gl and all("recal" in r.extra for r in gl):
            fired = sum(1 for r in gl if any(r.extra["watch_stale"]))
            classes: dict = {}
            gate = 0
            for r in gl:
                for rc in r.extra["recal"]:
                    gate += rc["gate"] == "fallback"
                    for c in rc["classes"].values():
                        classes[c] = classes.get(c, 0) + 1
            lines += [f"What the watch and the recalibration did: the watch fired in {fired} of {len(gl)} campaigns; at stale decisions the evidence was classed (one count per stale target per decision) " + (", ".join(f"{k} {v}" for k, v in sorted(classes.items())) or "never") +
                      f"; the promise check sent {gate} decisions back to the earlier response.", ""]
        lines += [""]
    lines += [f"## What this does not show [{LABEL}]", ""] + [f"- {x}" for x in not_shown(full, adopted)]
    if seconds is not None:
        lines += ["", f"(The whole comparison took {seconds / 60:.0f} minutes of computing.)"]
    return "\n".join(lines) + "\n"
