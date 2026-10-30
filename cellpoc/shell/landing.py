"""The front page of the client view, laid out like a product page: what this is, the challenge, the solution, how one trial works, the proof, and where to go next.

Fixed text and styling only. Every number on it comes from the run record (the headline cards, drawn by cellpoc.dashboard.client_results) or is named as an assumption. Colours are the Deloitte palette; Open Sans; circles as the one motif.
The same pieces (the challenge, the solution) are used by the welcome window (cellpoc/shell/tour.py), so the two never disagree.
"""
from __future__ import annotations

import html

import streamlit as st

GREEN, NEON, BLACK, DARK, WHITE, SOFT, EDGE, BLUE = "#86BC25", "#86EB22", "#000000", "#282728", "#FFFFFF", "#E6E6E6", "#555555", "#00A3E0"
HERO_IMAGE = "app/static/cell_hero.jpg"          # the app serves the static folder (the font is served the same way); made by tools/make_hero_image.py

CHALLENGE = [
    ("9", "experiments a week", "What a team can run by hand. This is an assumption: replace it with your own figure."),
    ("8 h", "a day, five days a week", "Typical working hours. Nights and weekends are lost, so good recipes wait."),
    ("By eye", "every bottle, every tablet", "Which bottle, how full, is the tablet damaged: each one is checked by a person."),
]
SOLUTION = [
    ("1", "A robot does the lab work", "The arm weighs, mixes, presses and tests tablets, trial after trial, with nobody in the lab."),
    ("2", "Cameras check everything", "Every ingredient bottle is identified by its barcode and printed name and its liquid is checked; every pressed tablet is inspected."),
    ("3", "An engine chooses what to try next", "Each new recipe comes from the results so far. Faults are handled, and the morning team gets a handover."),
]
FLOW = [
    ("Sense", "Reads the instruments"),
    ("Reason", "Chooses the next recipe"),
    ("Act", "Makes and tests the tablets"),
    ("Adapt", "Recovers from faults, then hands over"),
]
EXPLORE = [
    ("cellpoc/shell/pages/live_run.py", "Live run", "Watch the cell work, with the camera checks as they happen.", ":material/play_circle:"),
    ("cellpoc/shell/pages/results.py", "Results at a glance", "Charts of what the run delivered and what happened overnight.", ":material/insights:"),
    ("cellpoc/shell/pages/vision.py", "Vision", "See the cell's camera read the liquids in a picture.", ":material/photo_camera:"),
    ("cellpoc/shell/pages/setup.py", "Setup", "Describe your own study, ingredient by ingredient.", ":material/tune:"),
]

CSS = f"""<style>
@keyframes lp-pulse {{ 0%, 100% {{ box-shadow: 0 0 0 0 rgba(134,188,37,0); }} 50% {{ box-shadow: 0 0 0 9px rgba(134,188,37,0.28), 0 0 26px 4px rgba(134,188,37,0.35); }} }}
@keyframes lp-rise {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: none; }} }}
.lp-wrap {{ animation: lp-rise 0.5s ease-out both; }}
.lp-hero {{ position: relative; overflow: hidden; display: grid; grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr); gap: 32px; align-items: center;
  background: linear-gradient(125deg, {BLACK} 0%, {DARK} 100%); border: 1px solid {EDGE}; border-radius: 18px; padding: 40px 40px; margin: 2px 0 18px 0; }}
.lp-hero::after {{ content: ""; position: absolute; left: -120px; bottom: -150px; width: 380px; height: 380px; border-radius: 50%;
  background: repeating-radial-gradient(circle, transparent 0 42px, rgba(134,188,37,0.2) 42px 43px); pointer-events: none; }}
.lp-eyebrow {{ position: relative; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; color: {GREEN}; }}
.stApp .lp-hero h1 {{ position: relative; margin: 10px 0 14px 0; padding: 0; font-size: 2.9rem; line-height: 1.08; font-weight: 700; letter-spacing: -0.025em; color: {WHITE}; }}
.stApp .lp-hero h1 em {{ font-style: italic; color: {NEON}; }}
.stApp .lp-lead {{ position: relative; margin: 0 0 18px 0; font-size: 1.12rem; line-height: 1.55; color: {SOFT}; max-width: 560px; }}
.lp-pills {{ position: relative; display: flex; flex-wrap: wrap; gap: 8px; }}
.stApp .lp-pill {{ border: 1px solid {EDGE}; border-radius: 999px; padding: 4px 14px; font-size: 0.82rem; font-weight: 600; color: {SOFT}; background: {BLACK}; }}
.lp-shot {{ position: relative; border-radius: 14px; overflow: hidden; border: 1px solid {EDGE}; box-shadow: 0 10px 30px rgba(0,0,0,0.6); background: {BLACK}; }}
.lp-shot img {{ display: block; width: 100%; height: auto; }}
.lp-duo {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 0 0 14px; text-align: left; }}
.lp-duo-col {{ background: {DARK}; border: 1px solid {EDGE}; border-top: 3px solid {EDGE}; border-radius: 12px; padding: 14px 16px; }}
.lp-duo-col.lp-duo-gain {{ border-top-color: {GREEN}; }}
.stApp .lp-duo-col p {{ margin: 4px 0 0; font-size: 0.92rem; line-height: 1.5; color: {SOFT}; }}
.lp-section {{ margin: 46px 0 14px 0; }}
.lp-section .lp-eyebrow {{ display: block; }}
.stApp .lp-section h2 {{ margin: 6px 0 6px 0; padding: 0; font-size: 1.85rem; line-height: 1.18; letter-spacing: -0.015em; font-weight: 700; color: {WHITE}; }}
.stApp .lp-section p {{ margin: 0; max-width: 780px; color: {SOFT}; font-size: 1.02rem; line-height: 1.55; }}
.lp-grid3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 6px 0 0 0; }}
.lp-grid4 {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; margin: 6px 0 0 0; }}
.lp-tile {{ background: {DARK}; border: 1px solid {EDGE}; border-radius: 14px; padding: 22px 22px 20px; }}
.lp-tile.lp-pain {{ border-top: 3px solid {EDGE}; }}
.lp-tile.lp-gain {{ border-top: 3px solid {GREEN}; }}
.stApp .lp-big {{ font-size: 2.3rem; font-weight: 700; line-height: 1.05; letter-spacing: -0.02em; color: {WHITE}; }}
.stApp .lp-tile h3 {{ margin: 10px 0 6px; padding: 0; font-size: 1.12rem; line-height: 1.25; font-weight: 700; color: {WHITE}; }}
.stApp .lp-tile .lp-label {{ font-size: 1rem; font-weight: 700; color: {WHITE}; margin: 4px 0 6px; }}
.stApp .lp-tile p {{ margin: 0; color: {SOFT}; font-size: 0.92rem; line-height: 1.5; opacity: 0.92; }}
.lp-num {{ width: 40px; height: 40px; border-radius: 50%; border: 2px solid {GREEN}; display: flex; align-items: center; justify-content: center; font-weight: 800; color: {NEON}; background: {BLACK}; font-size: 1.05rem; }}
.stApp .lp-num {{ color: {NEON}; }}
.lp-flow-step {{ position: relative; text-align: center; padding: 6px 14px 0; }}
.lp-flow-step::before {{ content: ""; position: absolute; top: 25px; left: -50%; width: 100%; height: 2px; background: linear-gradient(90deg, transparent, {GREEN}); z-index: 0; }}
.lp-flow-step:first-child::before {{ display: none; }}
.lp-flow-step .lp-num {{ position: relative; z-index: 1; margin: 0 auto 10px; width: 50px; height: 50px; font-size: 1.15rem; }}
.stApp .lp-flow-name {{ font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; font-size: 0.95rem; color: {WHITE}; }}
.stApp .lp-flow-text {{ font-size: 0.88rem; color: {SOFT}; margin-top: 2px; }}
.stApp .lp-foot {{ margin: 22px 0 0; font-size: 0.82rem; color: {SOFT}; opacity: 0.8; }}
.lp-explore {{ background: {DARK}; border: 1px solid {EDGE}; border-left: 4px solid {GREEN}; border-radius: 12px; padding: 16px 18px 14px; min-height: 138px; margin-bottom: 10px; }}
.stApp .lp-explore h4 {{ margin: 0 0 4px; padding: 0; font-size: 1.05rem; color: {WHITE}; }}
.stApp .lp-explore p {{ margin: 0; font-size: 0.88rem; color: {SOFT}; }}
/* the buttons that are links to pages */
[data-testid="stPageLink"] a {{ background: transparent; border: 1.5px solid {GREEN}; border-radius: 999px; padding: 6px 18px; font-weight: 700; text-decoration: none; transition: background 0.15s; width: fit-content; }}
[data-testid="stPageLink"] a, [data-testid="stPageLink"] a * {{ color: {WHITE}; }}
[data-testid="stPageLink"] a:hover {{ background: rgba(134,188,37,0.22); }}
.st-key-lp_cta [data-testid="stColumn"]:first-child [data-testid="stPageLink"] a {{ background: {GREEN}; padding: 11px 28px; font-size: 1.02rem; animation: lp-pulse 2s ease-in-out 3; }}
.st-key-lp_cta [data-testid="stColumn"]:first-child [data-testid="stPageLink"] a, .st-key-lp_cta [data-testid="stColumn"]:first-child [data-testid="stPageLink"] a * {{ color: {BLACK}; }}
.st-key-lp_cta [data-testid="stColumn"]:first-child [data-testid="stPageLink"] a:hover {{ background: {NEON}; }}
.lp-pagehead {{ margin: 6px 0 16px; }}
.lp-pagehead .lp-eyebrow {{ display: block; }}
.stApp .lp-pagehead h1 {{ margin: 4px 0 6px; padding: 0; font-size: 2.1rem; line-height: 1.12; letter-spacing: -0.02em; font-weight: 700; color: {WHITE}; }}
.stApp .lp-pagehead p {{ margin: 0; max-width: 780px; font-size: 1.02rem; line-height: 1.5; color: {SOFT}; }}
.lp-panels {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
.lp-panel {{ background: {DARK}; border: 1px solid {EDGE}; border-radius: 14px; padding: 20px 24px 8px; border-top: 3px solid {GREEN}; }}
.lp-panel.lp-panel-no {{ border-top-color: {EDGE}; }}
.stApp .lp-panel h3 {{ margin: 0 0 10px; padding: 0; font-size: 1.15rem; color: {WHITE}; }}
.lp-panel ul {{ list-style: none; margin: 0; padding: 0; }}
.lp-panel li {{ position: relative; padding: 0 0 14px 22px; font-size: 0.95rem; line-height: 1.5; color: {SOFT}; }}
.lp-panel li::before {{ content: ""; position: absolute; left: 0; top: 7px; width: 9px; height: 9px; border-radius: 50%; background: {GREEN}; }}
.lp-panel.lp-panel-no li::before {{ background: {EDGE}; }}
@media (max-width: 900px) {{ .lp-panels {{ grid-template-columns: minmax(0, 1fr); }} }}
.lp-ready {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr); gap: 28px; align-items: center; background: linear-gradient(125deg, {BLACK} 0%, {DARK} 100%); border: 1px solid {EDGE}; border-radius: 16px; padding: 28px 30px; margin: 4px 0 14px; }}
.stApp .lp-ready h3 {{ margin: 6px 0 12px; padding: 0; font-size: 1.5rem; color: {WHITE}; }}
.lp-ready ol {{ list-style: none; margin: 0; padding: 0; counter-reset: lp; }}
.lp-ready li {{ position: relative; counter-increment: lp; padding: 0 0 12px 44px; font-size: 0.97rem; line-height: 1.45; color: {SOFT}; }}
.lp-ready li::before {{ content: counter(lp); position: absolute; left: 0; top: -2px; width: 30px; height: 30px; border-radius: 50%; border: 2px solid {GREEN}; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.85rem; color: {NEON}; background: {BLACK}; }}
.stApp .lp-ready li b {{ color: {WHITE}; }}
@media (max-width: 900px) {{ .lp-ready {{ grid-template-columns: minmax(0, 1fr); }} }}
@media (max-width: 900px) {{ .lp-duo {{ grid-template-columns: minmax(0, 1fr); }} }}
@media (max-width: 1000px) {{ .lp-hero {{ grid-template-columns: minmax(0, 1fr); padding: 28px; }} .lp-grid3, .lp-grid4 {{ grid-template-columns: minmax(0, 1fr); gap: 14px; }} .lp-flow-step::before {{ display: none; }} .stApp .lp-hero h1 {{ font-size: 2.2rem; }} }}
@media (prefers-reduced-motion: reduce) {{ .lp-wrap, .st-key-lp_cta [data-testid="stColumn"]:first-child [data-testid="stPageLink"] a {{ animation: none; }} }}
/* the welcome window: a readable title */
[data-testid="stDialog"] [role="dialog"] h2, [data-testid="stDialog"] [role="dialog"] [data-testid="stHeading"] {{ color: {SOFT}; font-size: 0.9rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }}
/* the client view hides the web framework's own toolbar and footer */
[data-testid="stToolbar"], [data-testid="stDeployButton"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
</style>"""


def page_header(eyebrow: str, title: str, text: str = "") -> str:
    """The heading of a client page: a small label, the title, one line saying what the page is for."""
    body = f"<p>{html.escape(text)}</p>" if text else ""
    return f'<div class="lp-pagehead"><span class="lp-eyebrow">{html.escape(eyebrow)}</span><h1>{html.escape(title)}</h1>{body}</div>'


def section(eyebrow: str, title: str, text: str = "") -> str:
    body = f"<p>{html.escape(text)}</p>" if text else ""
    return f'<div class="lp-section"><span class="lp-eyebrow">{html.escape(eyebrow)}</span><h2>{title}</h2>{body}</div>'


def hero_html(image_url: str = HERO_IMAGE) -> str:
    return ('<div class="lp-wrap lp-hero"><div>'
            '<div class="lp-eyebrow">Autonomous experimentation &middot; tablet formulation</div>'
            '<h1>Experiments that run <em>themselves</em>, day and night</h1>'
            '<p class="lp-lead">An autonomous lab station that makes, tests and learns from tablet recipes by itself, and checks every ingredient bottle and every tablet with its own cameras.</p>'
            '<div class="lp-pills"><span class="lp-pill">Robot arm</span><span class="lp-pill">Computer vision</span><span class="lp-pill">Decision engine</span></div></div>'
            f'<div class="lp-shot"><img src="{html.escape(image_url)}" alt="The simulated cell: a robot arm among the balance, press and testing instruments"></div></div>')


def challenge_html() -> str:
    tiles = "".join(f'<div class="lp-tile lp-pain"><div class="lp-big">{html.escape(big)}</div><div class="lp-label">{html.escape(label)}</div><p>{html.escape(text)}</p></div>' for big, label, text in CHALLENGE)
    return section("The challenge", "Formulating a tablet is slow, manual and stops at the end of the working day",
                   "Finding a recipe that dissolves and holds together means many rounds of trial and error, and each round waits for people.") + f'<div class="lp-grid3">{tiles}</div>'


def solution_html() -> str:
    tiles = "".join(f'<div class="lp-tile lp-gain"><div class="lp-num">{html.escape(n)}</div><h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>' for n, title, text in SOLUTION)
    return section("The solution", "A robotic station that keeps working through the night",
                   "One compact cell: an arm, the instruments, cameras and a decision engine, working as a single loop.") + f'<div class="lp-grid3">{tiles}</div>'


def flow_html() -> str:
    steps = "".join(f'<div class="lp-flow-step"><div class="lp-num">{n}</div><div class="lp-flow-name">{html.escape(name)}</div><div class="lp-flow-text">{html.escape(text)}</div></div>' for n, (name, text) in enumerate(FLOW, start=1))
    return section("How it works", "One loop, repeated for every trial") + f'<div class="lp-grid4">{steps}</div>'


def live_ready_html(image_url: str = HERO_IMAGE) -> str:
    """What the Live run page shows before the live demo is started: how to run it, beside the cell."""
    steps = ("<li><b>Press Start the live demo</b> below and wait a few seconds.</li>"
             "<li><b>Press Start the run</b> inside the live view. Simulated time runs faster than real time: the Speed menu changes how fast.</li>"
             "<li><b>Watch the arm work</b> and the camera check every ingredient bottle and every tablet: a green frame is right, red is wrong.</li>"
             "<li><b>Try a Demo scenario</b> to show the camera a wrong bottle or a defective tablet.</li>")
    return (f'<div class="lp-ready"><div><span class="lp-eyebrow">How to run it</span><h3>Watch the cell work</h3><ol>{steps}</ol></div>'
            f'<div class="lp-shot"><img src="{html.escape(image_url)}" alt="The simulated cell"></div></div>')


def explore_card(title: str, text: str) -> str:
    return f'<div class="lp-explore"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>'


def render_top() -> None:
    """The opening of the front page: the hero, a line under the picture, and the two buttons under it."""
    st.markdown(hero_html(), unsafe_allow_html=True)
    with st.container(key="lp_cta"):
        first, second, spare = st.columns([1.1, 1, 3])
        first.page_link("cellpoc/shell/pages/live_run.py", label="Start the live demo", icon=":material/play_circle:")
        second.page_link("cellpoc/shell/pages/results.py", label="See the results", icon=":material/insights:")


def render_story() -> None:
    """The challenge, the solution and how one trial works."""
    st.markdown(challenge_html(), unsafe_allow_html=True)
    st.markdown(solution_html(), unsafe_allow_html=True)
    st.markdown(flow_html(), unsafe_allow_html=True)


def render_explore() -> None:
    """Where to go next: four cards, each with its button."""
    st.markdown(section("Explore", "See it for yourself"), unsafe_allow_html=True)
    for column, (path, title, text, icon) in zip(st.columns(4), EXPLORE):
        column.markdown(explore_card(title, text), unsafe_allow_html=True)
        column.page_link(path, label=f"Open {title}", icon=icon)
