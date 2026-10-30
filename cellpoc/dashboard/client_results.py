"""The 'Results' page (platform runs only): the run told as results a client cares about, with charts.

Everything shown comes from client_story.json, which was worked out in advance and saved next to the run record (see cellpoc/client_story). This page only places it on the screen, as cards and charts. Nothing here is worked out:
every number is read from that file and only written out as text. The charts are drawn for the app's dark look (their own colours; the older dashboard pages and their charts are unchanged).
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

from . import style

STORY_FILE = "client_story.json"
GREEN, NEON, BLUE, AMBER, GREY, PANEL, TEXT, EDGE = "#86BC25", "#86EB22", "#00A3E0", "#E8A317", "#E6E6E6", "#282728", "#E6E6E6", "#555555"
OUTCOME_COLOURS = alt.Scale(domain=["Good", "Not good"], range=[GREEN, AMBER])


def load_story(record_path) -> Optional[dict]:
    """The client story saved next to the run record, or None when it is not there (a run made before this page existed)."""
    path = Path(record_path).parent.joinpath(STORY_FILE)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _dark(chart, height: int):
    """One look for every chart on this page: the panel colour behind it, light text, thin grid lines."""
    return (chart.properties(height=height, width="container")
            .configure(background=PANEL, font="Open Sans, Arial, sans-serif")
            .configure_axis(labelColor=TEXT, titleColor=TEXT, gridColor="#555555", gridOpacity=0.55, domainColor="#555555", tickColor="#555555", labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelColor=TEXT, titleColor=TEXT, orient="top", labelFontSize=12, symbolType="circle")
            .configure_view(stroke=None)
            .configure_title(color="#FFFFFF", fontSize=14, anchor="start", font="Open Sans, Arial, sans-serif"))


def _show(chart, height: int, name: str) -> None:
    """Draw a chart in a container the app's style sheet knows (so it sits on the panel colour, not on the white card the older pages' charts use)."""
    with st.container(key=f"darkchart_{name}"):
        st.altair_chart(_dark(chart, height), width="stretch", theme=None)


def _card(value: str, label: str, note: str) -> str:
    return (f'<div class="ub-kpi"><div class="ub-kpi-value">{html.escape(value)}</div><div class="ub-kpi-label">{html.escape(label)}</div>'
            f'<div class="ub-kpi-note">{html.escape(note)}</div></div>')


def headline_cards(story: dict) -> None:
    """The four numbers a client remembers, as large cards."""
    first = story["first_good"]
    cards = [
        _card(f"{story['multiple']:.1f}x", "more experiments per week", f"{story['trials_per_week']:g} a week against {story['manual_per_week']:g} by hand (assumed)"),
        _card(f"{story['unattended_share_pct']:.0f}%", "of the run unattended", f"{story['unattended_hours']:g} of {story['run_hours']:g} hours"),
    ]
    if first:
        cards.append(_card(f"{first['hours']:.0f} h", "to the first good recipe", f"about {first['manual_hours']:.0f} h by hand (assumed)"))
    cards.append(_card(f"{story['trials_good']} of {story['trials_with_result']}", "recipes met the requirements", f"{story['good_share_pct']:.0f}% of the recipes tested"))
    for column, card in zip(st.columns(len(cards)), cards):
        column.markdown(card, unsafe_allow_html=True)


def _section(title: str, takeaway: str) -> None:
    st.markdown(f'<div class="ub-section"><h3>{html.escape(title)}</h3><p>{html.escape(takeaway)}</p></div>', unsafe_allow_html=True)


def _throughput(story: dict) -> None:
    _section("More experiments in the same time", "Day and night, not working hours only. The manual figure is an assumption.")
    rows = pd.DataFrame([{"Who": "Autonomous cell", "Trials with a result per week": story["trials_per_week"]}, {"Who": "By hand (assumed)", "Trials with a result per week": story["manual_per_week"]}])
    bars = alt.Chart(rows).mark_bar(size=34, cornerRadiusEnd=4).encode(
        y=alt.Y("Who:N", title=None, sort=["Autonomous cell", "By hand (assumed)"]), x=alt.X("Trials with a result per week:Q", title="Trials with a result per week"),
        color=alt.Color("Who:N", legend=None, scale=alt.Scale(domain=["Autonomous cell", "By hand (assumed)"], range=[GREEN, GREY])), tooltip=["Who", "Trials with a result per week"])
    labels = alt.Chart(rows).mark_text(align="left", dx=6, color="#FFFFFF", fontSize=15, fontWeight="bold").encode(y=alt.Y("Who:N", title=None, sort=["Autonomous cell", "By hand (assumed)"]), x=alt.X("Trials with a result per week:Q", title="Trials with a result per week"), text="Trials with a result per week:Q")
    _show(bars + labels, 150, "throughput")


def _learning(story: dict) -> None:
    start, chosen = story["starting"], story["chosen"]
    lead = "The first recipes are spread out; then the engine chooses."
    if start and chosen:
        lead = lead + f" Good before: {start['good']} of {start['count']}. Good after: {chosen['good']} of {chosen['with_result']}."
        _section("It learns where the good recipes are", lead)
    rows = pd.DataFrame([{"Recipe number": e["trial"], "Dissolution at 30 min (%)": e["dissolution"], "Result": e["outcome"], "How the recipe was picked": e["chosen_by"]} for e in story["learning"]])
    points = alt.Chart(rows).mark_circle(size=130, opacity=0.95).encode(
        x=alt.X("Recipe number:Q", title="Recipe number", scale=alt.Scale(domain=[0, story["trials_attempted"] + 1])), y=alt.Y("Dissolution at 30 min (%):Q", title="Dissolution at 30 min (%)", scale=alt.Scale(zero=False)),
        color=alt.Color("Result:N", scale=OUTCOME_COLOURS, legend=alt.Legend(title=None)), tooltip=["Recipe number", "Dissolution at 30 min (%)", "Result", "How the recipe was picked"])
    layers = points
    for target in story["targets"]:
        if target["goal"] == "at_least" and target["response"].startswith("dissolution"):
            line = alt.Chart(pd.DataFrame([{"y": target["value"], "label": f"Requirement: {target['text']}"}]))
            layers = layers + line.mark_rule(color=NEON, strokeDash=[6, 4], strokeWidth=2).encode(y=alt.Y("y:Q", title="Dissolution at 30 min (%)")) + line.mark_text(align="left", dx=6, dy=-8, color=NEON, fontSize=12).encode(y=alt.Y("y:Q", title="Dissolution at 30 min (%)"), text="label:N", x=alt.value(4))
    if start:
        edge = alt.Chart(pd.DataFrame([{"x": story["starting_trials"] + 0.5, "label": "Engine takes over"}]))
        layers = layers + edge.mark_rule(color=BLUE, strokeDash=[2, 4], strokeWidth=2).encode(x=alt.X("x:Q", title="Recipe number")) + edge.mark_text(align="left", dx=6, dy=-4, baseline="top", color=BLUE, fontSize=12).encode(x=alt.X("x:Q", title="Recipe number"), text="label:N", y=alt.value(4))
    left, right = st.columns(2)
    with left:
        st.markdown("**Dissolution of each recipe**")
        _show(layers, 330, "learning_dots")
    with right:
        st.markdown("**Good recipes so far**")
        found = pd.DataFrame([{"Days into the run": e["day"], "Good recipes found": e["good_so_far"]} for e in story["learning"]])
        area = alt.Chart(found).mark_area(interpolate="step-after", color=GREEN, opacity=0.35, line={"color": GREEN, "strokeWidth": 3}).encode(
            x=alt.X("Days into the run:Q", scale=alt.Scale(domain=[0, story["run_days"]])), y=alt.Y("Good recipes found:Q"), tooltip=["Days into the run", "Good recipes found"])
        _show(area, 330, "learning_curve")


def _utilisation(story: dict) -> None:
    _section("It works while nobody is there", f"{story['trials_started_unattended']} of {story['trials_attempted']} trials were started with nobody in the lab.")
    rows = []
    for w in story["week"]["windows"]:
        if w["staffed"]:
            rows.append({"Row": "People in the lab", "From": w["start_d"], "To": w["end_d"], "Colour": "People in the lab", "Detail": f"{w['from']} to {w['to']}"})
    for t in story["week"]["trials"]:
        rows.append({"Row": "The cell running trials", "From": t["start_d"], "To": t["end_d"], "Colour": t["outcome"], "Detail": f"Trial {t['trial']}: {t['outcome']}"})
    order = ["People in the lab", "The cell running trials"]
    bars = alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadius=3, stroke=PANEL, strokeWidth=1).encode(
        x=alt.X("From:Q", title="Days into the run", scale=alt.Scale(domain=[0, story["run_days"]])), x2="To:Q", y=alt.Y("Row:N", title=None, sort=order),
        color=alt.Color("Colour:N", legend=alt.Legend(title=None), scale=alt.Scale(domain=["People in the lab", "Good", "Not good", "No result"], range=[BLUE, GREEN, AMBER, "#555555"])), tooltip=["Detail"])
    _show(bars, 180, "utilisation")


def _space(story: dict) -> None:
    _section("Where the good recipes are", "Each dot is a recipe; green met the requirements.")
    rows = pd.DataFrame([{"Drug (active), %": e["drug"], "Filler, %": e["filler"], "Result": e["outcome"], "Recipe number": e["trial"]} for e in story["space"]])
    dots = alt.Chart(rows).mark_circle(size=150, opacity=0.9, stroke=PANEL, strokeWidth=1).encode(
        x=alt.X("Drug (active), %:Q", scale=alt.Scale(zero=False)), y=alt.Y("Filler, %:Q", scale=alt.Scale(zero=False)),
        color=alt.Color("Result:N", scale=alt.Scale(domain=["Good", "Not good", "No result"], range=[GREEN, AMBER, "#555555"]), legend=alt.Legend(title=None)), tooltip=["Recipe number", "Drug (active), %", "Filler, %", "Result"])
    _show(dots, 360, "space")


def _events(story: dict) -> None:
    _section("When something goes wrong", "Handled by the cell where it can; the rest waits for the first person in.")
    if not story["events"]:
        st.markdown('<div class="ub-card ub-quiet"><h4>No faults in this run</h4><p>Nothing needed attention.</p></div>', unsafe_allow_html=True)
    for event in story["events"]:
        tone = "ub-warn" if event["needs_human"] else ""
        queued = f" Waiting for staff: {event['queued_for']}." if event["queued_for"] else ""
        st.markdown(f'<div class="ub-card {tone}"><h4>{html.escape(event["title"])}</h4><p>{html.escape(event["when"])}. {html.escape(event["text"])}.{html.escape(queued)}</p></div>', unsafe_allow_html=True)
    if story["handovers"]:
        st.markdown("**Handover for the morning team**")
        first = story["handovers"][0]
        with st.expander(first["title"], expanded=True):
            st.write(first["text"])
        for handover in story["handovers"][1:]:
            with st.expander(handover["title"]):
                st.write(handover["text"])


def _requirements(story: dict) -> None:
    rows = []
    for target in story["targets"]:
        rows.append({"Requirement a recipe has to meet": target["label"], "Target": target["text"], "Required": "Yes" if target["required"] else "Optional"})
    if rows:
        _section("What good means", "Every required target is met.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render(record, record_path) -> None:
    style.stamp(record.meta.banner)
    story = load_story(record_path)
    st.subheader("What the cell delivered")
    st.caption(record.platform.label if record.platform is not None else story["label"] if story else "")
    if story is None:
        st.warning("The results summary was not found next to this run. Double-click run_app.bat (it builds the run and this summary), then reload this page.")
        return
    headline_cards(story)
    st.caption("Illustrative values. The manual comparison is an assumption.")
    _throughput(story)
    _learning(story)
    _utilisation(story)
    _space(story)
    _events(story)
    _requirements(story)
