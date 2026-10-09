"""Shared plumbing for the stage health checks: a PASS/FAIL list printed in plain words."""
from __future__ import annotations

import re
from pathlib import Path

_EXTERNAL = re.compile(r"<(?:script|link|img|iframe)[^>]+(?:src|href)=[\"']https?://[^\"']+", re.IGNORECASE)


def external_references(html: str) -> list[str]:
    """Anything in a page that would be fetched from the internet when it is opened."""
    return _EXTERNAL.findall(html)


def write_chart_page(chart, path: Path, banner: str, accent: str, font: str) -> None:
    """Save an Altair chart as a stand-alone web page that works with no internet.

    The chart library is bundled into the file (inline=True), and the 'illustrative values'
    banner is added on top. Raises if the finished page would still fetch anything online.
    The font is named but not bundled: with no internet and the font not installed, the
    browser falls back to Arial.
    """
    chart.save(str(path), inline=True)
    bar = (f'<div style="font-family:\'{font}\',Arial,sans-serif;background:{accent};color:#000;'
           f'padding:10px 16px;font-weight:600">{banner}</div>')
    html = path.read_text(encoding="utf-8").replace("<body>", "<body>" + bar, 1)
    path.write_text(html, encoding="utf-8")
    leaks = external_references(html)
    if leaks:
        raise RuntimeError(f"{path.name} would still need the internet: {leaks}")


class Checklist:
    def __init__(self, title: str):
        self.title = title
        self.rows: list[tuple[str, str, str]] = []
        self.headlines: list[str] = []

    def record(self, ok: bool, what: str, detail: str = "") -> bool:
        self.rows.append(("PASS" if ok else "FAIL", what, detail))
        return ok

    def skip(self, what: str, detail: str) -> None:
        self.rows.append(("SKIP", what, detail))

    def warn(self, what: str, detail: str = "") -> None:
        """Something to look at that does not make the check fail."""
        self.rows.append(("WARN", what, detail))

    def headline(self, text: str) -> None:
        self.headlines.append(text)

    def print(self) -> int:
        print()
        print(self.title)
        print("=" * 60)
        for status, what, detail in self.rows:
            print(f"[{status}] {what}")
            if detail:
                print(f"        {detail}")
        print("=" * 60)
        for line in self.headlines:
            print(f"HEADLINE: {line}")
        if self.headlines:
            print("-" * 60)
        failed = sum(1 for status, _, _ in self.rows if status == "FAIL")
        passed = sum(1 for status, _, _ in self.rows if status == "PASS")
        warned = sum(1 for status, _, _ in self.rows if status == "WARN")
        warning_text = f", {warned} warning{'s' if warned != 1 else ''}" if warned else ""
        verdict = "  SOMETHING NEEDS ATTENTION." if failed else ("  ALL GOOD (warnings are for you to look at; they are not failures)." if warned else "  ALL GOOD.")
        print(f"{passed} passed, {failed} failed{warning_text}." + verdict)
        return 1 if failed else 0
