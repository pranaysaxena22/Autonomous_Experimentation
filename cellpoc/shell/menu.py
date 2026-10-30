"""The left menu, as data: which pages there are, in which order, under which heading. Display only; nothing here decides anything."""
from __future__ import annotations

from typing import NamedTuple


class Entry(NamedTuple):
    title: str
    path: str            # the page's file, relative to the app's launcher file (unified_app.py)
    icon: str
    needs_platform: bool  # only a platform run (not the proof of concept's demo) has this page
    what: str            # one plain line for the Overview's "demo in order" list


FOLDER = "cellpoc/shell/pages/"

# Section heading -> its pages, in the approved order. Setup is the setup app drawn inside this app (Stage B); Live run is the live view, started and stopped from the page (Stage C).
SECTIONS = {
    "Start": [Entry("Overview", FOLDER + "overview.py", ":material/home:", False, "The headline numbers."),
              Entry("Vision", FOLDER + "vision.py", ":material/photo_camera:", False, "The cell reads levels and solutions from a picture."),
              Entry("Results at a glance", FOLDER + "results.py", ":material/insights:", True, "What the cell delivered, in charts.")],
    "Describe": [Entry("Setup", FOLDER + "setup.py", ":material/tune:", False, "Describe a study.")],
    "Run": [Entry("The run", FOLDER + "the_run.py", ":material/timeline:", False, "The finished run, moment by moment."),
            Entry("Live run", FOLDER + "live_run.py", ":material/play_circle:", False, "The cell working, live.")],
    "See the cell": [Entry("3D replay", FOLDER + "replay.py", ":material/view_in_ar:", True, "The run as a 3D picture, with the jam."),
                Entry("Physics (MuJoCo)", FOLDER + "physics.py", ":material/precision_manufacturing:", True, "The run played in a physics model.")],
    "Evidence": [Entry("Data and model", FOLDER + "data_and_model.py", ":material/database:", True, "The data and the models."),
                 Entry("Reports", FOLDER + "reports.py", ":material/description:", True, "A labelled report to take away.")],
    "About": [Entry("About and limits", FOLDER + "about.py", ":material/info:", False, "What this shows, and what it does not.")],
}

# The client view: the pages that are meant for the people the demo is for. The other pages (the finished run moment by moment, the 3D and physics views, the data and models) are for the team and are in the developer view.
_BY_TITLE = {entry.title: entry for entries in SECTIONS.values() for entry in entries}
CLIENT_SECTIONS = {
    "Monitor": [_BY_TITLE["Overview"], _BY_TITLE["Live run"], _BY_TITLE["Results at a glance"], _BY_TITLE["Vision"]],
    "Configure": [_BY_TITLE["Setup"]],
    "Output": [_BY_TITLE["Reports"]],
    "About": [_BY_TITLE["About and limits"]],
}
