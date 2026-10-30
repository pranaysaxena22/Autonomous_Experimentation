"""Reads a picture of a bench: finds the vessels that hold a coloured liquid, says how full each is and which colour (so which solution) it holds, and, when the four printed markers are in view, where each stands in the arm's own frame and whether the arm can reach it.

It uses classic image processing (OpenCV): colour segmentation for the liquids, printed markers for position. It needs no training data and no internet. What it cannot do, said plainly: a colourless liquid is invisible to it, an empty vessel is not found, and the level is read against the vessel shape that was set (VesselType), so it is an estimate to a few per cent, not a measurement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import COLOUR_HUES, MARKER_SIDE_M, Calibration, VesselType, colour_name

MAX_WIDTH = 1280
MIN_LIQUID_PIXELS = 250
GREEN, AMBER, WHITE, BLACK = (37, 188, 134), (23, 163, 232), (255, 255, 255), (0, 0, 0)       # Deloitte green and amber, in OpenCV's blue-green-red order


class VisionError(Exception):
    """The picture cannot be read. The message says why, in plain words."""


@dataclass
class Vessel:
    index: int
    box: tuple                  # x, y, width, height of the liquid, in the (possibly shrunk) picture
    fill_pct: float
    hue: float
    colour: str
    confidence: float
    table_xy_m: tuple | None = None
    reachable: bool | None = None
    note: str = ""

    @property
    def trusted(self) -> bool:
        return self.confidence >= 0.75 and 0 < self.fill_pct <= 105


@dataclass
class Analysis:
    vessels: list[Vessel]
    markers_found: int
    calibrated: bool
    notes: list[str]
    annotated: np.ndarray
    scale: float = 1.0
    engine: str = "rules"            # which reader made this analysis: "rules" (colour and geometry) or "model" (the trained network)

    def rows(self) -> list[dict]:
        """One plain row per vessel, for a table."""
        out = []
        for v in self.vessels:
            where = f"x {v.table_xy_m[0]:+.2f} m, y {v.table_xy_m[1]:+.2f} m" if v.table_xy_m else "needs the four markers"
            out.append({"Vessel": v.index, "Solution (by colour)": v.colour.capitalize(), "Level (%)": f"{v.fill_pct:.0f}", "Position for the arm": where,
                        "Arm can reach": ("yes" if v.reachable else "no") if v.reachable is not None else "-", "Confidence": "good" if v.trusted else "check"})
        return out

    def client_rows(self) -> list[dict]:
        """One plain row per vessel for a client: which solution, how full, and whether to trust the reading."""
        return [{"Vessel": v.index, "Solution": v.colour.capitalize(), "Level (%)": f"{v.fill_pct:.0f}", "Reading": "good" if v.trusted else "please check"} for v in self.vessels]

    def summary(self) -> dict:
        """The few counts a page shows: vessels found, markers seen, how many can be reached."""
        return {"vessels": len(self.vessels), "markers": self.markers_found, "calibrated": self.calibrated, "reachable": sum(1 for v in self.vessels if v.reachable), "unreachable": sum(1 for v in self.vessels if v.reachable is False),
                "to_check": sum(1 for v in self.vessels if not v.trusted)}

    def compare_rows(self, truth: list[dict]) -> list[dict]:
        """For a test scene, each vessel's read level next to the known one and the difference in points (vessels are matched left to right)."""
        return [{"Vessel": v.index, "Known solution": t["colour"].capitalize(), "Read as": v.colour.capitalize(), "Known level (%)": f"{t['fill_pct']:.0f}", "Read level (%)": f"{v.fill_pct:.0f}", "Difference (points)": f"{v.fill_pct - t['fill_pct']:+.1f}"}
                for v, t in zip(self.vessels, truth)]

    def png(self) -> bytes:
        ok, data = cv2.imencode(".png", self.annotated)
        return data.tobytes() if ok else b""


def decode(data: bytes) -> np.ndarray:
    """Bytes of a picture file (a photo, a camera frame) to an image. Refuses anything else in plain words."""
    if not data:
        raise VisionError("There is no picture to read.")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise VisionError("That file could not be read as a picture. Use a photo (JPG or PNG).")
    return image


def _circular_mean_hue(hues: np.ndarray) -> float:
    angles = hues.astype(np.float64) * (2 * math.pi / 180.0)
    return (math.atan2(np.sin(angles).mean(), np.cos(angles).mean()) * 180.0 / (2 * math.pi)) % 180.0


def _homography(image: np.ndarray, calibration: Calibration) -> tuple[np.ndarray | None, int]:
    """(the map from picture to bench, how many of the four markers were seen). The map exists only when all four were."""
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    if ids is None:
        return None, 0
    seen = {int(i): c.reshape(4, 2) for i, c in zip(ids.ravel(), corners) if int(i) in calibration.markers}
    if len(seen) < 4:
        return None, len(seen)
    half = MARKER_SIDE_M / 2
    source, target = [], []
    for marker_id, quad in seen.items():
        cx, cy = calibration.markers[marker_id]
        for (px, py), (dx, dy) in zip(quad, ((-half, half), (half, half), (half, -half), (-half, -half))):        # top-left, top-right, bottom-right, bottom-left of the marker, as the table lies
            source.append((px, py))
            target.append((cx + dx, cy + dy))
    matrix, _ = cv2.findHomography(np.array(source, np.float32), np.array(target, np.float32), 0)
    return matrix, len(seen)


def _to_table(matrix: np.ndarray, point: tuple[float, float]) -> tuple[float, float]:
    mapped = cv2.perspectiveTransform(np.array([[point]], np.float32), matrix)[0, 0]
    return float(mapped[0]), float(mapped[1])


def analyse(image: np.ndarray, vessel: VesselType = VesselType(), calibration: Calibration = Calibration(), engine: str = "rules") -> Analysis:
    """Find the liquids in the picture and describe each vessel. engine: "rules" (colour and geometry, the default), "model" (the trained network, when its weights exist) or "auto" (the network when it exists, else the rules).
    Never raises on an odd picture: it returns no vessels and says why."""
    if engine in ("model", "auto"):
        from . import learned
        if learned.available():
            return learned.analyse(image, vessel, calibration)
        if engine == "model":
            raise VisionError("The trained model is not available on this computer yet. Train it with tools\\train_vision.py (see docs/vision.md).")
    scale = 1.0
    if image.shape[1] > MAX_WIDTH:
        scale = MAX_WIDTH / image.shape[1]
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    notes: list[str] = []
    matrix, found = _homography(image, calibration)
    if found == 0:
        notes.append("No printed markers were found, so positions for the arm cannot be given (levels and colours still are).")
    elif matrix is None:
        notes.append(f"Only {found} of the four printed markers were found, so positions for the arm cannot be given.")
    hsv = cv2.cvtColor(cv2.GaussianBlur(image, (5, 5), 0), cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] >= 80) & (hsv[:, :, 2] >= 50)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))      # joins a liquid split by a bright reflection
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 9)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    vessels: list[Vessel] = []
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if area < MIN_LIQUID_PIXELS or w < 8 or h < 6:
            continue
        inside = labels[y:y + h, x:x + w] == label
        row_widths = inside.sum(axis=1)
        solid = np.where(row_widths >= 0.7 * np.median(row_widths[row_widths > 0]))[0]            # the rows as wide as the liquid is: leaves out the thin curve of the surface
        if solid.size == 0:
            continue
        y, h, w = int(y + solid[0]), int(solid[-1] - solid[0] + 1), int(round(float(np.median(row_widths[solid]))))
        pixels = hsv[:, :, 0][labels == label]
        hue = _circular_mean_hue(pixels)
        spread = float(np.sqrt(np.mean(((pixels.astype(np.float64) - hue + 90) % 180 - 90) ** 2)))
        rectangular = min(1.0, (area / float(w * h)) / 0.9)
        confidence = max(0.0, min(1.0, rectangular * (1.0 - min(1.0, spread / 25.0))))
        fill = 100.0 * h / (w * vessel.body_aspect)
        entry = Vessel(0, (int(x), int(y), int(w), int(h)), min(fill, 130.0), hue, colour_name(hue), confidence)
        entry.box = (int(x), int(y), int(max(w, stats[label][2])), int(h))
        if fill > 105:
            entry.note = "taller than a full vessel of this shape: check the shape setting"
        if matrix is not None:
            entry.table_xy_m = _to_table(matrix, (x + w / 2.0, float(y + h)))
            dx, dy = entry.table_xy_m[0] - calibration.arm_base[0], entry.table_xy_m[1] - calibration.arm_base[1]
            distance = math.hypot(dx, dy)
            entry.reachable = calibration.min_radius_m <= distance <= calibration.reach_m
        vessels.append(entry)
    vessels.sort(key=lambda v: v.box[0])
    for number, entry in enumerate(vessels, start=1):
        entry.index = number
    if not vessels:
        notes.append("No coloured liquid was found. Colourless liquids and empty vessels are not seen: use coloured solutions, good light and a plain background.")
    return Analysis(vessels, found, matrix is not None, notes, annotate(image, vessels, matrix is not None), scale)


def annotate(image: np.ndarray, vessels: list[Vessel], calibrated: bool) -> np.ndarray:
    """The picture with each liquid boxed and labelled (green when trusted, amber when it should be checked)."""
    out = image.copy()
    for v in vessels:
        x, y, w, h = v.box
        colour = GREEN if v.trusted else AMBER
        cv2.rectangle(out, (x - 3, y - 3), (x + w + 3, y + h + 3), colour, 2)
        lines = [f"{v.index}: {v.colour} {v.fill_pct:.0f}%"] + ([f"({v.table_xy_m[0]:+.2f}, {v.table_xy_m[1]:+.2f}) m" + ("" if v.reachable else " out of reach")] if v.table_xy_m else [])
        widest = max(cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0][0] for text in lines) + 8
        left = x + w + 8 if x + w + 8 + widest < out.shape[1] else x - 8 - widest             # beside the liquid, on whichever side has room
        for k, text in enumerate(lines):
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            ty = max(th + 6, y + 14) + 20 * k
            cv2.rectangle(out, (left - 3, ty - th - 5), (left + tw + 5, ty + 5), BLACK, -1)
            cv2.putText(out, text, (left + 1, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1, cv2.LINE_AA)
    return out


def analyse_bytes(data: bytes, vessel: VesselType = VesselType(), calibration: Calibration = Calibration(), engine: str = "rules") -> Analysis:
    """The same from a picture file's bytes (what a camera or an upload gives)."""
    return analyse(decode(data), vessel, calibration, engine)
