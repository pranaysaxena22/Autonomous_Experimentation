"""Writes the 3D replay viewer: ONE self-contained HTML file with the layout and the executed timelines embedded and the 3D library (three.js r128, MIT, bundled in vendor/) and the font (Open Sans, bundled in
static/) inside it, so it opens with a double-click on a computer with no internet. The file replays the timelines it contains and calculates no result of its own (see viewer.js).

This module only assembles data files and text; it imports no other part of the platform. Every timeline's data status is respected: the page is labelled with the weakest status among the layout and the timelines.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT = HERE.parents[1] / "static" / "OpenSans.ttf"
STATUS_ORDER = ("synthetic", "illustrative", "real", "validated")


class ViewerError(Exception):
    """The viewer cannot be built from these inputs. The message says what is wrong."""


def _safe(text: str) -> str:
    """Text placed inside a <script> block must never contain a closing tag."""
    return text.replace("</", "<\\/")


def build_viewer(layout: dict, timelines: list[dict], out_path: Path | str, title: str = "Robot cell: 3D replay") -> Path:
    if not timelines:
        raise ViewerError("There is no executed timeline to replay.")
    ids = {t["layout_id"] for t in timelines}
    if ids != {layout["layout_id"]}:
        raise ViewerError(f"The timelines were run on layout(s) {sorted(ids)} but the layout given is '{layout['layout_id']}'.")
    status = min([layout.get("data_status", "illustrative"), *[t["data_status"] for t in timelines]], key=STATUS_ORDER.index)
    template = (HERE / "template.html").read_text(encoding="utf-8")
    page = (template.replace("__TITLE__", title).replace("__LABEL__", f"{status.upper()} replay.")
            .replace("__FONT_BASE64__", base64.b64encode(FONT.read_bytes()).decode("ascii"))
            .replace("__LAYOUT_JSON__", _safe(json.dumps(layout, separators=(",", ":"))))
            .replace("__TIMELINES_JSON__", _safe(json.dumps(timelines, separators=(",", ":"))))
            .replace("/*__THREE__*/", _safe((HERE / "vendor" / "three.min.js").read_text(encoding="utf-8")))
            .replace("/*__VIEWER_JS__*/", _safe((HERE / "viewer.js").read_text(encoding="utf-8"))))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
