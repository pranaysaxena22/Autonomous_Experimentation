"""Look and feel of the setup app: the project's own accent colour and font, the 'illustrative' banner, labelled messages.

The setup app keeps its own copy of the palette (it must not import the dashboard). The accent colour, font and banner come
from the project settings (config/settings.yaml, read only). Nothing is fetched from the internet: the font is the bundled
Open Sans in static/, or Arial when that is not available.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st
import yaml

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
FALLBACK = {"banner": "Simulation with illustrative values", "accent_colour": "#86BC25", "font": "Open Sans"}

DARK = "#282728"
GREY_TEXT = "#555555"
RULE = "#E6E6E6"
PAGE_ALT = "#F5F5F5"
WHITE = "#FFFFFF"
AMBER = "#E8A317"
RED = "#DA291C"
BLUE = "#005587"
NEON = "#86EB22"

# a message's label is always written out as a word; the colour only reinforces it
LEVELS = {"error": ("Error", RED, "rgba(218, 41, 28, 0.07)"),
          "warning": ("Warning", AMBER, "rgba(232, 163, 23, 0.13)"),
          "note": ("Note", BLUE, "rgba(0, 85, 135, 0.07)")}


def project_display() -> dict:
    """banner, accent colour and font from config/settings.yaml; sensible defaults if it cannot be read or is odd."""
    try:
        shown = (yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8")) or {}).get("display", {})
    except (OSError, yaml.YAMLError, AttributeError):
        shown = {}
    banner, accent, font = (shown.get(k) if isinstance(shown, dict) else None for k in ("banner", "accent_colour", "font"))
    if not (isinstance(banner, str) and re.search(r"illustrative|synthetic", banner, re.IGNORECASE)):
        banner = FALLBACK["banner"]
    if not (isinstance(accent, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", accent)):
        accent = FALLBACK["accent_colour"]
    if not (isinstance(font, str) and re.fullmatch(r"[A-Za-z0-9 ]{1,40}", font)):
        font = FALLBACK["font"]
    return {"banner": banner, "accent_colour": accent, "font": font}


def css(display: dict) -> str:
    accent, font = display["accent_colour"], display["font"]
    stack = f"'{font}', Arial, sans-serif"
    return f"""
<style>
@font-face {{ font-family: '{font}'; src: local('{font}'), url('app/static/OpenSans.ttf') format('truetype'); font-weight: 300 800; }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp button, .stApp input,
.stApp textarea, .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"] {{ font-family: {stack}; }}
.stApp {{ color: {DARK}; }}
.block-container {{ padding-top: 1rem; max-width: 1200px; }}
h2, h3, h4 {{ font-weight: 700; color: {DARK}; }}
.sa-header {{ background: {DARK}; border-top: 4px solid {accent}; border-radius: 0 0 8px 8px; padding: 18px 26px; }}
.sa-header h1 {{ margin: 0; padding: 0; color: {WHITE}; font-size: 1.8rem; font-weight: 700; line-height: 1.2; }}
.sa-accent {{ font-style: italic; color: {NEON}; font-weight: 700; }}
.sa-header p {{ margin: 6px 0 0 0; color: {RULE}; font-size: 0.95rem; }}
.sa-banner {{ background: {accent}; color: #000000; padding: 8px 16px; font-weight: 700; border-radius: 0 0 4px 4px; margin-bottom: 10px; }}
.sa-status {{ border-left: 4px solid {accent}; padding: 2px 10px; color: {GREY_TEXT}; font-size: 0.88rem; margin: 2px 0 10px 0; }}
.sa-msg {{ border-left: 5px solid {RULE}; border-radius: 4px; padding: 6px 10px; margin: 2px 0 10px 0; font-size: 0.92rem; color: {DARK}; }}
.sa-msg b {{ font-weight: 700; margin-right: 6px; }}
.sa-count {{ font-weight: 600; }}
.stButton button {{ border: 2px solid {accent}; background: {WHITE}; color: {DARK}; font-weight: 700; }}
.stButton button:hover:not(:disabled) {{ background: {accent}; color: #000000; border-color: {accent}; }}
.stButton button:disabled {{ border-color: {RULE}; color: {GREY_TEXT}; }}
.stButton button[kind="primary"] {{ background: {accent}; color: #000000; }}
[data-testid="stExpander"] {{ border: 1px solid {RULE}; border-radius: 6px; }}
.sa-swatch {{ display: inline-block; width: 28px; height: 28px; border-radius: 50%; border: 1px solid {DARK}; vertical-align: middle; }}
</style>
"""


def apply(display: dict) -> None:
    st.set_page_config(page_title="Study setup", layout="wide")
    st.markdown(css(display), unsafe_allow_html=True)


def header() -> None:
    st.markdown('<div class="sa-header"><h1>Study <span class="sa-accent">setup</span></h1>'
                '<p>Describe a study screen by screen. This app checks, saves and previews a setup; it calculates no results.</p></div>',
                unsafe_allow_html=True)


def banner(text: str) -> None:
    st.markdown(f'<div class="sa-banner">{html.escape(text)}</div>', unsafe_allow_html=True)


def status(text: str) -> None:
    st.markdown(f'<div class="sa-status">{html.escape(text).replace("$", "&#36;")}</div>', unsafe_allow_html=True)


def message(level: str, text: str) -> None:
    """One message with its label written out as a word (Error, Warning or Note). What the person typed is escaped."""
    label, colour, tint = LEVELS[level]
    safe = html.escape(text).replace("$", "&#36;")      # a dollar sign would otherwise start a formula
    st.markdown(f'<div class="sa-msg" style="border-left-color:{colour};background:{tint}"><b>{label}:</b> {safe}</div>',
                unsafe_allow_html=True)


def swatch(colour: str) -> str:
    return f'<span class="sa-swatch" style="background:{html.escape(colour)}"></span>'
