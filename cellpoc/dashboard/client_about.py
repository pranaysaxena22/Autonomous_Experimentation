"""The client view's About page: a plain summary of what the demo shows and does not show, for the people the demo is for.

The full limitations (written once, in cellpoc/about_text.py, and carried in every run record) are in the developer view and in the reports; these lines must never say more than they do.
(This is its own file, not part of the proof of concept's About page, which stays exactly as it was.)
"""
from __future__ import annotations

import html

import streamlit as st

from . import style

CLIENT_SHOWS = (
    "A robotic lab station that makes and tests tablets by itself, trial after trial, day and night.",
    "How the cell chooses its next recipe, copes when something goes wrong (for example a jammed bottle) and hands over to the morning team.",
    "The cell's cameras at work: reading which bottle is which (barcode and printed name), how full it is, and inspecting every pressed tablet.",
)
CLIENT_DOES_NOT_SHOW = (
    "Real tablets. Every number (dissolution, hardness, timings, results) is an illustrative value from a simulation. It says nothing about real products.",
    "A real robot. The arm, its reach and its timings are stand-ins; a real arm and real instruments would behave differently.",
    "The cameras on real equipment. The photographs are stock photographs standing in for the cell's camera, and the stickers on the bottles are added by the simulation. The camera checks were trained on public photographs and have not seen your bottles, labels, lighting or tablets, so how accurate they are on your equipment is not known.",
    "A promised speed-up. The comparison with manual work (9 trials a week) is an assumption: replace it with your own figure.",
    "Safety, quality or regulatory approval. Nothing here has been validated for use in a regulated laboratory.",
    "An exact number of trials. About 29 to 30 trials fit a run; the exact count depends on a small timing margin.",
)


def _panel(title: str, lines: tuple, tone: str) -> str:
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return f'<div class="lp-panel {tone}"><h3>{html.escape(title)}</h3><ul>{items}</ul></div>'


def render(record) -> None:
    style.stamp(record.meta.banner)
    st.markdown('<div class="lp-pagehead"><span class="lp-eyebrow">About</span><h1>What this shows, and what it does not</h1>'
                '<p>Please read this before drawing any conclusion from the numbers.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="lp-panels">' + _panel("What this shows", CLIENT_SHOWS, "") + _panel("What it does not show", CLIENT_DOES_NOT_SHOW, "lp-panel-no") + "</div>", unsafe_allow_html=True)