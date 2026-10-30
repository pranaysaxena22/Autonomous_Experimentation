"""Test scenes with a known answer: a bench seen from a tilted camera, four printed markers on a sheet, and vials holding coloured liquids at levels chosen in advance.

Because the levels, colours and positions are chosen, the health check can say exactly how right the reading is. The scenes are drawn, not photographed: they stand for a clean bench with plain light and are NOT proof that a real photo will read as well (a real camera, real glass and real light need their own try, with the page's camera or upload). Nothing here is random unless a seed is given.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .config import COLOUR_HUES, MARKER_SIDE_M, Calibration

SAMPLES_FOLDER = Path(__file__).resolve().parents[2] / "data" / "vision_samples"       # real photos dropped here show up as samples
DEMO_BOTTLES = Path(__file__).resolve().parents[2] / "data" / "public" / "labpics" / "demo_bottles"       # one real photograph per solution colour (tools/pick_bottle_photos.py)
X0, Y0, WIDTH_M, HEIGHT_M = -1.3, -0.2, 0.6, 0.4           # the printed sheet on the bench, in the arm's frame
PIXELS_PER_M = 1000
VIAL_DIAMETER_M = 0.02
CANVAS_CORNERS = np.float32([[0, 0], [WIDTH_M * PIXELS_PER_M, 0], [WIDTH_M * PIXELS_PER_M, HEIGHT_M * PIXELS_PER_M], [0, HEIGHT_M * PIXELS_PER_M]])
CAMERA_CORNERS = np.float32([[230, 215], [1050, 205], [1240, 690], [40, 700]])         # where the sheet's corners appear: a camera looking down at a slant


def _sheet(calibration: Calibration) -> np.ndarray:
    canvas = np.full((int(HEIGHT_M * PIXELS_PER_M), int(WIDTH_M * PIXELS_PER_M), 3), 245, np.uint8)
    cv2.rectangle(canvas, (2, 2), (canvas.shape[1] - 3, canvas.shape[0] - 3), (190, 190, 190), 3)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    side = int(MARKER_SIDE_M * PIXELS_PER_M)
    for marker_id, (cx, cy) in calibration.markers.items():
        marker = cv2.cvtColor(cv2.aruco.generateImageMarker(dictionary, marker_id, side), cv2.COLOR_GRAY2BGR)
        px, py = int((cx - X0) * PIXELS_PER_M - side / 2), int((Y0 + HEIGHT_M - cy) * PIXELS_PER_M - side / 2)
        canvas[py:py + side, px:px + side] = marker
    return canvas


def project(matrix: np.ndarray, x_m: float, y_m: float) -> tuple[float, float]:
    """Where a point on the bench (arm frame, metres) appears in the picture."""
    point = np.array([[[(x_m - X0) * PIXELS_PER_M, (Y0 + HEIGHT_M - y_m) * PIXELS_PER_M]]], np.float32)
    mapped = cv2.perspectiveTransform(point, matrix)[0, 0]
    return float(mapped[0]), float(mapped[1])


def _bgr(hue: int) -> tuple[int, int, int]:
    return tuple(int(v) for v in cv2.cvtColor(np.uint8([[[hue, 210, 215]]]), cv2.COLOR_HSV2BGR)[0, 0])


def _vial(img: np.ndarray, base: tuple[float, float], width_px: float, fill: float, hue: int, aspect: float, labels: np.ndarray | None = None) -> float:
    """Draw one standing vial with its base at a point; returns the liquid's width in pixels. The liquid is `fill` (0 to 1) of what it would be if full."""
    bx, by = int(round(base[0])), int(round(base[1]))
    w = max(12, int(round(width_px)))
    inner = w - 4
    full_h = inner * aspect
    body_h = int(full_h + 8)
    x0, x1 = bx - w // 2, bx + w // 2
    top = by - body_h
    shadow = img.copy()
    cv2.ellipse(shadow, (bx + 4, by + 2), (int(w * 0.8), max(3, w // 5)), 0, 0, 360, (90, 90, 90), -1)
    img[:] = cv2.addWeighted(shadow, 0.35, img, 0.65, 0)
    glass = img.copy()
    cv2.rectangle(glass, (x0, top), (x1, by - w // 4), (255, 255, 255), -1)
    cv2.ellipse(glass, (bx, by - w // 4), (w // 2, w // 4), 0, 0, 180, (255, 255, 255), -1)
    img[:] = cv2.addWeighted(glass, 0.18, img, 0.82, 0)
    liquid_h = int(round(fill * full_h))
    if liquid_h > 0:
        colour = np.array(_bgr(hue), np.float32)
        y_bottom = by - 4
        y_top = y_bottom - liquid_h
        columns = np.arange(inner, dtype=np.float32)
        shade = (0.82 + 0.18 * np.cos((columns / max(1, inner - 1) - 0.5) * np.pi))[None, :, None]
        block = np.clip(np.ones((liquid_h, inner, 3), np.float32) * colour * shade, 0, 255).astype(np.uint8)
        img[y_top:y_bottom, x0 + 2:x0 + 2 + inner] = block
        cv2.ellipse(img, (bx, y_top), (inner // 2, 3), 0, 0, 360, tuple(int(min(255, c * 1.2)) for c in colour), -1)
        cv2.line(img, (x0 + 2 + inner // 4, y_top + 2), (x0 + 2 + inner // 4, y_bottom - 3), (255, 255, 255), 2)       # a bright reflection down the glass
    cv2.line(img, (x0, top), (x0, by - w // 4), (170, 170, 170), 2)
    cv2.line(img, (x1, top), (x1, by - w // 4), (170, 170, 170), 2)
    cv2.ellipse(img, (bx, by - w // 4), (w // 2, w // 4), 0, 0, 180, (170, 170, 170), 2)
    cv2.rectangle(img, (x0 - 2, top - 14), (x1 + 2, top), (55, 55, 55), -1)                         # the cap
    if labels is not None:                                                                            # what each pixel is, for training: 1 vessel (glass and cap), 2 what is in it (a nearer vial paints over a farther one)
        cv2.rectangle(labels, (x0 - 2, top - 14), (x1 + 2, by - w // 4), 1, -1)
        cv2.ellipse(labels, (bx, by - w // 4), (w // 2, w // 4), 0, 0, 180, 1, -1)
        if liquid_h > 0:
            labels[by - 4 - liquid_h:by - 4, x0 + 2:x0 + 2 + inner] = 2
    return float(inner)


def make_scene(vials: list[tuple], seed: int = 0, brightness: float = 1.0, noise: float = 3.0, blur: int = 0, markers: bool = True, aspect: float = 4.5,
               size: tuple[int, int] = (1280, 720), calibration: Calibration = Calibration(), labels: np.ndarray | None = None) -> tuple[np.ndarray, list[dict]]:
    """A picture and its truth. `vials` is a list of (x in metres, y in metres, level 0 to 1, colour name). The truth lists each vial's position, level and colour. Pass `labels` (a zero array of the picture's height and width) to also get, for training, what each pixel is."""
    rng = np.random.default_rng(seed)
    matrix = cv2.getPerspectiveTransform(CANVAS_CORNERS, CAMERA_CORNERS)
    ramp = np.linspace(205, 225, size[1], dtype=np.float32)[:, None, None]
    img = np.clip(np.ones((size[1], size[0], 3), np.float32) * ramp, 0, 255).astype(np.uint8)
    sheet = _sheet(calibration if markers else Calibration(markers={}))
    warped = cv2.warpPerspective(sheet, matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    inside = cv2.warpPerspective(np.full(sheet.shape[:2], 255, np.uint8), matrix, size) > 0
    img[inside] = warped[inside]
    truth = []
    for x, y, level, colour in sorted(vials, key=lambda v: -v[1]):                  # far ones first, so near ones stand in front
        base = project(matrix, x, y)
        left, right = project(matrix, x - VIAL_DIAMETER_M / 2, y), project(matrix, x + VIAL_DIAMETER_M / 2, y)
        width = _vial(img, base, abs(right[0] - left[0]), level, COLOUR_HUES[colour], aspect, labels)
        truth.append({"x_m": x, "y_m": y, "fill_pct": 100.0 * level, "colour": colour, "base_px": base, "width_px": width})
    out = np.clip(img.astype(np.float32) * brightness + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    if blur:
        out = cv2.GaussianBlur(out, (blur | 1, blur | 1), 0)
    truth.sort(key=lambda t: t["base_px"][0])
    return out, truth


def scene_set() -> list[tuple[str, list[tuple]]]:
    """The sample scenes the page offers: (name, vials)."""
    return [
        ("Four solutions, one row", [(-1.14, 0.0, 0.80, "red"), (-1.04, 0.0, 0.55, "blue"), (-0.94, 0.0, 0.30, "green"), (-0.84, 0.0, 0.95, "yellow")]),
        ("Six vials, two rows", [(-1.12, 0.07, 0.40, "orange"), (-1.0, 0.07, 0.70, "purple"), (-0.88, 0.07, 0.25, "teal"), (-1.06, -0.07, 0.90, "pink"), (-0.94, -0.07, 0.15, "red"), (-0.82, -0.07, 0.60, "blue")]),
        ("A nearly empty set", [(-1.1, 0.0, 0.12, "green"), (-0.98, 0.0, 0.08, "blue"), (-0.86, 0.0, 0.20, "red")]),
    ]


def bottle_photo(colour: str) -> np.ndarray | None:
    """The real photograph standing for a bottle of this solution colour, if tools/pick_bottle_photos.py has made it."""
    path = DEMO_BOTTLES / f"{colour}.jpg"
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR) if path.exists() else None


def real_photos() -> list[tuple[str, np.ndarray]]:
    """Real photographs: the five demo bottle photographs (if made), then any dropped into data/vision_samples (JPG or PNG), by file name."""
    found = []
    for colour in ("blue", "yellow", "green", "orange", "purple"):
        photo = bottle_photo(colour)
        if photo is not None:
            found.append((f"Real photograph, {colour} solution", photo))
    if SAMPLES_FOLDER.exists():
        for path in sorted(SAMPLES_FOLDER.iterdir()):
            if path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
                if image is not None:
                    found.append((path.stem.replace("_", " "), image))
    return found
