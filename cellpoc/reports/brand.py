"""The Deloitte look for every file the platform writes for people to read (reports, guides): palette, Open Sans, the dark header band with its green top rule, the green label banner, and a small Markdown-to-page converter.

The palette is the same as the dashboard's (cellpoc/dashboard/style.py); a health check keeps the two equal. Colours come only from the brand palette. Green is used for fills, borders and rules, not for small text on white.
No logo and no tagline are used. Every page carries its data-status label, and nothing in a page is fetched from the internet: the font is inside the file.
"""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

GREEN = "#86BC25"
NEON = "#86EB22"
BLUE = "#00A3E0"
BLUE_DARK = "#005587"
BLUE_LIGHT = "#A0DCFF"
LIME = "#B7E320"
DARK = "#282728"
GREY_TEXT = "#555555"
RULE = "#E6E6E6"
PAGE_ALT = "#F5F5F5"
WHITE = "#FFFFFF"
AMBER = "#E8A317"
RED = "#DA291C"
BLACK = "#000000"
PALETTE = {GREEN, NEON, BLUE, BLUE_DARK, BLUE_LIGHT, LIME, DARK, GREY_TEXT, RULE, PAGE_ALT, WHITE, AMBER, RED, BLACK}
FONT = "Open Sans"
FONT_STACK = "'Open Sans', Arial, sans-serif"
FONT_FILE = Path(__file__).resolve().parents[2] / "static" / "OpenSans.ttf"

CSS = f"""
@font-face{{font-family:'Open Sans';font-weight:300 800;src:url(data:font/ttf;base64,__FONT__) format('truetype')}}
*,*::before,*::after{{box-sizing:border-box}}
body{{margin:0;background:{WHITE};color:{DARK};font-family:{FONT_STACK};line-height:1.55;font-size:14px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.band{{position:relative;overflow:hidden;background:{DARK};border-top:4px solid {GREEN};padding:24px 32px 22px 32px}}
.band h1{{margin:0;color:{WHITE};font-size:1.9rem;font-weight:700;line-height:1.2}}
.band .accent{{font-style:italic;color:{NEON};font-weight:700}}
.band p{{margin:6px 0 0 0;color:{RULE};font-size:.95rem}}
.band svg{{position:absolute;right:-50px;top:-50px;width:260px;height:260px;opacity:.35}}
.label{{background:{GREEN};color:{BLACK};padding:8px 32px;font-weight:700}}
.wrap{{max-width:1000px;margin:0 auto;padding:8px 32px 28px 32px}}
h2{{font-size:1.25rem;margin:26px 0 8px 0;padding-top:6px;border-top:2px solid {GREEN};color:{DARK}}}
h3{{font-size:1.05rem;margin:18px 0 6px 0;color:{DARK}}}
p{{margin:6px 0}}
ul,ol{{margin:6px 0 6px 22px;padding:0}}
li{{margin:3px 0}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:.85rem}}
th{{background:{DARK};color:{WHITE};text-align:left;padding:6px 8px;font-weight:700}}
td{{border-bottom:1px solid {RULE};padding:5px 8px;vertical-align:top}}
tr:nth-child(even) td{{background:{PAGE_ALT}}}
td.num{{text-align:right;white-space:nowrap}}
code{{background:{PAGE_ALT};border:1px solid {RULE};border-radius:3px;padding:0 4px;font-size:.85em}}
pre{{background:{PAGE_ALT};border:1px solid {RULE};border-left:4px solid {GREEN};border-radius:4px;padding:10px 12px;overflow:auto;font-size:.82rem}}
blockquote{{margin:10px 0;padding:6px 14px;border-left:4px solid {GREEN};background:{PAGE_ALT};color:{DARK}}}
hr{{border:0;border-top:1px solid {RULE};margin:18px 0}}
.good{{border-left:4px solid {GREEN};padding-left:8px}}
.not-good{{border-left:4px solid {BLUE_LIGHT};padding-left:8px}}
.none{{border-left:4px solid {RED};padding-left:8px}}
.foot{{margin-top:26px;border-top:1px solid {RULE};padding-top:8px;color:{GREY_TEXT};font-size:.8rem}}
@page{{size:A4;margin:12mm}}
@media print{{h2,h3{{break-after:avoid}}tr{{break-inside:avoid}}pre,blockquote{{break-inside:avoid}}}}
"""

RINGS = (f'<svg viewBox="0 0 200 200" aria-hidden="true"><circle cx="100" cy="100" r="92" fill="none" stroke="{GREEN}" stroke-width="1.5"/>'
         f'<circle cx="100" cy="100" r="68" fill="none" stroke="{NEON}" stroke-width="1.5"/><circle cx="100" cy="100" r="44" fill="none" stroke="{BLUE}" stroke-width="1.5"/></svg>')


def font_base64() -> str:
    return base64.b64encode(FONT_FILE.read_bytes()).decode("ascii")


def page(title: str, accent: str, subtitle: str, label: str, body_html: str, footer: str = "") -> str:
    """One self-contained page: the dark band (the title with ONE italic accent word), the green label banner, the body and a footer. `accent` must be a word of `title`."""
    words = html.escape(title).split(" ")
    marked = False
    shown_words = []
    for w in words:
        if not marked and w.strip(":,.").lower() == html.escape(accent).lower():       # the accent word is matched without regard to capitals or a trailing colon
            shown_words.append(f'<span class="accent">{w}</span>')
            marked = True
        else:
            shown_words.append(w)
    shown = " ".join(shown_words)
    css = CSS.replace("__FONT__", font_base64())
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head>\n'
            f'<body><div class="band">{RINGS}<h1>{shown}</h1><p>{html.escape(subtitle)}</p></div><div class="label">{html.escape(label)}</div>\n'
            f'<div class="wrap">\n{body_html}\n<div class="foot">{html.escape(footer or label)}</div></div></body></html>\n')


# ---------------------------------------------------------------- a small Markdown converter (only what the guides use)
def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<em>\1</em>", text)
    return text


def md_to_html(text: str) -> str:
    """Headings (## and ###), paragraphs, bullet and numbered lists, tables, quotes, rules and code blocks. The first '# ' heading is left out (it is the page title)."""
    out: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    para: list[str] = []
    list_kind: str | None = None

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para = []

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para(); close_list()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
        elif stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip().lstrip("|")):
            flush_para(); close_list()
            head = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>" for row in rows) + "</tbody></table>")
            continue
        elif stripped.startswith("# "):
            flush_para(); close_list()
        elif stripped.startswith("## "):
            flush_para(); close_list()
            out.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            flush_para(); close_list()
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped in ("---", "***"):
            flush_para(); close_list()
            out.append("<hr>")
        elif stripped.startswith("> "):
            flush_para(); close_list()
            quote = [stripped[2:]]
            while i + 1 < len(lines) and lines[i + 1].strip().startswith(">"):
                i += 1
                quote.append(lines[i].strip().lstrip(">").strip())
            out.append("<blockquote>" + _inline(" ".join(q for q in quote if q)) + "</blockquote>")
        elif re.match(r"^\s*[-*] ", line) or re.match(r"^\s*\d+\. ", line):
            flush_para()
            kind = "ol" if re.match(r"^\s*\d+\. ", line) else "ul"
            if list_kind != kind:
                close_list()
                out.append(f"<{kind}>")
                list_kind = kind
            item = re.sub(r"^\s*(?:[-*]|\d+\.) ", "", line)
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip() and not re.match(r"^\s*(?:[-*]|\d+\.) ", lines[i + 1]):
                i += 1
                item += " " + lines[i].strip()
            out.append(f"<li>{_inline(item)}</li>")
        elif not stripped:
            flush_para(); close_list()
        else:
            close_list()
            para.append(stripped)
        i += 1
    flush_para(); close_list()
    return "\n".join(out)
