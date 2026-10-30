"""Builds the live page: one self-contained HTML file (the 3D library and the font inside it), made from the replay viewer's state engine and drawing code, unchanged, plus the live page script.

The replay viewer's script is cut where its own page part begins and the live page part is joined on, so the arm is drawn by exactly the same code in the replay and in the live run. Data files only; no other part is imported."""
from __future__ import annotations

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIEWER = HERE.parent / "viewer"
FONT = HERE.parents[1] / "static" / "OpenSans.ttf"
MARKER = "// ======================================================================== PART 3: the page"


class LivePageError(Exception):
    """The live page cannot be built."""


def _safe(text: str) -> str:
    return text.replace("</", "<\\/")


def live_script() -> str:
    """The replay viewer's parts 1 and 2 (the state engine and the drawing), then the live page part, inside the same closure."""
    source = (VIEWER / "viewer.js").read_text(encoding="utf-8")
    if MARKER not in source:
        raise LivePageError("The replay viewer's script no longer has the marker where its page part begins, so the live page cannot reuse its drawing code.")
    return source.split(MARKER)[0] + (HERE / "live_part3.js").read_text(encoding="utf-8") + "\n})();\n"


def console_script() -> str:
    """The replay viewer's parts 1 and 2 (the state engine and the drawing), then the console's page part, inside the same closure."""
    source = (VIEWER / "viewer.js").read_text(encoding="utf-8")
    if MARKER not in source:
        raise LivePageError("The replay viewer's script no longer has the marker where its page part begins, so the console cannot reuse its drawing code.")
    return source.split(MARKER)[0] + (HERE / "console_part3.js").read_text(encoding="utf-8") + "\n})();\n"


def narration_audio() -> dict:
    """The recorded narrator (voice_models/narration_audio.json, made by build_voice.bat), as {sentence fingerprint: base64 mp3}; empty if it has not been made, and the page then uses the computer's own voice."""
    path = HERE.parents[1] / "voice_models" / "narration_audio.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("clips", {}) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def build_console_page(layout: dict, title: str = "Autonomous Formulation Cell", token: str = "", autostart_hook: bool = False, replay_script: str = "", audio: dict | None = None) -> str:
    """The operations console: one self-contained page (the font and the 3D library inside) that shows the live run as three views (overview, operator, lab manager), with a welcome and a guided tour. Same safeguards as the live page:
    `token` is the secret the server writes into the page so its own controls can prove they come from it; `autostart_hook` (tests only) lets ?autostart=1 press play."""
    template = (HERE / "console_template.html").read_text(encoding="utf-8")
    clips = narration_audio() if audio is None else audio
    return (template.replace("__TITLE__", title).replace("__TOKEN__", token).replace("__AUTOSTART__", "1" if autostart_hook else "")
            .replace("__FONT_BASE64__", base64.b64encode(FONT.read_bytes()).decode("ascii"))
            .replace("__LAYOUT_JSON__", _safe(json.dumps(layout, separators=(",", ":"))))
            .replace("__NARRATION_AUDIO__", _safe(json.dumps(clips, separators=(",", ":"))))
            .replace("/*__THREE__*/", _safe((VIEWER / "vendor" / "three.min.js").read_text(encoding="utf-8")))
            .replace("/*__REPLAY__*/", _safe(replay_script))
            .replace("/*__CONSOLE_JS__*/", _safe(console_script())))


def build_live_page(layout: dict, title: str = "Robot cell: live run", token: str = "", autostart_hook: bool = False) -> str:
    """`token` is the secret the server writes into the page so that the page's own controls can prove they come from it; `autostart_hook` (tests only) lets ?autostart=1 start the run."""
    status = layout.get("data_status", "illustrative")
    template = (HERE / "live_template.html").read_text(encoding="utf-8")
    return (template.replace("__TITLE__", title).replace("__TOKEN__", token).replace("__AUTOSTART__", "1" if autostart_hook else "").replace("__LABEL__", f"{status.upper()} live run.")
            .replace("__FONT_BASE64__", base64.b64encode(FONT.read_bytes()).decode("ascii"))
            .replace("__LAYOUT_JSON__", _safe(json.dumps(layout, separators=(",", ":"))))
            .replace("/*__THREE__*/", _safe((VIEWER / "vendor" / "three.min.js").read_text(encoding="utf-8")))
            .replace("/*__LIVE_JS__*/", _safe(live_script())))
