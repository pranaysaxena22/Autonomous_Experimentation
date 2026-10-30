"""What the vision needs to be told once: the shape of the vessels, the names of the colours, and where the four printed markers lie on the bench (so a picture can be turned into positions the arm can use).

Everything here is a setting with a default; nothing about a particular camera is built into the code.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# OpenCV hue runs 0 to 179. A coloured liquid is named from its average hue: (name, first hue, last hue). Red wraps round, so it is listed twice.
COLOUR_BANDS = [("red", 170, 180), ("red", 0, 8), ("orange", 8, 20), ("yellow", 20, 35), ("green", 35, 85), ("teal", 85, 100), ("blue", 100, 130), ("purple", 130, 155), ("pink", 155, 170)]
# a typical hue for each name (used to draw the sample scenes and to show a swatch)
COLOUR_HUES = {"red": 2, "orange": 14, "yellow": 28, "green": 60, "teal": 92, "blue": 112, "purple": 140, "pink": 162}
# The stock solution each ingredient bottle holds in the demonstration (illustrative colours, so a camera can tell the bottles apart): the cell's vision check compares what it sees with this
INGREDIENT_SOLUTIONS = {"drug_pct": "blue", "filler_pct": "yellow", "binder_pct": "green", "disintegrant_pct": "orange", "lubricant_pct": "purple"}
MARKER_SIDE_M = 0.06            # the printed side of each marker, in metres
MARKER_DICTIONARY = "DICT_4X4_50"


@dataclass(frozen=True)
class VesselType:
    """The shape of the vessels: how tall the liquid is when the vessel is FULL, divided by the liquid's width (a test tube is tall and thin, a vial is shorter). The level is read against this; set it once by looking at a full vessel."""
    body_aspect: float = 4.5
    full_fraction: float = 0.78      # for the trained reader: when the vessel is FULL its contents fill this share of the vessel's whole height (glass bottom, shoulder and cap take the rest)


@dataclass(frozen=True)
class Calibration:
    """Where the four printed markers (ids 0 to 3) lie on the bench, as the centre of each in the arm's own frame, in metres (x to the right, y away from the arm's base), and how far the arm reaches.
    With all four found in a picture, any point on the bench in that picture can be turned into a position the arm can go to."""
    markers: dict = field(default_factory=lambda: {0: (-1.26, -0.16), 1: (-0.74, -0.16), 2: (-0.74, 0.16), 3: (-1.26, 0.16)})
    reach_m: float = 1.44
    arm_base: tuple = (0.0, 0.0)
    min_radius_m: float = 0.25          # closer than this to the arm's base is inside its own column


def colour_name(hue: float) -> str:
    """The name of an OpenCV hue (0 to 179)."""
    for name, low, high in COLOUR_BANDS:
        if low <= hue < high:
            return name
    return "red"
