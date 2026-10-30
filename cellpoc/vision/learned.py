"""The trained reader: a small neural network (a MobileNetV3 segmentation network, fine-tuned) that marks, in a picture, every pixel as background, vessel or the contents of a vessel, and from those masks the same readings as the rule-based reader: how full each vessel is, which solution (by the contents' colour), and where it stands for the arm.

It is trained by tools/train_vision.py on the public LabPics photographs (2,187 real photographs of liquids and solids in vessels, MIT licence) together with drawn bench scenes, and its weights live in data/vision_models (not saved in git). When the weights are absent the program says so and uses the colour rules.
Everything runs on this computer; nothing is fetched at run time.
"""
from __future__ import annotations

import json
import math
from importlib.util import find_spec
from pathlib import Path

import cv2
import numpy as np

from .analyse import Analysis, Vessel, _homography, _to_table, annotate
from .config import Calibration, VesselType, colour_name

MODEL_FOLDER = Path(__file__).resolve().parents[2] / "data" / "vision_models"
WEIGHTS = MODEL_FOLDER / "vessel_content.pt"
REPORT = MODEL_FOLDER / "report.json"
CLASSES = ("background", "vessel", "contents")
SHORT_SIDE = 320
MIN_COMPONENT_FRACTION = 0.0015
_cache: dict = {}


def available() -> bool:
    """True when the trained weights exist and PyTorch can be loaded."""
    return WEIGHTS.exists() and find_spec("torch") is not None and find_spec("torchvision") is not None


def build_model(pretrained: bool = False):
    """The network: LRASPP with a MobileNetV3-Large backbone, three classes. `pretrained` starts from weights learned on everyday photographs (for training)."""
    from torchvision.models.segmentation import LRASPP_MobileNet_V3_Large_Weights, lraspp_mobilenet_v3_large
    model = lraspp_mobilenet_v3_large(weights=LRASPP_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1 if pretrained else None, weights_backbone=None)
    from torch import nn
    model.classifier.low_classifier = nn.Conv2d(model.classifier.low_classifier.in_channels, len(CLASSES), 1)
    model.classifier.high_classifier = nn.Conv2d(model.classifier.high_classifier.in_channels, len(CLASSES), 1)
    return model


def _model():
    if "model" not in _cache:
        import torch
        model = build_model(False)
        model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=True))
        model.eval()
        _cache["model"] = model
    return _cache["model"]


MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)


def to_tensor(image_bgr: np.ndarray):
    """A picture as the network's input: resized so its short side is SHORT_SIDE (and both sides a multiple of 8), colours normalised."""
    import torch
    h, w = image_bgr.shape[:2]
    scale = SHORT_SIDE / min(h, w)
    nh, nw = max(32, int(round(h * scale / 8)) * 8), max(32, int(round(w * scale / 8)) * 8)
    small = cv2.resize(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB), (nw, nh), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    return torch.from_numpy(((small - MEAN) / STD).transpose(2, 0, 1)).unsqueeze(0)


def predict(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(the class of every pixel, how sure the network is of each), both at the picture's own size."""
    import torch
    with torch.no_grad():
        scores = _model()(to_tensor(image_bgr))["out"]
        scores = torch.nn.functional.interpolate(scores, size=image_bgr.shape[:2], mode="bilinear", align_corners=False)
        probs = torch.softmax(scores, dim=1)[0].numpy()
    return probs.argmax(axis=0).astype(np.uint8), probs.max(axis=0)


def readings_from_masks(image: np.ndarray, labels: np.ndarray, sure: np.ndarray, vessel: VesselType, calibration: Calibration) -> tuple[list[Vessel], np.ndarray | None, int, list[str]]:
    """Turn the network's masks into vessels: each connected region that is vessel or contents is one vessel; its fill is the height of its contents over its own height, its solution the colour of its contents."""
    notes: list[str] = []
    matrix, found = _homography(image, calibration)
    if found == 0:
        notes.append("No printed markers were found, so positions for the arm cannot be given (levels and colours still are).")
    elif matrix is None:
        notes.append(f"Only {found} of the four printed markers were found, so positions for the arm cannot be given.")
    union = ((labels == 1) | (labels == 2)).astype(np.uint8) * 255
    union = cv2.morphologyEx(union, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    count, comp, stats, _ = cv2.connectedComponentsWithStats(union, connectivity=8)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    minimum = MIN_COMPONENT_FRACTION * image.shape[0] * image.shape[1]
    vessels: list[Vessel] = []
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if area < minimum or h < 12 or w < 6:
            continue
        region = comp == label
        contents = region & (labels == 2)
        rows = np.where(contents.any(axis=1))[0]
        if rows.size >= 3 and contents.sum() > 0.03 * area:
            fill = 100.0 * (rows[-1] - rows[0] + 1) / h / max(0.3, vessel.full_fraction)
            ys, xs = np.where(contents)
            pixels = hsv[contents]
            saturation = float(pixels[:, 1].mean())
            hue = float(np.degrees(math.atan2(np.sin(np.radians(pixels[:, 0] * 2.0)).mean(), np.cos(np.radians(pixels[:, 0] * 2.0)).mean())) % 360.0 / 2.0)
            colour = colour_name(hue) if saturation >= 45 else "colourless"
            box = (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
        else:
            fill, hue, colour, box = 0.0, 0.0, "empty", (int(x), int(y), int(w), int(h))
        confidence = float(sure[region].mean())
        entry = Vessel(0, box, min(fill, 130.0), hue, colour, confidence)
        if matrix is not None:
            entry.table_xy_m = _to_table(matrix, (x + w / 2.0, float(y + h)))
            dx, dy = entry.table_xy_m[0] - calibration.arm_base[0], entry.table_xy_m[1] - calibration.arm_base[1]
            entry.reachable = calibration.min_radius_m <= math.hypot(dx, dy) <= calibration.reach_m
        vessels.append(entry)
    vessels.sort(key=lambda v: v.box[0])
    for number, entry in enumerate(vessels, start=1):
        entry.index = number
    if not vessels:
        notes.append("The trained model found no vessel in this picture.")
    return vessels, matrix, found, notes


def analyse(image: np.ndarray, vessel: VesselType = VesselType(), calibration: Calibration = Calibration()) -> Analysis:
    """The trained reader's analysis of a picture (same shape as the rule-based one)."""
    scale = 1.0
    if image.shape[1] > 1280:
        scale = 1280 / image.shape[1]
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    labels, sure = predict(image)
    vessels, matrix, found, notes = readings_from_masks(image, labels, sure, vessel, calibration)
    return Analysis(vessels, found, matrix is not None, notes, annotate(image, vessels, matrix is not None), scale, "model")


def status() -> dict:
    """What a page shows about the trained model: whether it exists, how far training has got (if it is running), and the scores it earned on pictures it never trained on, as plain rows."""
    out = {"available": available(), "stage": None, "fraction": 0.0, "text": "", "rows": [], "updated": None}
    progress = MODEL_FOLDER / "progress.json"
    if progress.exists():
        p = json.loads(progress.read_text(encoding="utf-8"))
        out["stage"], out["updated"] = p.get("stage"), p.get("updated")
        if p.get("stage") == "training":
            out["fraction"] = float(p.get("step", 0)) / float(max(1, p.get("steps", 1)))
            out["text"] = f"Training: round {p.get('epoch')} of {p.get('epochs')}, about {p.get('minutes_left')} minutes left (loss {p.get('loss', 0):.2f})"
        elif p.get("stage") in ("preparing the photographs", "drawing the bench scenes", "testing", "starting"):
            out["text"] = f"Training is getting ready: {p.get('stage')}"
        elif p.get("stage") == "done":
            out["fraction"] = 1.0
            out["text"] = f"Training finished ({p.get('minutes')} minutes)"
    rep = report()
    if rep:
        d, photos, drawn, level = rep["data"], rep.get("iou_on_unseen_photographs"), rep["iou_on_unseen_drawn_scenes"], rep["level_reading_on_drawn_scenes"]
        out["rows"] = [{"What": "Trained on", "Result": f"{d['real_train']:,} real photographs (LabPics, MIT licence) and {d['drawn_train']:,} drawn bench scenes"},
                       {"What": "Network", "Result": "MobileNetV3 segmentation network, started from weights learned on everyday photographs"}]
        if photos:
            out["rows"].append({"What": f"Overlap with hand-drawn outlines on {d['real_test']} unseen real photographs (1.0 is perfect)", "Result": f"vessel {photos['vessel']:.2f}, contents {photos['contents']:.2f}"})
        out["rows"] += [{"What": f"Overlap on {d['drawn_test']} unseen drawn scenes", "Result": f"vessel {drawn['vessel']:.2f}, contents {drawn['contents']:.2f}"},
                        {"What": f"Level reading on {level['scenes']} unseen drawn scenes", "Result": f"average error {level['mean_error_points']:.1f} points; {level['within_10_points_pct']:.0f}% within 10 points"},
                        {"What": "Trained", "Result": f"{rep['trained']}, {rep['minutes']} minutes on this computer's processor"}]
    return out


def report() -> dict | None:
    """What the training recorded about this model (data, scores), or None when there is none."""
    return json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else None
