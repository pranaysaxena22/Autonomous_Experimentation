"""Colours, fonts and the 'simulation with illustrative values' banner. Presentation only."""
from __future__ import annotations

import streamlit as st

GREEN = "#86BC25"                       # Deloitte green
FONT_STACK = "'Open Sans', Arial, sans-serif"
FALLBACK_BANNER = "Simulation with illustrative values"

# How a chart colours each kind of stretch (the run record says which kind each one is).
LOOK_COLOURS = {
    "Trial measured good": GREEN,
    "Trial measured not good": "#9AA5B1",
    "Fault: failed attempt": "#D0021B",
    "Fault: purge": "#F5A623",
    "Fault: retry recovered": "#B8860B",
    "Fault: retry failed": "#8B0000",
    "Cleaning after a skipped candidate": "#6C7A89",
}
PHASE_COLOURS = {"Act": GREEN, "Sense": "#0097A9", "Reason": "#005587", "Adapt": "#C4D600"}
SHADE_COLOURS = {"Staffed": "#FFFFFF", "Night": "#DDE1E6", "Weekend": "#C3C9D1", "Unattended": "#DDE1E6"}
STRATEGY_COLOURS = {"Adaptive": GREEN, "Fixed list": "#404040", "Random": "#A0A0A0"}

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
.sim-banner {{ background: {GREEN}; color: #000; padding: 10px 16px; font-weight: 700; border-radius: 4px; margin-bottom: 6px; }}
.sim-stamp {{ border-left: 4px solid {GREEN}; padding: 2px 10px; color: #333; font-size: 0.85rem; margin: 2px 0 10px 0; }}
.tile {{ border: 2px solid #C3C9D1; border-radius: 6px; padding: 8px 10px; min-height: 84px; background: #FAFAFA; }}
.tile-title {{ font-weight: 700; font-size: 0.95rem; }}
.tile-text {{ font-size: 0.85rem; margin-top: 4px; }}
.tile-working {{ border-color: {GREEN}; background: #EEF6DC; }}
.tile-purge {{ border-color: #D0021B; background: #FDE8EA; }}
.tile-retry {{ border-color: #F5A623; background: #FEF3DF; }}
.phase {{ border: 2px solid #C3C9D1; border-radius: 6px; padding: 8px 10px; text-align: center; font-weight: 700; background: #FAFAFA; color: #666; }}
.phase-active {{ background: {GREEN}; border-color: {GREEN}; color: #000; }}
.phase-done {{ background: #EEF6DC; border-color: {GREEN}; color: #333; }}
.phase-failed {{ background: #FDE8EA; border-color: #D0021B; color: #8B0000; }}
.phase-not_reached {{ border-style: dashed; color: #999; }}
.lab-badge {{ display: inline-block; padding: 6px 14px; border-radius: 16px; font-weight: 700; }}
.lab-in {{ background: #EEF6DC; border: 2px solid {GREEN}; }}
.lab-out {{ background: #E8EAEE; border: 2px solid #6C7A89; }}
</style>
"""


def apply() -> None:
    """Page settings and fonts. Must run before anything else is drawn."""
    st.set_page_config(page_title="Autonomous formulation cell", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def banner(text: str) -> None:
    st.markdown(f'<div class="sim-banner">{text}</div>', unsafe_allow_html=True)


def stamp(text: str) -> None:
    """A small reminder at the top of every page."""
    st.markdown(f'<div class="sim-stamp">{text}</div>', unsafe_allow_html=True)


def chart(figure) -> None:
    """Show an Altair chart in this dashboard's font, with its own colours."""
    st.altair_chart(figure.configure(font=FONT_STACK).configure_title(font=FONT_STACK, fontSize=14),
                    theme=None, width="stretch")
