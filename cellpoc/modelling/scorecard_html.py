"""The scorecard pages (Stage 3b-4): one stand-alone page per table and an index. Plain HTML and CSS only: no script, no web address, no library, so every page opens with no internet.

Look: Deloitte palette only (green first; dark grey, blue and the light tints), Open Sans with an Arial fallback, green never used for small text on white (it is used for fills with black text).
Two things must never be told apart by colour alone, so each has its own border style, marker and label as well:
  - a result's status: CARRIED (solid green bar), CARRIED BUT EXPLORATORY (dashed blue outline, hatched, labelled) and NOT ASSESSED (dotted grey);
  - the reading for a kind of shift: PICKS OUT THE LARGE ERRORS (solid green, a reliable reading), MIXED (double blue border, weak but positive), CANNOT BE JUDGED (dotted grey, not enough data)
    and DOES NOT (solid dark, clearly negative). Only the first is reliable; the page says so.
The page order is fixed: data-status banner, the unifying statement, the safeguard panel (the warning is the main safeguard), the per-shift readings, the test-data limitation (synthetic tables),
then the results by status, the replay, and what this does not show.
"""
from __future__ import annotations

import html

from .carry import BORDERLINE, CARRIED, SKIPPED
from .calibration import HONEST_BAND
from .domain_report import SAFEGUARD
from .findings import NO_REPLAY_SENTENCE, UNIFYING_STATEMENT
from .replay import MIN_WARNED
from .replay_report import LIMITS as REPLAY_LIMITS
from .scorecard import RELIABLE_WORDS, WORD_CANNOT, WORD_DOES_NOT, WORD_MIXED, WORD_PICKS, TableCard
from .scorecard import ResultCard, ShiftReading

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#FFFFFF;color:#282728;font-family:'Open Sans',Arial,sans-serif;font-size:15px;line-height:1.5}
.top{background:#282728;color:#FFFFFF;padding:14px 24px;border-bottom:6px solid #86BC25;font-weight:600}
.status{padding:10px 24px;font-weight:700;color:#000000}
.status-synthetic{background:#A0DCFF}
.status-real{background:#E8A317}
.status-other{background:#E2E2E2}
.status .tagline{display:block;font-weight:600;margin-top:2px}
main{max-width:1120px;margin:0 auto;padding:8px 24px 48px}
h1{font-size:26px;margin:24px 0 6px}
h2{font-size:20px;margin:30px 0 10px;border-bottom:2px solid #E2E2E2;padding-bottom:4px}
h3{font-size:17px;margin:0 0 6px}
p{margin:6px 0}
.panel{border:2px solid #282728;padding:14px 18px;margin:16px 0;background:#F5F5F5}
.unify{background:#282728;color:#FFFFFF;border:0;border-left:10px solid #86EB22;font-size:19px;font-weight:700}
.safeguard{border-left:10px solid #000000;background:#FFFFFF}
.limit{border:2px dashed #555555;background:#FFFFFF}
.statuses{margin:8px 0 0;padding-left:20px}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;margin:8px 0 12px;font-size:14px}
th,td{border:1px solid #E2E2E2;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#F5F5F5}
.nums{margin:0;padding-left:16px}
.badge{display:inline-block;padding:3px 10px;font-weight:700;color:#000000}
.read-picks{background:#86BC25;border:2px solid #86BC25}
.read-mixed{background:#A0DCFF;border:3px double #005587}
.read-cannot{background:#FFFFFF;color:#555555;border:2px dotted #555555}
.read-does-not{background:#282728;color:#FFFFFF;border:2px solid #000000}
.key{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
.key div{flex:1 1 230px}
.card{margin:14px 0;padding:12px 16px}
.card-carried{border:1px solid #E2E2E2;border-left:10px solid #86BC25;background:#FFFFFF}
.card-exploratory{border:3px dashed #00A3E0;background:repeating-linear-gradient(45deg,#FFFFFF,#FFFFFF 10px,#F5F5F5 10px,#F5F5F5 20px)}
.card-skipped{border:2px dotted #555555;background:#F5F5F5;color:#555555}
.chip{display:inline-block;padding:2px 8px;font-size:12px;font-weight:700;margin-right:8px;color:#000000}
.chip-carried{background:#86BC25}
.chip-exploratory{background:#00A3E0}
.chip-skipped{background:#E2E2E2;border:1px dotted #555555}
.bar{display:inline-block;height:10px;background:#86BC25;vertical-align:middle}
.barbox{display:inline-block;width:120px;background:#E6E6E6;vertical-align:middle;margin-right:6px}
.fixed{border-left:6px solid #005587;padding-left:10px;margin:8px 0;font-weight:600}
small,.muted{color:#555555}
a{color:#005587}
"""

STYLE = {WORD_PICKS: ("read-picks", "▲"), WORD_MIXED: ("read-mixed", "◐"), WORD_CANNOT: ("read-cannot", "?"), WORD_DOES_NOT: ("read-does-not", "✕")}
MEANING = {WORD_PICKS: "Reliable: the lift is above 1 (better than chance) in every result.",
           WORD_MIXED: "Weak but positive: the lift is above 1 in some results and not in others. Not reliable.",
           WORD_CANNOT: f"Not enough data: a result had fewer than {MIN_WARNED} warned rows, so no reading is given. Not reliable.",
           WORD_DOES_NOT: "Clearly negative: the lift is 1 or below in every result. Not reliable."}
CARD = {CARRIED: ("card-carried", "chip-carried", "CARRIED"), BORDERLINE: ("card-exploratory", "chip-exploratory", "CARRIED BUT EXPLORATORY"), SKIPPED: ("card-skipped", "chip-skipped", "NOT ASSESSED")}
FOUR = [("(1) Per recipe, distance", "far from the training recipes"), ("(2) Per recipe, numeric range", "a numeric input outside the range seen in training"),
        ("(3) Per recipe, unseen supplier or product", "a supplier or product value the model never saw (named)"), ("(4) Whole group", "this whole batch, supplier or time period looks unfamiliar")]
NOT_SHOWN = ["Anything about real tablets or a client. Synthetic pages are made-up data; the real-data pages are public data and are not client data.",
             "Whether a model is good enough to act on: that is for a formulation expert to judge, with real data.",
             "Anything for a result that was not carried: those are listed as not assessed, with the reason, and carry no number.",
             "How the warnings behave under a real supplier change or real drift in the recipes: the synthetic tables cannot show it (see the test-data limitation)."]


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def num(x, digits: int = 2) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def pct(x) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def points(x: float) -> str:
    return f"{100 * x:+.1f}"


def _page(title: str, body: str) -> str:
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body>\n{body}\n</body></html>\n")


def _banner(label: str, synthetic: bool, tag: str) -> str:
    kind = "status-synthetic" if synthetic else "status-real" if "REAL" in label.upper() else "status-other"
    extra = f'<span class="tagline">{esc(tag)}</span>' if tag else ""
    return f'<div class="top">Model scorecard (Stage 3b)</div><div class="status {kind}">{esc(label)}{extra}</div>'


def unifying_panel() -> str:
    return f'<div class="panel unify">{esc(UNIFYING_STATEMENT)}</div>'


def safeguard_panel() -> str:
    items = "".join(f"<li><b>{esc(a)}:</b> {esc(b)}</li>" for a, b in FOUR)
    return (f'<div class="panel safeguard"><h2 style="border:0;margin:0 0 6px">The warning is the main safeguard</h2><p>{esc(SAFEGUARD.replace("**", ""))}</p>'
            f'<p>Four separate warning statuses, none folded into another (there is no combined flag):</p><ul class="statuses">{items}</ul></div>')


def reading_key() -> str:
    cells = "".join(f'<div><span class="badge {STYLE[w][0]}">{STYLE[w][1]} {esc(w)}</span><br><small>{esc(MEANING[w])}</small></div>' for w in (WORD_PICKS, WORD_MIXED, WORD_CANNOT, WORD_DOES_NOT))
    return f'<div class="key">{cells}</div>'


def badge(word: str) -> str:
    css, mark = STYLE[word]
    return f'<span class="badge {css}" data-reading="{esc(word)}">{mark} {esc(word)}</span>'


def readings_section(readings: list[ShiftReading]) -> str:
    if not readings:
        return '<h2>Can the warning be trusted, and for which kind of shift?</h2><p>No result on this page was carried, so there is nothing to read.</p>'
    rows = []
    for r in readings:
        nums = "".join(f"<li><b>{esc(n.label)}:</b> {n.rows} rows warned, lift {num(n.lift)}, error ratio {num(n.ratio)}</li>" for n in r.results)
        rows.append(f'<tr data-kind="{esc(r.kind)}"><td>{esc(r.heading)}</td><td>{badge(r.word)}</td><td><ul class="nums">{nums}</ul></td><td>{esc(r.group_text) or "-"}</td></tr>')
    return ('<h2>Can the warning be trusted, and for which kind of shift?</h2>'
            f'<p>The per-recipe distance warning, judged for each result separately (never averaged) and for each kind of shift. A reading is <b>reliable only when it says "{esc(RELIABLE_WORDS[0])}"</b>; '
            'the other three are all not reliable, and they are three different findings. The word is never shown without each result\'s own numbers: lift is the share of the 10% largest errors that were warned, divided by the share warned overall '
            '(above 1 beats chance); error ratio is the average error of warned rows over that of unwarned rows.</p>'
            f'{reading_key()}<div class="wrap"><table><tr><th>Kind of shift</th><th>Reading</th><th>Each result: rows warned, lift, error ratio</th><th>(4) Whole-group warning for the same shift</th></tr>{"".join(rows)}</table></div>')


def limitation_panel(card: TableCard) -> str:
    if not card.synthetic:
        return ""
    share = ""
    if card.supplier_share is not None:
        real = f"{100 * card.real_supplier_share:.0f}%" if card.real_supplier_share is not None else "a far larger share"
        share = f" (here the supplier explains at most {100 * card.supplier_share:.1f}% of an input's spread, against {real} on the real batch data)"
    drift = ""
    if card.replay is not None and card.replay.movement.drift is not None:
        drift = f" The same gap applies to later dates: the largest rank correlation of any input with the date is {card.replay.movement.drift:.2f}, so a good later-dates reading here is the easy case."
    return ('<div class="panel limit"><h2 style="border:0;margin:0 0 6px">Known limitation of the test data itself</h2>'
            f'<p>In these synthetic tables a supplier changes the measured result but barely touches the recipe\'s inputs{esc(share)}. So they <b>cannot validate how the distance check behaves under a supplier shift</b>. '
            f'"Cannot be judged" for suppliers on this page is <b>a gap in the design of the synthetic test, not a neutral or a passing result</b>.{esc(drift)}</p>'
            '<p>This is a limit of the test data (the fixtures) themselves. It is separate from the general statement that the method has been shown on synthetic data; closing it would need a test generator in which a supplier or a period changes the recipes\' inputs.</p></div>')


def _accuracy(r: ResultCard) -> str:
    rows = "".join(f"<tr><td>{esc(a.heading)}</td><td>{num(a.chosen)}</td><td>{num(a.mean)}</td><td>{num(a.nearest)}</td></tr>" for a in r.accuracy)
    return ('<p><b>How well it predicts groups it never saw.</b> Error divided by the result\'s spread (1.0 is no better than guessing the average; smaller is better).</p>'
            f'<div class="wrap"><table><tr><th>Hold-out</th><th>Chosen model</th><th>Training average</th><th>Nearest-neighbour lookup</th></tr>{rows}</table></div>')


def _calibration(r: ResultCard) -> str:
    rows = []
    for c in r.calibration:
        ci = f" [{c.ci[0]:.2f} to {c.ci[1]:.2f}]" if c.ci else f" [no error bar: {c.n_groups} groups]"
        bar = f'<span class="barbox"><span class="bar" style="width:{max(0, min(100, round(100 * c.hit)))}%"></span></span>'
        after = "could not be recalibrated" if c.recal_hit is None else f"{c.recal_hit:.2f} ({esc(c.moved)})"
        rows.append(f"<tr><td>{esc(c.heading)}</td><td>{bar}{c.hit:.2f}{ci}</td><td>{after}</td></tr>")
    after_word = "n/a" if r.verdict_after is None else r.verdict_after
    return (f'<p><b>Is its stated 90% range honest?</b> About 0.90 is honest (the honest band is {HONEST_BAND[0]:.2f} to {HONEST_BAND[1]:.2f} in every hold-out type). As stated: <b>{esc(r.verdict)}</b>; after recalibration: <b>{esc(after_word)}</b>. '
            f'Recalibration learned from other batches does not reliably carry over to a new supplier or a later month. Knows when it is unsure: {esc(r.unsure)}.</p>'
            f'<div class="wrap"><table><tr><th>Hold-out</th><th>How often the range contained the truth</th><th>After recalibration</th></tr>{"".join(rows)}</table></div>')


def _warnings(r: ResultCard) -> str:
    rows = []
    for w in r.warnings:
        rows.append(f"<tr><td>{esc(w.heading)}</td><td>{pct(w.distance[0])} (error ratio {num(w.distance[1])}, lift {num(w.distance[2])})</td>"
                    f"<td>{pct(w.range_[0])} (error ratio {num(w.range_[1])}, lift {num(w.range_[2])})</td><td>{pct(w.category_share)}; {esc(w.unseen)}</td><td>{esc(w.group_text) or '-'}</td></tr>")
    return ('<p><b>The four warning statuses, each on its own.</b> Shares are of the held-out rows (or groups) warned.</p>'
            '<div class="wrap"><table><tr><th>Hold-out</th><th>(1) Distance</th><th>(2) Numeric range</th><th>(3) Unseen supplier or product</th><th>(4) Whole group</th></tr>'
            f'{"".join(rows)}</table></div>')


def result_card(r: ResultCard, table_tag: str) -> str:
    box, chip, word = CARD[r.status]
    tag = " ".join(t for t in (table_tag, r.tag) if t)
    head = f'<h3><span class="chip {chip}">{word}</span>{esc(r.label)}</h3>' + (f'<p><b>{esc(tag)}</b></p>' if tag else "")
    if r.status == SKIPPED:
        body = f"<p>{esc(r.reason)}</p><p><small>No numbers are given for a result that was not assessed.</small></p>"
    else:
        body = (f"<p>Chosen model: <b>{esc(r.model)}</b> (worst hold-out error {num(r.worst)} of the spread). {esc(r.why)}</p>"
                + (f"<p>{esc(r.derived_note)}</p>" if r.derived_note else "") + _accuracy(r) + _calibration(r) + _warnings(r)
                + (f'<p class="fixed">{esc(r.replay_sentence)}</p>' if r.replay_sentence else ""))
    return f'<section class="card {box}" data-status="{r.status}">{head}{body}</section>'


def replay_section(card: TableCard) -> str:
    rep = card.replay
    if rep is None or not rep.targets:
        return ""
    rows = []
    for t in rep.targets:
        s = t.summary
        ci = "-" if not s.interval else f"{points(s.interval[0])} to {points(s.interval[1])}"
        css = "card-exploratory" if t.exploratory else ""
        rows.append(f'<tr class="{css}" data-status="{"borderline" if t.exploratory else "carried"}"><td>{esc(t.heading)}</td><td>{100 * s.picked_rate:.1f}%</td><td>{100 * s.random_rate:.1f}%</td><td>{100 * s.perfect_rate:.1f}%</td>'
                    f'<td>{"-" if s.captured is None else f"{s.captured:.2f}"}</td><td>{esc(ci)}</td><td><b>{esc(s.verdict)}</b></td></tr>')
    most = max((w.warned, t.summary.picks) for t in rep.targets for w in t.warned.values())
    return ('<h2>Decision-usefulness replay (synthetic data only)</h2>'
            '<p>Had a model been used to choose which recipes to run next in each later period, using only data from before it? The top 10% of each window were picked and compared with picking at random and with a perfect ranking. '
            'An EXPLORATORY row includes a borderline result.</p>'
            f'<div class="wrap"><table><tr><th>Target</th><th>Picked passed</th><th>Random would pass</th><th>Perfect would pass</th><th>Captured share</th><th>95% interval for the gain (points)</th><th>Verdict</th></tr>{"".join(rows)}</table></div>'
            f'<p><b>Did warned picks do worse?</b> Not answerable here: at most {most[0]} of {most[1]} picks were warned by any one status, fewer than the {MIN_WARNED} needed.</p>'
            f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in REPLAY_LIMITS)}</ul>')


def render_table(card: TableCard) -> str:
    sections = []
    for status, title in ((CARRIED, "Carried results"), (BORDERLINE, "Carried but exploratory results (borderline)"), (SKIPPED, "Not assessed")):
        group = card.by_status(status)
        if group:
            sections.append(f"<h2>{title}</h2>" + "".join(result_card(r, card.tag) for r in group))
    body = (_banner(card.label, card.synthetic, card.tag) + f'<main><h1>Scorecard: {esc(card.name)} [{esc(card.label)}]</h1>'
            f'<p>One page for one table. Every number is read from the saved model comparison; nothing here is a prediction about real tablets or a client. <a href="index.html">All tables</a></p>'
            + unifying_panel() + safeguard_panel() + readings_section(card.readings) + limitation_panel(card) + "".join(sections) + replay_section(card)
            + '<h2>What this does not show</h2><ul>' + "".join(f"<li>{esc(x)}</li>" for x in NOT_SHOWN) + "</ul></main>")
    return _page(f"Scorecard: {card.name} [{card.label}]", body)


def render_index(cards: list[TableCard], files: dict[str, str]) -> str:
    rows = []
    for c in cards:
        n = {s: len(c.by_status(s)) for s in (CARRIED, BORDERLINE, SKIPPED)}
        rows.append(f'<tr><td><a href="{esc(files[c.name])}">{esc(c.name)}</a></td><td>{esc(c.label)}</td><td>{esc(c.tag) or "-"}</td>'
                    f'<td>{n[CARRIED]}</td><td>{n[BORDERLINE]}</td><td>{n[SKIPPED]}</td></tr>')
    legend = ('<div class="key"><div><span class="chip chip-carried">CARRIED</span><br><small>Strong enough to be calibrated and warned about (solid green bar).</small></div>'
              '<div><span class="chip chip-exploratory">CARRIED BUT EXPLORATORY</span><br><small>Borderline: shown for information, never part of the main findings (dashed blue outline, hatched).</small></div>'
              '<div><span class="chip chip-skipped">NOT ASSESSED</span><br><small>Not strong enough: listed with the reason and no number (dotted grey).</small></div></div>')
    any_synthetic = any(c.synthetic for c in cards)
    limit = ('<div class="panel limit"><h2 style="border:0;margin:0 0 6px">Known limitation of the test data itself</h2><p>The synthetic tables cannot validate how the distance check behaves under a supplier shift, '
             'or under drift in the recipes over time: there, a supplier changes the measured result but barely touches the recipe\'s inputs. "Cannot be judged" on a synthetic page is a gap in the design of the test, '
             'not a neutral or a passing result.</p></div>') if any_synthetic else ""
    body = (_banner("SCORECARD INDEX: SYNTHETIC DATA and REAL PUBLIC DATA, NOT CLIENT DATA (each page carries its own label)", False, "") + '<main><h1>Model scorecard: all tables</h1>'
            '<p>One page per table. Nothing here is about real tablets or a client.</p>' + unifying_panel() + safeguard_panel() + limit + "<h2>How to read a page</h2>" + legend + reading_key()
            + f'<h2>Tables</h2><div class="wrap"><table><tr><th>Table</th><th>Data status</th><th>Label</th><th>Carried</th><th>Exploratory</th><th>Not assessed</th></tr>{"".join(rows)}</table></div></main>')
    return _page("Model scorecard: all tables", body)
