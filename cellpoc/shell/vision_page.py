"""The Vision page: a picture of the bench in, the liquids it holds out: which solution (by colour), how full, where it stands for the arm, and whether the arm can reach it.

Pictures come from a sample scene (drawn, with a known answer), the computer's camera, or a photo. The reading is done by the vision part (cellpoc/vision); this page only shows what it returns and works nothing out.
"""
from __future__ import annotations

import streamlit as st

from cellpoc.dashboard import style as dashboard_style
from cellpoc.shell import context, landing
from cellpoc.vision import VesselType, VisionError, analyse, analyse_bytes, make_scene, model_available, model_status, real_photos, scene_set

CAMERA, SAMPLE, PHOTO = "Camera", "Sample scene", "Photo"


MODEL, RULES = "Trained model", "Colour rules"


def _sample(name: str, shape: VesselType, engine: str):
    for index, (scene, vials) in enumerate(scene_set()):
        if scene == name:
            image, truth = make_scene(vials, seed=index)
            return analyse(image, shape, engine=engine), truth
    for photo, image in real_photos():
        if photo + " (image file)" == name:
            return analyse(image, shape, engine=engine), None
    return None, None


@st.fragment(run_every=6)
def _model_panel() -> None:
    """What the trained model is: its scores, and, while it is being trained, how far training has got (this refreshes by itself)."""
    status = model_status()
    if status["text"] and status["stage"] != "done":
        st.progress(status["fraction"], text=status["text"])
    if status["rows"]:
        st.dataframe(status["rows"], hide_index=True, width="stretch")
    elif not status["text"]:
        st.caption("No trained model yet: run tools\\train_vision.py.")


def render() -> None:
    record, _ = context.load_record()
    dev = context.developer()
    dashboard_style.stamp(record.meta.banner)
    if dev:
        st.subheader("Vision")
    else:
        st.markdown(landing.page_header("Monitor", "Vision", "Pick a picture, take one with your camera or upload a photo. The cell reads which solution is in each vessel and how full it is."), unsafe_allow_html=True)
    source = st.radio("Picture from", [SAMPLE, CAMERA, PHOTO], horizontal=True, label_visibility="collapsed")
    if dev:
        engines = [MODEL, RULES] if model_available() else [RULES]
        left, right = st.columns([1, 2])
        engine = MODEL if left.radio("Reader", engines, horizontal=True, label_visibility="collapsed") == MODEL else RULES
        if engine == MODEL:
            shape = VesselType(full_fraction=right.slider("How full a FULL vessel reads: the share of the vessel's height its contents fill", 0.5, 1.0, VesselType().full_fraction, 0.01))
        else:
            shape = VesselType(right.slider("Vessel shape: height of a full vessel divided by its width", 2.0, 8.0, VesselType().body_aspect, 0.1))
    else:
        engine = MODEL if model_available() else RULES            # the client view uses the best reader there is, with the usual settings
        shape = VesselType()
    engine_name = "model" if engine == MODEL else "rules"
    analysis, truth = None, None
    try:
        if source == SAMPLE:
            names = [photo + " (image file)" for photo, _ in real_photos()] + [name for name, _ in scene_set()]          # real photographs first: the page opens on one
            analysis, truth = _sample(st.selectbox("Sample", names, label_visibility="collapsed"), shape, engine_name)
        elif source == CAMERA:
            shot = st.camera_input("Take a picture of the bench (coloured liquids, plain background, the four printed markers in view)" if dev else "Take a picture of the liquids to read")
            analysis = analyse_bytes(shot.getvalue(), shape, engine=engine_name) if shot is not None else None
        else:
            upload = st.file_uploader("A photo of the bench" if dev else "A photo of the liquids to read", type=["jpg", "jpeg", "png"])
            analysis = analyse_bytes(upload.getvalue(), shape, engine=engine_name) if upload is not None else None
    except VisionError as problem:
        st.warning(str(problem))
    if dev:
        with st.expander("The trained model: how it was made and how well it does"):
            _model_panel()
    if analysis is None:
        return
    counts = analysis.summary()
    if not dev:
        left, right = st.columns([1.2, 1])                       # the picture beside what the cell reads from it
        left.image(analysis.png())
        right.metric("Vessels found", counts["vessels"])
        if analysis.vessels:
            right.dataframe(analysis.client_rows(), hide_index=True, width="stretch")
        return
    st.image(analysis.png())
    if dev:
        first, second, third = st.columns(3)
        first.metric("Vessels found", counts["vessels"])
        second.metric("Markers seen", f"{counts['markers']} of 4")
        third.metric("Arm can reach", f"{counts['reachable']} of {counts['vessels']}" if counts["calibrated"] else "-")
    else:
        st.metric("Vessels found", counts["vessels"])
    if analysis.vessels:
        st.dataframe(analysis.rows() if dev else analysis.client_rows(), hide_index=True, width="stretch")
    if dev:
        for note in analysis.notes:
            st.info(note)
    if dev and truth is not None and analysis.vessels:
        with st.expander("Check against the known answer"):
            st.dataframe(analysis.compare_rows(truth), hide_index=True, width="stretch")
