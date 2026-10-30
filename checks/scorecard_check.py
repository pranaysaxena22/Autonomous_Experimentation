"""Health check for Stage 3b-4 (the model scorecard): does each page say the right things, in the right order, in a style that tells different findings apart at a glance?

In plain words it checks that: the reading for a kind of shift is worked out for each result on its own and never averaged (hardness at 0.59 and tensile at 1.17 give 'cannot be judged' with 17 warned
rows and 'mixed' with 100, never 'picks out the large errors', and every result's own numbers are printed beside the word); the four readings ('picks out the large errors', 'mixed', 'cannot be judged',
'does not') each have their own look, different from each other in background, border and marker, so weak-but-positive, not-enough-data and clearly-negative can be told apart at a glance;
carried, carried-but-exploratory and not-assessed results each have their own look and appear only in their own style; every colour is from the Deloitte palette, green is never used for small text,
and a page needs no internet and no script; the page order is fixed (banner, the unifying statement, the safeguard panel, the readings, the test-data limitation, results, replay, what it does not show);
the fixture limitation is stated on every synthetic page as its own item; the four warning statuses are separate with no combined flag; real batch hardness and tensile strength carry the fixed
'replay not run' sentence and no window; every line naming api_code says 'proxy, not a confirmed supplier'; tagged tables carry their label in every result heading. Nothing is written into the project.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling import PROXY_PHRASE, build_table_for_setup  # noqa: E402
from cellpoc.modelling.carry import BORDERLINE, CARRIED, SKIPPED, decide_all  # noqa: E402
from cellpoc.modelling.findings import NO_REPLAY_SENTENCE, UNIFYING_STATEMENT  # noqa: E402
from cellpoc.modelling.fixtures import MOCK_FILES, NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.replay import movement, replay_table, targets_from_setup  # noqa: E402
from cellpoc.modelling.scorecard import WORD_CANNOT, WORD_DOES_NOT, WORD_MIXED, WORD_PICKS, Numbers, ResultCard, TableCard, build_card, shift_reading  # noqa: E402
from cellpoc.modelling import scorecard_html as html_module  # noqa: E402
from cellpoc.modelling.scorecard_html import CSS, STYLE, render_index, render_table  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist, external_references  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

CACHE = ROOT / "runs" / "modelling" / "cache_full"
BRAND = {"#86BC25", "#000000", "#86EB22", "#00A3E0", "#282728", "#FFFFFF", "#A0DCFF", "#005587", "#E6E6E6", "#E2E2E2",
         "#F5F5F5", "#555555", "#B7E320", "#63C631", "#3FC3EC", "#E8A317", "#DA291C"}


def rule(selector: str) -> str:
    """The body of one CSS rule, spaces removed."""
    found = re.search(re.escape(selector) + r"\{([^}]*)\}", CSS)
    return found.group(1).replace(" ", "") if found else ""


def attribute(body: str, name: str) -> str:
    found = re.search(r"(?:^|;)" + name + r":([^;]*)", body)
    return found.group(1) if found else ""


def border_style(body: str) -> str:
    border = attribute(body, "border") or attribute(body, "border-left")
    return next((w for w in ("solid", "double", "dotted", "dashed") if w in border), "")


def made_up_card(synthetic: bool = True, tag: str = "") -> TableCard:
    ok = ResultCard("r1", "Hardness", CARRIED, "", model="Linear regression", why="Chosen.", worst=0.4)
    exp = ResultCard("r2", "Dissolution", BORDERLINE, "EXPLORATORY: borderline result (worst error 0.74 of the spread)", model="Linear regression", why="Chosen.", worst=0.74)
    skip = ResultCard("r3", "Yield", SKIPPED, "", reason="Calibration not assessed: the model does not predict well enough.")
    readings = [shift_reading("batch", "whole batches (batch_id)", [Numbers("Hardness", 56, 2.14, 1.52, 0), Numbers("Tensile", 56, 2.85, 1.64, 0)], "30 of 158 batches flagged"),
                shift_reading("supplier", "whole suppliers (binder_supplier)", [Numbers("Hardness", 3, 0.0, None, 0)], "3 of 3 suppliers flagged, threshold from chance alone"),
                shift_reading("date", "later dates (date)", [Numbers("Hardness", 17, 0.59, 0.94, 0), Numbers("Tensile", 17, 1.17, 0.94, 0)], "4 of 4 time periods flagged"),
                shift_reading("date", "later dates, enough rows", [Numbers("Hardness", 100, 0.59, 0.94, 0), Numbers("Tensile", 100, 1.17, 0.94, 0)]),
                shift_reading("date", "later dates, all below chance", [Numbers("Hardness", 100, 0.59, 0.94, 0), Numbers("Tensile", 100, 0.7, 0.94, 0)])]
    return TableCard("made_up", "SYNTHETIC DATA" if synthetic else "REAL PUBLIC DATA, NOT CLIENT DATA", synthetic, tag, [ok, exp, skip], readings, None, 0.002, 0.86)


FOUR_HEADS = ("(1) Distance", "(2) Numeric range", "(3) Unseen supplier or product", "(4) Whole group")


def status_problems(section: str, result: ResultCard) -> list[str]:
    """Everything missing from one carried or borderline result's card about the four warning statuses (empty means all four are there for every hold-out type)."""
    problems = [f"no '{h}' column" for h in FOUR_HEADS if f"<th>{h}</th>" not in section]
    table = section.split("The four warning statuses", 1)[-1].split("</table>", 1)[0]
    rows = re.findall(r"<tr><td>(.*?)</tr>", table, re.S)
    if not rows or len(rows) != len(result.warnings) or len(rows) != len(result.accuracy):
        problems.append(f"{len(rows)} warning rows for {len(result.accuracy)} hold-out types")
    for row in rows:
        cells = row.split("</td><td>")
        if len(cells) != 5 or "%" not in cells[2] or "%" not in cells[3]:
            problems.append("a hold-out row lacks its numeric-range or unseen-supplier-or-product figure")
    return problems


def reading_checks(cl: Checklist) -> None:
    rows = {n: shift_reading("date", "later dates", [Numbers("Hardness", n, 0.59, 0.94, 0), Numbers("Tensile", n, 1.17, 0.94, 0)]).word for n in (17, 29, 30, 100)}
    cl.record(rows == {17: WORD_CANNOT, 29: WORD_CANNOT, 30: WORD_MIXED, 100: WORD_MIXED},
              "Per-result rule (your worked example): hardness 0.59 and tensile 1.17 give 'cannot be judged' with 17 or 29 warned rows and 'mixed' with 30 or 100, and never 'picks out the large errors': tensile cannot carry hardness", str(rows))
    words = [shift_reading("k", "h", [Numbers("a", 100, x, 1.0, 0), Numbers("b", 100, y, 1.0, 0)]).word for x, y in ((1.2, 1.5), (1.2, 0.9), (0.9, 0.8), (1.0, 1.0))]
    cl.record(words == [WORD_PICKS, WORD_MIXED, WORD_DOES_NOT, WORD_DOES_NOT], "The four readings come out right for 100 rows each: above chance in both, in one, in neither, and exactly chance (1.0) is not above", str(words))
    page = render_table(made_up_card())
    mixed_row = re.search(r'<tr data-kind="date"><td>later dates, enough rows</td>(.*?)</tr>', page, re.S).group(1)
    cl.record(WORD_MIXED in mixed_row and "lift 0.59" in mixed_row and "lift 1.17" in mixed_row and "0.88" not in page and WORD_PICKS not in mixed_row,
              "The page prints every result's own rows warned, lift and error ratio beside the word (0.59 and 1.17 both shown, no average of them anywhere)", "")
    source = "".join((ROOT / "cellpoc" / "modelling" / f).read_text(encoding="utf-8") for f in ("scorecard.py", "scorecard_html.py"))
    cl.record(re.search(r"mean\(|average\(", source) is None, "The scorecard code never averages anything across results (no mean or average calculation in it)", "")


def style_checks(cl: Checklist) -> None:
    words = (WORD_PICKS, WORD_MIXED, WORD_CANNOT, WORD_DOES_NOT)
    bodies = {w: rule("." + STYLE[w][0]) for w in words}
    attrs = {w: (attribute(bodies[w], "background"), border_style(bodies[w]), STYLE[w][1]) for w in words}
    pairs = [(a, b) for i, a in enumerate(words) for b in words[i + 1:]]
    differing = {(a, b): sum(x != y for x, y in zip(attrs[a], attrs[b])) for a, b in pairs}
    cl.record(all(bodies.values()) and all(v >= 2 for v in differing.values()) and len({a[0] for a in attrs.values()}) == 4 and len({a[2] for a in attrs.values()}) == 4,
              "Your addition: 'picks out the large errors', 'mixed', 'cannot be judged' and 'does not' each have their own look: four different backgrounds, four different markers, and any two differ in at least two of background, border and marker",
              "; ".join(f"{w}: {attrs[w]}" for w in words))
    mixed, cannot, does = attrs[WORD_MIXED], attrs[WORD_CANNOT], attrs[WORD_DOES_NOT]
    cl.record(all(sum(x != y for x, y in zip(a, b)) == 3 for a, b in ((mixed, cannot), (mixed, does), (cannot, does))),
              "The three 'not reliable' readings (weak but positive, not enough data, clearly negative) differ from each other in all three of background, border and marker", "")
    page = render_table(made_up_card())
    found = {w: re.findall(r'<span class="badge ([a-z-]+)" data-reading="([^"]+)">(\S+) ' + re.escape(w) + "</span>", page) for w in words}
    cl.record(all(found[w] and all(f[0] == STYLE[w][0] and f[2] == STYLE[w][1] for f in found[w]) for w in words),
              "On a rendered page every reading is drawn in its own style with its own marker (and the key at the top shows all four)", str({w: len(v) for w, v in found.items()}))
    # the three result statuses
    cards = {"carried": rule(".card-carried"), "borderline": rule(".card-exploratory"), "skipped": rule(".card-skipped")}
    borders = {k: border_style(v) for k, v in cards.items()}
    chips = {k: rule(f".chip-{k if k != 'borderline' else 'exploratory'}") for k in cards}
    cl.record(len(set(borders.values())) == 3 and len({attribute(c, "background") for c in cards.values()}) == 3 and len({attribute(c, "background") for c in chips.values()}) == 3 and "" not in borders.values(),
              "Carried, carried-but-exploratory and not-assessed results each have their own look: three different border styles, card backgrounds and chip colours", str(borders))
    sections = re.findall(r'<section class="card (card-[a-z]+)" data-status="([a-z]+)">(.*?)</section>', page, re.S)
    expect = {"carried": ("card-carried", "CARRIED<"), "borderline": ("card-exploratory", "CARRIED BUT EXPLORATORY<"), "skipped": ("card-skipped", "NOT ASSESSED<")}
    ok = len(sections) == 3 and all(css == expect[st][0] and expect[st][1] in body for css, st, body in sections)
    ok = ok and all("Hold-out" in body for css, st, body in sections if st != "skipped") and all("Hold-out" not in body for css, st, body in sections if st == "skipped")
    ok = ok and any("EXPLORATORY: borderline" in body for css, st, body in sections if st == "borderline") and not any("EXPLORATORY" in body for css, st, body in sections if st != "borderline")
    cl.record(ok, "Each status appears only in its own style: a carried card is never styled as exploratory or skipped (and the reverse), exploratory cards carry their label, not-assessed cards carry the reason and no numbers", f"{len(sections)} cards")


def page_checks(cl: Checklist) -> None:
    pages = {"synthetic": render_table(made_up_card()), "real": render_table(made_up_card(False)), "index": render_index([made_up_card()], {"made_up": "scorecard_made_up.html"})}
    colours = {c.upper() for p in pages.values() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", p)}
    cl.record(colours <= BRAND and {"#86BC25", "#282728", "#00A3E0"} <= colours, "Every colour on the pages is from the Deloitte palette (green first; dark grey and blue in use)", f"{len(colours)} colours; outside the palette: {sorted(colours - BRAND)}")
    green_text = re.findall(r"(?<![-\w])color:\s*#86BC25", CSS)
    cl.record(not green_text, "Green is used only for fills and bars (with black text), never as the colour of small text on white", "")
    cl.record(all(not external_references(p) and "<script" not in p.lower() and "http://" not in p and "https://" not in p and "@import" not in p for p in pages.values()),
              "Pages need no internet and no script: no web address, no script, no imported font or library", "")
    cl.record("'Open Sans',Arial" in CSS, "The font stack is Open Sans with an Arial fallback", "")
    page = pages["synthetic"]
    order = [page.index(k) for k in ('class="top"', UNIFYING_STATEMENT, "The warning is the main safeguard", "Can the warning be trusted", "Known limitation of the test data itself", "<h2>Carried results</h2>", "What this does not show")]
    cl.record(order == sorted(order), "Page order is fixed: banner, the unifying statement, the safeguard panel, the readings, the test-data limitation, the results, what it does not show", "")
    limit = {k: "Known limitation of the test data itself" in p for k, p in pages.items()}
    cl.record(limit == {"synthetic": True, "real": False, "index": True} and all(s in page for s in ("cannot validate how the distance check behaves under a supplier shift", "a gap in the design of the synthetic test", "not a neutral or a passing result", "0.2%", "86%")),
              "The fixture limitation is its own panel on synthetic pages and the index (not on real-data pages): the mocks cannot validate the distance check under a supplier shift; 'cannot be judged' there is a gap in the test design, not a neutral or passing result", str(limit))
    cl.record(all(a in page for a in ("(1) Per recipe, distance", "(2) Per recipe, numeric range", "(3) Per recipe, unseen supplier or product", "(4) Whole group")) and not any(w in page for w in ("any check", "combined flag:", "Warned (any")),
              "The four warning statuses are listed separately in the safeguard panel and no combined flag exists", "")
    cl.record(all(UNIFYING_STATEMENT in p for p in pages.values()), "Every page, and the index, carries the unifying statement word for word", "")


def saved_checks(cl: Checklist) -> None:
    files = len(list(CACHE.glob("*.pkl"))) if CACHE.exists() else 0
    if files < 280 or not all(fixture_available(n) for n in NAMES):
        cl.skip("The scorecard on the saved Stage 3a answers", "they (or the real public data) are not on this computer: double-click run_full_validation.bat first")
        return
    validations = [run_validation(build_table_for_setup(fixture_setup(n), None, PROJECT_ROOT, n), FULL, n_jobs=1, cache=CACHE, save=False) for n in NAMES]
    decisions = decide_all(validations)
    by = {v.table.name: v for v in validations}
    real_share = movement(by["batch_production"].table, "tbl_av_hardness").supplier
    cards = {}
    for v in validations:
        n = v.table.name
        replay = replay_table(v, decisions, targets_from_setup(fixture_setup(n))) if n in MOCK_FILES else None
        cards[n] = build_card(v, decisions, replay, real_share)
    pages = {n: render_table(c) for n, c in cards.items()}
    cl.record(set(pages) == set(NAMES), "One page is built for each of the six tables", ", ".join(pages))
    cl.record(all(c.label in pages[n] and pages[n].count(c.label) >= 2 for n, c in cards.items()), "Every page opens with its data-status banner and repeats the label in its title (SYNTHETIC DATA or REAL PUBLIC DATA, NOT CLIENT DATA)", "")
    real = pages["batch_production"]
    carried = [d for d in decisions if d.table == "batch_production" and d.status == CARRIED]
    cl.record(len(carried) == 2 and real.count(NO_REPLAY_SENTENCE) == 2 and not any(w in NO_REPLAY_SENTENCE for w in ("kP", "between", "at least", "at most")),
              "Real batch hardness and tensile strength each carry the fixed 'Decision-usefulness replay not run; no client-specified target exists for this result...' sentence, and the page states no window or target of any kind", f"{real.count(NO_REPLAY_SENTENCE)} sentences")
    cl.record("Replay (synthetic" not in real and "Decision-usefulness replay (synthetic" not in real and all("Decision-usefulness replay (synthetic" in pages[n] for n in ("mock_easy", "mock_hard")),
              "The replay appears only on the synthetic mock pages", "")
    bad = []
    for n, p in pages.items():
        for m in re.finditer("api_code", p):
            if PROXY_PHRASE not in p[m.start():m.start() + 60]:
                bad.append(n)
    cl.record(not bad and "api_code" in real, "Every mention of api_code on every page is followed by 'proxy, not a confirmed supplier'", f"{len(bad)} without it")
    date_row = re.search(r'<tr data-kind="date">(.*?)</tr>', real, re.S).group(1)
    cl.record(WORD_CANNOT in date_row and "lift 0.59" in date_row and "lift 1.17" in date_row and WORD_PICKS not in date_row,
              "Real batch data, later dates (your worked example on the real page): hardness lift 0.59 and tensile lift 1.17 with 17 warned rows each read 'cannot be judged', both numbers shown", "")
    hard = pages["mock_hard"]
    cl.record(("EXPLORATORY: borderline" in hard) and "card-exploratory" in hard and "[EXPLORATORY: borderline]" in re.search(r'<tr data-kind="batch">(.*?)</tr>', hard, re.S).group(1),
              "On the hard mock page the borderline result is in its own exploratory card, is marked EXPLORATORY inside the readings it contributes to, and its replay rows are in the exploratory style", "")
    easy = pages["mock_easy"]
    cl.record("card-exploratory" not in easy.split("</style>", 1)[1] and "[EXPLORATORY: borderline]" not in easy, "The easy mock page has no exploratory styling at all (it has no borderline results)", "")
    tagged = [n for n, c in cards.items() if c.tag]
    ok = True
    for n in tagged:
        tag = html.escape(cards[n].tag, quote=True)
        cards_html = re.findall(r"<section class=.*?</section>", pages[n], re.S)
        ok = ok and len(cards_html) == len(cards[n].results) and all(tag in s for s in cards_html) and tag in pages[n].split('<div class="status', 1)[1].split("</div>", 1)[0]
    cl.record(bool(tagged) and ok, "Exploratory and robustness-only tables carry their label in the banner and in every result card", ", ".join(tagged))
    missing, total = [], 0
    for n, c in cards.items():
        sections = re.findall(r"<section class=.*?</section>", pages[n], re.S)
        in_page_order = c.by_status(CARRIED) + c.by_status(BORDERLINE) + c.by_status(SKIPPED)         # the page groups cards by status
        assert len(sections) == len(in_page_order)
        for r, section in zip(in_page_order, sections):
            if r.status in (CARRIED, BORDERLINE):
                total += 1
                missing += [f"{n}/{r.result}: {p}" for p in status_problems(section, r)]
    cl.record(total >= 8 and not missing, f"Every carried and borderline result's card (all {total} of them, on every page) shows distance, numeric range, unseen supplier or product and whole-group for EVERY hold-out type it has, each with its figures: none is left out now that they are not in the readings table",
              "; ".join(missing[:3]))
    # a negative control: the same test must notice a card that lacks them
    sample = next(r for c in cards.values() for r in c.results if r.status == CARRIED)
    good = re.findall(r"<section class=.*?</section>", pages["mock_easy"], re.S)[0]
    broken = [good.replace("<th>(2) Numeric range</th>", ""), good.replace("<th>(3) Unseen supplier or product</th>", ""), good.replace("The four warning statuses", "x")]
    cl.record(all(status_problems(b, cards["mock_easy"].results[0]) for b in broken) and not status_problems(good, cards["mock_easy"].results[0]) and bool(status_problems(good, ResultCard("x", "X", CARRIED, ""))),
              "Negative control: the same test does report a card with the numeric-range column removed, one with the unseen-supplier-or-product column removed, one with the whole warning table removed, and a result with no warning rows", sample.label)
    skipped = [r for c in cards.values() for r in c.results if r.status == SKIPPED]
    cl.record(bool(skipped) and all(not r.accuracy and not r.calibration and not r.warnings and r.reason for r in skipped), "Results that were not carried have a reason and no accuracy, calibration or warning numbers", f"{len(skipped)} results")
    index = render_index(list(cards.values()), {n: f"scorecard_{n}.html" for n in cards})
    cl.record(all(f'href="scorecard_{n}.html"' in index for n in cards) and "Known limitation of the test data itself" in index and UNIFYING_STATEMENT in index,
              "The index links all six pages and carries the unifying statement and the test-data limitation", "")
    cl.record(UNIFYING_STATEMENT in (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8").replace("**", ""), "docs/decisions.md records the unifying statement word for word", "")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 3b-4: the model scorecard (are the right things said, in the right order, in a style that tells different findings apart?)")
    before = project_files()
    reading_checks(cl)
    style_checks(cl)
    page_checks(cl)
    saved_checks(cl)
    found = forbidden_in(sorted((ROOT / "cellpoc" / "modelling").glob("*.py")))
    cl.record(not found, "The modelling code, including the scorecard, contains no random splitter or sampler", "; ".join(found[:3]))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
