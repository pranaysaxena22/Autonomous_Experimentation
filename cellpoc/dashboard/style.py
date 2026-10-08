"""Deloitte look and feel: palette, Open Sans, the dark header band, and the 'simulation with illustrative values' banner.

Presentation only. Colours come from the Deloitte brand palette (Together makes progress, June 2025):
  Deloitte Green #86BC25 (primary), Black, Neon Green #86EB22 (accent, on dark surfaces), Blue #00A3E0,
  Dark Gray #282728, light grays, and the supplemental amber and red the brand allows for status indicators.
Green is used for fills, borders and the one accent word, not for small text on white (it lacks contrast there);
on the dark header the accent word uses Neon Green, as the brand requires.
"""
from __future__ import annotations

import streamlit as st

# ---- brand palette
GREEN = "#86BC25"          # Deloitte Green: primary
NEON = "#86EB22"           # accent, for text on dark surfaces
BLUE = "#00A3E0"
BLUE_DARK = "#005587"
BLUE_LIGHT = "#A0DCFF"
LIME = "#B7E320"
DARK = "#282728"           # Dark Gray: text and dark surfaces
GREY_TEXT = "#555555"
RULE = "#E6E6E6"           # borders and grid lines
PAGE_ALT = "#F5F5F5"
WHITE = "#FFFFFF"
AMBER = "#E8A317"          # supplemental, for warnings
RED = "#DA291C"            # supplemental, for errors

FONT_STACK = "'Open Sans', Arial, sans-serif"
FALLBACK_BANNER = "Simulation with illustrative values"

# How a chart colours each kind of stretch (the run record says which kind each one is).
LOOK_COLOURS = {
    "Trial measured good": GREEN,
    "Trial measured not good": BLUE_LIGHT,
    "Fault: failed attempt": RED,
    "Fault: purge": AMBER,
    "Fault: retry recovered": BLUE,
    "Fault: retry failed": DARK,
    "Cleaning after a skipped candidate": BLUE_DARK,
}
PHASE_COLOURS = {"Sense": BLUE, "Reason": BLUE_DARK, "Act": GREEN, "Adapt": LIME}
SHADE_COLOURS = {"Staffed": WHITE, "Night": PAGE_ALT, "Weekend": RULE, "Unattended": PAGE_ALT}
STRATEGY_COLOURS = {"Adaptive": GREEN, "Fixed list": DARK, "Random": BLUE}

CSS = f"""
<style>
@font-face {{
  font-family: 'Open Sans';
  src: local('Open Sans'), local('OpenSans-Regular'), url('app/static/OpenSans.ttf') format('truetype');
  font-weight: 300 800;
}}
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp td, .stApp th, .stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricLabel"], .stApp [data-testid="stCaptionContainer"] {{
  font-family: {FONT_STACK};
}}
.stApp {{ color: {DARK}; }}
.block-container {{ padding-top: 1rem; max-width: 1400px; }}
h2, h3, h4 {{ font-weight: 700; color: {DARK}; }}

/* header band: dark surface, signature green rule, concentric rings (decoration only) */
.dl-header {{ position: relative; overflow: hidden; background: {DARK}; border-top: 4px solid {GREEN};
  border-radius: 0 0 8px 8px; padding: 22px 28px 20px 28px; margin-bottom: 0; }}
.dl-header h1 {{ margin: 0; padding: 0; color: {WHITE}; font-size: 2rem; font-weight: 700; line-height: 1.2; }}
.dl-accent-word {{ font-style: italic; color: {NEON}; font-weight: 700; }}
.dl-header p {{ margin: 6px 0 0 0; color: {RULE}; font-size: 0.95rem; }}
.dl-rings {{ position: absolute; right: -50px; top: -50px; width: 260px; height: 260px; opacity: 0.35; pointer-events: none; }}

.sim-banner {{ background: {GREEN}; color: #000000; padding: 8px 16px; font-weight: 700; border-radius: 0 0 4px 4px; margin-bottom: 8px; }}
.sim-stamp {{ border-left: 4px solid {GREEN}; padding: 2px 10px; color: {GREY_TEXT}; font-size: 0.85rem; margin: 2px 0 10px 0; }}

/* tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid {RULE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; color: {GREY_TEXT}; }}
.stTabs [aria-selected="true"] {{ color: {DARK}; }}

/* cards, metrics, buttons, expanders */
[data-testid="stMetric"] {{ background: {WHITE}; border: 1px solid {RULE}; border-left: 5px solid {GREEN}; border-radius: 6px; padding: 10px 16px; }}
[data-testid="stExpander"] {{ border: 1px solid {RULE}; border-radius: 6px; }}
.stButton button {{ border: 2px solid {GREEN}; background: {WHITE}; color: {DARK}; font-weight: 700; }}
.stButton button:hover:not(:disabled) {{ background: {GREEN}; color: #000000; border-color: {GREEN}; }}
.stButton button:disabled {{ border-color: {RULE}; color: {GREY_TEXT}; }}

/* stations */
.tile {{ border: 1px solid {RULE}; border-left: 6px solid {RULE}; border-radius: 6px; padding: 8px 10px; min-height: 84px; background: {WHITE}; }}
.tile-title {{ font-weight: 700; font-size: 0.95rem; color: {DARK}; }}
.tile-text {{ font-size: 0.85rem; margin-top: 4px; color: {DARK}; }}
.tile-working {{ border-left-color: {GREEN}; background: rgba(134, 188, 37, 0.12); }}
.tile-purge {{ border-left-color: {RED}; background: rgba(218, 41, 28, 0.08); }}
.tile-retry {{ border-left-color: {AMBER}; background: rgba(232, 163, 23, 0.12); }}

/* Sense / Reason / Act / Adapt */
.phase {{ border: 1px solid {RULE}; border-radius: 6px; padding: 8px 10px; text-align: center; font-weight: 700; background: {WHITE}; color: {GREY_TEXT}; }}
.phase-active {{ background: {GREEN}; border-color: {GREEN}; color: #000000; }}
.phase-done {{ background: rgba(134, 188, 37, 0.14); border-color: {GREEN}; color: {DARK}; }}
.phase-failed {{ background: rgba(218, 41, 28, 0.10); border-color: {RED}; color: {DARK}; }}
.phase-not_reached {{ border-style: dashed; color: {GREY_TEXT}; }}

.lab-badge {{ display: inline-block; padding: 6px 14px; border-radius: 16px; font-weight: 700; }}
.lab-in {{ background: rgba(134, 188, 37, 0.18); border: 2px solid {GREEN}; color: {DARK}; }}
.lab-out {{ background: {DARK}; border: 2px solid {DARK}; color: {WHITE}; }}
</style>
"""

RINGS = (f'<svg class="dl-rings" viewBox="0 0 200 200">'
         f'<circle cx="100" cy="100" r="92" fill="none" stroke="{GREEN}" stroke-width="1.5"/>'
         f'<circle cx="100" cy="100" r="68" fill="none" stroke="{NEON}" stroke-width="1.5"/>'
         f'<circle cx="100" cy="100" r="44" fill="none" stroke="{BLUE}" stroke-width="1.5"/>'
         f'</svg>')


def apply() -> None:
    """Page settings and fonts. Must run before anything else is drawn."""
    st.set_page_config(page_title="Autonomous formulation cell", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def header() -> None:
    """The dark title band with its green top rule. One italic accent word, as the brand allows."""
    st.markdown(f'<div class="dl-header">{RINGS}<h1>Autonomous <span class="dl-accent-word">formulation</span> cell</h1>'
                '<p>A multi-day unattended run of a tablet formulation cell, shown moment by moment.</p></div>',
                unsafe_allow_html=True)


def banner(text: str) -> None:
    st.markdown(f'<div class="sim-banner">{text}</div>', unsafe_allow_html=True)


def stamp(text: str) -> None:
    """A small reminder at the top of every page."""
    st.markdown(f'<div class="sim-stamp">{text}</div>', unsafe_allow_html=True)


def chart(figure) -> None:
    """Show an Altair chart in the brand's font and colours: dark text, light grid lines, no frame."""
    styled = (figure.configure(font=FONT_STACK)
              .configure_axis(labelColor=DARK, titleColor=DARK, gridColor=RULE, domainColor=RULE, tickColor=RULE)
              .configure_legend(labelColor=DARK, titleColor=DARK)
              .configure_title(font=FONT_STACK, fontSize=14, color=DARK, anchor="start")
              .configure_view(strokeWidth=0))
    st.altair_chart(styled, theme=None, width="stretch")
