"""The dark Deloitte look of the unified app: Black page, Dark Gray panels, Deloitte Green accents, Open Sans.

Presentation only. Colours come from the Deloitte palette (the same list the dashboard uses). Green is used for fills, rules and edges, and Neon Green only
for the one accent word on a dark surface; text is white or light gray, never green on a dark panel at small size.
It is loaded after the dashboard's own style sheet, so the dashboard's pages (which are drawn for a light page) pick up the dark surfaces without being changed.
"""
from __future__ import annotations

import html

import streamlit as st

GREEN = "#86BC25"
NEON = "#86EB22"
BLUE = "#00A3E0"
BLACK = "#000000"
DARK = "#282728"
WHITE = "#FFFFFF"
SOFT = "#E6E6E6"
GREY_EDGE = "#555555"
AMBER = "#E8A317"
RED = "#DA291C"

CSS = f"""
<style>
/* page and panels: Black page, Dark Gray panels, thin gray edges */
.stApp {{ background: {BLACK}; color: {WHITE}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1rem; padding-bottom: 3rem; max-width: 1500px; }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp td, .stApp th,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricLabel"] {{ color: {WHITE}; }}
.stApp h2, .stApp h3, .stApp h4 {{ color: {WHITE}; }}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ color: {SOFT}; opacity: 0.8; }}
.stApp a {{ color: {BLUE}; }}
.stApp hr {{ border-color: {GREY_EDGE}; }}

/* the left menu */
[data-testid="stSidebar"] {{ background: {DARK}; border-right: 1px solid {GREY_EDGE}; }}
[data-testid="stSidebar"] * {{ color: {SOFT}; }}
[data-testid="stSidebarNavLink"] {{ border-radius: 8px; border-left: 3px solid transparent; padding-left: 10px; }}
[data-testid="stSidebarNavLink"]:hover {{ background: rgba(255, 255, 255, 0.07); }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{ background: rgba(134, 188, 37, 0.16); border-left: 3px solid {GREEN}; }}
[data-testid="stSidebarNavLink"][aria-current="page"] * {{ color: {WHITE}; font-weight: 700; }}
[data-testid="stNavSectionHeader"] {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.72rem; opacity: 0.7; }}

/* the top bar: brand on the left, status chips on the right */
.ub-bar {{ position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  background: {DARK}; border: 1px solid {GREY_EDGE}; border-top: 4px solid {GREEN}; border-radius: 10px; padding: 12px 20px; margin-bottom: 16px; }}
.ub-bar::after {{ content: ""; position: absolute; right: -70px; top: -120px; width: 280px; height: 280px; border-radius: 50%;
  background: repeating-radial-gradient(circle, transparent 0 34px, rgba(134, 188, 37, 0.22) 34px 35px); pointer-events: none; }}
.ub-brand {{ position: relative; font-size: 1.35rem; font-weight: 700; color: {WHITE}; letter-spacing: -0.005em; }}
.ub-accent {{ font-style: italic; color: {NEON}; font-weight: 700; }}
.ub-chips {{ position: relative; display: flex; gap: 8px; flex-wrap: wrap; z-index: 1; }}
.ub-chip {{ border: 1px solid {GREY_EDGE}; border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600; color: {SOFT}; background: {BLACK}; }}
.ub-chip-label {{ background: {GREEN}; border-color: {GREEN}; color: {BLACK}; font-weight: 800; letter-spacing: 0.04em; }}
.stApp .ub-brand {{ color: {WHITE}; }}
.stApp .ub-accent {{ color: {NEON}; }}
.stApp .ub-chip {{ color: {SOFT}; }}
.stApp .ub-chip-label {{ color: {BLACK}; }}
.stApp .ub-num {{ color: {NEON}; }}

/* panels and cards */
.ub-card {{ background: {DARK}; border: 1px solid {GREY_EDGE}; border-left: 4px solid {GREEN}; border-radius: 10px; padding: 14px 20px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.5); margin-bottom: 8px; }}
.stApp .ub-card h4 {{ margin: 0 0 4px 0; padding: 0; font-size: 1.02rem; }}
.stApp .ub-card p {{ margin: 0; color: {SOFT}; font-size: 0.9rem; }}
.ub-card.ub-quiet {{ border-left-color: {GREY_EDGE}; }}
.ub-card.ub-warn {{ border-left-color: {AMBER}; }}
.ub-card.ub-bad {{ border-left-color: {RED}; }}
.ub-step {{ display: flex; gap: 16px; align-items: center; }}
.ub-num {{ flex: 0 0 38px; width: 38px; height: 38px; border-radius: 50%; background: {BLACK}; border: 1px solid {GREEN}; color: {NEON}; font-weight: 800; display: flex; align-items: center; justify-content: center; }}
[data-testid="stMetric"] {{ background: {DARK}; border: 1px solid {GREY_EDGE}; border-left: 5px solid {GREEN}; border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.5); }}
[data-testid="stExpander"] {{ background: {DARK}; border: 1px solid {GREY_EDGE}; border-radius: 10px; }}
[data-testid="stAlert"] {{ border-radius: 10px; }}

/* the Overview's opening: a headline, the loop the cell repeats, the honesty cards */
.ub-hero {{ position: relative; overflow: hidden; background: linear-gradient(120deg, {BLACK} 0%, {DARK} 100%); border: 1px solid {GREY_EDGE}; border-radius: 14px; padding: 34px 40px; margin: 4px 0 14px 0; }}
.ub-hero::after {{ content: ""; position: absolute; right: -90px; top: -110px; width: 360px; height: 360px; border-radius: 50%;
  background: repeating-radial-gradient(circle, transparent 0 40px, rgba(134, 188, 37, 0.28) 40px 41px); pointer-events: none; }}
.stApp .ub-hero h1 {{ position: relative; margin: 6px 0 10px 0; padding: 0; font-size: 2.1rem; line-height: 1.15; font-weight: 700; letter-spacing: -0.015em; max-width: 900px; }}
.stApp .ub-hero p {{ position: relative; margin: 0; max-width: 760px; font-size: 1.05rem; color: {SOFT}; }}
.stApp .ub-eyebrow {{ position: relative; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {GREEN}; }}
.ub-loop {{ display: flex; gap: 0; margin: 4px 0 4px 0; }}
.ub-loop-step {{ position: relative; flex: 1 1 0; background: {DARK}; border: 1px solid {GREY_EDGE}; border-top: 3px solid {GREEN}; padding: 14px 18px 14px 22px; margin-right: 14px; border-radius: 4px 10px 10px 4px; }}
.ub-loop-step::after {{ content: ""; position: absolute; right: -15px; top: 50%; margin-top: -9px; width: 0; height: 0; border-style: solid; border-width: 9px 0 9px 12px; border-color: transparent transparent transparent {GREEN}; }}
.ub-loop-step:last-child {{ margin-right: 0; }}
.ub-loop-step:last-child::after {{ display: none; }}
.stApp .ub-loop-name {{ font-weight: 700; font-size: 1.05rem; letter-spacing: 0.06em; text-transform: uppercase; color: {WHITE}; margin-bottom: 4px; }}
.stApp .ub-loop-text {{ font-size: 0.86rem; color: {SOFT}; }}
.stApp .ub-loop-caption {{ font-size: 0.8rem; color: {SOFT}; opacity: 0.75; margin: 4px 0 18px 2px; }}
.ub-card.ub-tall {{ min-height: 168px; }}
.ub-card.ub-card-green {{ border-left-color: {NEON}; }}
[data-testid="stMetricLabel"] p {{ white-space: normal; overflow: visible; text-overflow: clip; font-size: 0.82rem; }}
[data-testid="stMetricLabel"] {{ min-height: 2.4em; align-items: flex-end; }}

/* the headline cards and the section headings of the Results page */
.ub-kpi {{ min-height: 170px; background: linear-gradient(160deg, {DARK} 0%, {BLACK} 100%); border: 1px solid {GREY_EDGE}; border-top: 4px solid {GREEN}; border-radius: 12px; padding: 18px 20px 16px 20px; box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5); }}
.stApp .ub-kpi-value {{ font-size: 2.6rem; font-weight: 700; line-height: 1.05; letter-spacing: -0.02em; color: {NEON}; }}
.stApp .ub-kpi-label {{ margin-top: 6px; font-size: 1rem; font-weight: 700; color: {WHITE}; line-height: 1.25; }}
.stApp .ub-kpi-note {{ margin-top: 6px; font-size: 0.8rem; color: {SOFT}; opacity: 0.8; line-height: 1.3; }}
.ub-section {{ margin: 26px 0 6px 0; padding-left: 14px; border-left: 4px solid {GREEN}; }}
.stApp .ub-section h3 {{ margin: 0 0 4px 0; padding: 0; font-size: 1.35rem; }}
.stApp .ub-section p {{ margin: 0; max-width: 960px; color: {SOFT}; font-size: 0.95rem; }}
[class*="st-key-darkchart"] [data-testid="stArrowVegaLiteChart"], [class*="st-key-darkchart"] [data-testid="stVegaLiteChart"] {{ background: {DARK}; border: 1px solid {GREY_EDGE}; border-radius: 12px; padding: 8px 10px; }}

/* the setup screens' messages and status line (their own style sheet is for a light page) */
.stApp .sa-msg, .stApp .sa-msg b {{ color: {WHITE}; }}
.stApp .sa-status {{ color: {SOFT}; }}
.stApp .sa-count {{ color: {WHITE}; }}

/* what the dashboard's pages draw for a light page: dark panels instead of white ones */
.sim-stamp {{ border-left: 3px solid {GREEN}; color: {SOFT}; }}
.tile {{ background: {DARK}; border-color: {GREY_EDGE}; }}
.tile-title, .tile-text {{ color: {WHITE}; }}
.tile-working {{ background: rgba(134, 188, 37, 0.18); }}
.phase {{ background: {DARK}; border-color: {GREY_EDGE}; color: {SOFT}; }}
.phase-active {{ background: {GREEN}; color: {BLACK}; }}
.phase-done {{ background: rgba(134, 188, 37, 0.18); color: {WHITE}; }}
.phase-failed {{ background: rgba(218, 41, 28, 0.25); color: {WHITE}; }}
.lab-out {{ background: {BLACK}; border-color: {GREY_EDGE}; color: {WHITE}; }}
.lab-in {{ color: {WHITE}; }}
.stButton button, .stDownloadButton button {{ background: {DARK}; color: {WHITE}; }}
.stButton button:hover:not(:disabled), .stDownloadButton button:hover:not(:disabled) {{ background: {GREEN}; color: {BLACK}; }}
.stButton button p {{ white-space: normal; overflow: visible; text-overflow: clip; }}
.stButton button:disabled {{ opacity: 0.45; }}
.stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid {GREY_EDGE}; }}
.stTabs [data-baseweb="tab"] {{ color: {SOFT}; }}
.stTabs [aria-selected="true"] {{ color: {WHITE}; }}
/* charts are drawn for a light page (dark text), so each sits on a white card */
[data-testid="stArrowVegaLiteChart"], [data-testid="stVegaLiteChart"] {{ background: {WHITE}; border-radius: 10px; padding: 12px; }}
</style>
"""


def topbar(run_name: str, trials: int, developer: bool = False) -> None:
    """The slim bar across the top. Everything on it is read from the run record; the label chip is always there. The developer view adds the trial count, the offline chip and a chip that says it is the developer view."""
    more = (f'<span class="ub-chip" data-chip="trials">{trials} trials attempted</span><span class="ub-chip" data-chip="offline">OFFLINE</span><span class="ub-chip" data-chip="developer">DEVELOPER VIEW</span>') if developer else ""
    st.markdown(f'<div class="ub-bar"><div class="ub-brand">Autonomous <span class="ub-accent">formulation</span> cell</div>'
                f'<div class="ub-chips"><span class="ub-chip ub-chip-label" data-chip="label">ILLUSTRATIVE</span>'
                f'<span class="ub-chip" data-chip="run">{html.escape(run_name)}</span>{more}</div></div>', unsafe_allow_html=True)
