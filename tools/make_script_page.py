"""Turns the team-call demo script (docs/guides/team_call_demo_script.md) into one self-contained html page (Deloitte look, prints cleanly): runs/guides/team_call_demo_script.html.

Edit the markdown, run this again. The page needs no internet (the font is inside it).
"""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "guides" / "team_call_demo_script.md"
TARGET = ROOT / "runs" / "guides" / "team_call_demo_script.html"
FONT = ROOT / "static" / "OpenSans.ttf"


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"(?<![\w*])\*(.+?)\*(?![\w*])", r"<em>\1</em>", text)
    return text


def render(lines: list[str]) -> tuple[str, str]:
    title, body, i = "", [], 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("# "):
            title = line[2:]
        elif line.startswith("## "):
            body.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            i -= 1
            for when, show, say in rows[2:]:
                parts = when.split("**")
                clock = parts[1] if len(parts) > 2 else when
                label = parts[2].strip() if len(parts) > 2 else ""
                body.append(f'<div class="beat"><div class="when"><b>{html.escape(clock)}</b><span>{html.escape(label)}</span></div>'
                            f'<div class="show"><small>Show on screen</small>{inline(show)}</div><div class="say"><small>Say</small>{inline(say)}</div></div>')
        elif re.match(r"^\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                items.append(f"<li>{inline(re.sub(r'^\d+\. ', '', lines[i].rstrip()))}</li>")
                i += 1
            i -= 1
            body.append("<ol>" + "".join(items) + "</ol>")
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:].rstrip())}</li>")
                i += 1
            i -= 1
            body.append("<ul>" + "".join(items) + "</ul>")
        elif line.strip():
            body.append(f"<p>{inline(line)}</p>")
        i += 1
    return title, "\n".join(body)


CSS = """
@font-face{font-family:'Open Sans';font-weight:300 800;src:url(data:font/ttf;base64,%FONT%) format('truetype')}
:root{--green:#86BC25;--neon:#86EB22;--ink:#282728;--muted:#5E5E60;--line:rgba(40,39,40,.14)}
*{box-sizing:border-box}
body{margin:0;background:#F1F2EE;color:var(--ink);font-family:'Open Sans',Arial,sans-serif;font-size:16px;line-height:1.55}
header{background:var(--ink);color:#fff;border-bottom:5px solid var(--green);padding:30px 6vw 26px;position:relative;overflow:hidden}
header::after{content:"";position:absolute;right:-120px;top:-150px;width:380px;height:380px;border-radius:50%;background:repeating-radial-gradient(circle,transparent 0 36px,rgba(134,188,37,.25) 36px 38px)}
.brand{display:flex;align-items:center;gap:14px;font-weight:700;position:relative}
.mark{width:34px;height:34px;border-radius:50%;border:4px solid var(--green);position:relative}.mark::after{content:"";position:absolute;inset:7px;border-radius:50%;background:var(--neon)}
h1{margin:18px 0 6px;font-size:2.2rem;line-height:1.15;letter-spacing:-.02em;position:relative}
.chip{display:inline-block;margin-top:8px;background:var(--green);color:#000;border-radius:999px;padding:2px 14px;font-size:.74rem;font-weight:800;letter-spacing:.06em;position:relative}
main{max-width:1100px;margin:0 auto;padding:26px 6vw 60px}
h2{margin:34px 0 14px;font-size:1.35rem;display:flex;align-items:center;gap:10px}
h2::before{content:"";width:12px;height:12px;border-radius:50%;background:var(--green);flex:0 0 12px}
p,li{max-width:80ch}
code{background:#fff;border:1px solid var(--line);border-radius:5px;padding:0 6px;font-size:.9em}
.beat{display:grid;grid-template-columns:150px minmax(0,.8fr) minmax(0,1.6fr);gap:0;background:#fff;border:1px solid var(--line);border-radius:16px;margin:0 0 12px;overflow:hidden;box-shadow:0 1px 2px rgba(40,39,40,.06)}
.beat>div{padding:14px 18px}
.when{background:var(--ink);color:#fff;border-right:5px solid var(--green)}.when b{display:block;font-size:1.05rem;color:var(--neon)}.when span{font-size:.82rem;color:#d0d0d0}
.show{background:#F7F8F4;border-right:1px solid var(--line);font-size:.92rem;color:var(--muted)}
.say{font-size:1.02rem}
small{display:block;font-size:.66rem;letter-spacing:.12em;text-transform:uppercase;font-weight:800;color:var(--muted);margin-bottom:4px}
.say small{color:#4b6e00}
ol,ul{padding-left:22px}li{margin:0 0 6px}
footer{padding:18px 6vw;background:var(--ink);color:#d0d0d0;font-size:.8rem}footer b{color:var(--neon)}
@media (max-width:820px){.beat{grid-template-columns:1fr}.when{border-right:0;border-bottom:4px solid var(--green)}.show{border-right:0;border-bottom:1px solid var(--line)}}
@media print{body{background:#fff;font-size:12px}header,.when{-webkit-print-color-adjust:exact;print-color-adjust:exact}.beat{break-inside:avoid;box-shadow:none}footer{display:none}h2{break-after:avoid}}
"""


def main() -> None:
    title, body = render(SOURCE.read_text(encoding="utf-8").splitlines())
    page = (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{CSS.replace('%FONT%', base64.b64encode(FONT.read_bytes()).decode('ascii'))}</style></head><body>"
            f"<header><div class='brand'><div class='mark'></div>Autonomous Formulation Cell</div><h1>{html.escape(title)}</h1><span class='chip'>SIMULATION WITH ILLUSTRATIVE VALUES</span></header>"
            f"<main>{body}</main><footer><b>ILLUSTRATIVE</b> · a simulation with made-up values · nothing here is a result about real tablets</footer></body></html>")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(page, encoding="utf-8")
    print(f"written: {TARGET}")


if __name__ == "__main__":
    main()
