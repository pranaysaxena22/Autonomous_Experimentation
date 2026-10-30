"""Turns the plain-language guides in docs/guides/*.md into branded pages (Deloitte palette, Open Sans, green label banner, the font inside the file, no internet needed) and, with --pdf, into PDFs, using an installed browser.

The Markdown in docs/guides/ is the source and is saved in git; the pages and PDFs are generated into runs/guides/ (not saved in git, so they can never be out of date). Double-click make_guides.bat, or run:
    .venv\\Scripts\\python.exe tools\\make_guides.py [--pdf] [output folder]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.reports import brand  # noqa: E402
from cellpoc.reports.builder import write_pdf  # noqa: E402

GUIDES_DIR = ROOT / "docs" / "guides"
DEFAULT_OUT = ROOT / "runs" / "guides"
LABEL = "ILLUSTRATIVE: a simulation with illustrative values. Nothing here is real client data, and nothing says anything about real tablets."
# name -> (page title, the one italic accent word, subtitle)
GUIDES = {
    "demo_video_script": ("Demo video script: three minutes, problem to solution", "video", "A crisp script for a three-minute demo video: the problem, the idea, the live demo, the numbers and what is next"),
    "client_demo_script": ("Client demo script for the autonomous formulation cell", "client", "A 15-minute walk through the app for a client: what to open, what to say, what is real and what is not"),
    "demo_script": ("Demo script for the autonomous formulation cell", "demo", "A simple script for showing the whole project, with what to click and what to say"),
    "system_explained": ("The autonomous formulation cell explained", "explained", "What it is, how it is built and how to operate it, in plain language"),
    "work_report": ("Work report: Stages 5 to 10", "report", "What was built, how it was checked, what was decided and what is still open"),
    "acceptance_runner_design": ("The sealed acceptance run: a design for review", "review", "Proposed, not approved. Nothing built and nothing run"),
}


def page_for(name: str) -> str:
    title, accent, subtitle = GUIDES[name]
    source = (GUIDES_DIR / f"{name}.md").read_text(encoding="utf-8")
    return brand.page(title, accent, subtitle, LABEL, brand.md_to_html(source), LABEL + " Generated from docs/guides/" + name + ".md by tools/make_guides.py.")


def build_all(out: Path, pdf: bool = False) -> list[str]:
    """Write every guide's page (and PDF) into `out`; returns plain notes about anything that could not be done."""
    out.mkdir(parents=True, exist_ok=True)
    notes = []
    for name in GUIDES:
        page = out / f"{name}.html"
        page.write_text(page_for(name), encoding="utf-8", newline="\n")
        if pdf:
            note = write_pdf(page, out / f"{name}.pdf")
            if note:
                notes.append(note)
    return notes


def main(argv: list[str]) -> int:
    folders = [a for a in argv if not a.startswith("--")]
    out = Path(folders[0]) if folders else DEFAULT_OUT
    notes = build_all(out, "--pdf" in argv)
    print(f"Wrote {len(GUIDES)} guides to {out}:")
    for name in GUIDES:
        print(f"  {name}.html" + ("  and .pdf" if "--pdf" in argv and not notes else ""))
    for note in sorted(set(notes)):
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
