"""Reading the printed NAME on an ingredient bottle's sticker, from a photograph.

Two small models, run by OpenCV itself (no library added): a text finder (PP-OCRv3) that boxes every piece of writing in the picture, and a text reader (CRNN) that reads each box. They are downloaded by tools/download_ocr_models.py into
data/vision_models/ocr (not saved in git). When they are absent the program says so and the cell identifies the bottle by its barcode alone. What was read is then compared with the list of names this cell's bottles carry (drug, filler, binder,
disintegrant, lubricant): a reading that is close to one of them (a letter or two wrong) is taken for it, and a reading that is close to none is not.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import cv2
import numpy as np

FOLDER = Path(__file__).resolve().parents[2] / "data" / "vision_models" / "ocr"
FINDER = FOLDER / "text_detection_en_ppocrv3_2023may.onnx"
READER = FOLDER / "text_recognition_CRNN_EN_2021sep.onnx"
CHARSET = "0123456789abcdefghijklmnopqrstuvwxyz"            # the reader's alphabet (it does not tell capitals from small letters)
MATCH = 0.75                                                # how close (0 to 1) a reading must be to a known name to be taken for it
_cache: dict = {}


def available() -> bool:
    return FINDER.exists() and READER.exists()


def _finder():
    if "finder" not in _cache:
        model = cv2.dnn_TextDetectionModel_DB(str(FINDER))
        model.setBinaryThreshold(0.3)
        model.setPolygonThreshold(0.5)
        model.setUnclipRatio(2.0)
        model.setMaxCandidates(200)
        model.setInputParams(1.0 / 255.0, (736, 736), (122.67891434, 116.66876762, 104.00698793))
        _cache["finder"] = model
    return _cache["finder"]


def _reader():
    if "reader" not in _cache:
        _cache["reader"] = cv2.dnn.readNet(str(READER))
    return _cache["reader"]


def _read_crop(crop_bgr: np.ndarray) -> str:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    blob = cv2.dnn.blobFromImage(gray, scalefactor=1.0 / 127.5, size=(100, 32), mean=127.5)
    net = _reader()
    net.setInput(blob)
    out = net.forward()                                     # (steps, 1, 37): the blank first, then the 36 characters
    best = out[:, 0, :].argmax(axis=1)
    text, previous = "", 0
    for c in best:
        if c != 0 and c != previous:
            text += CHARSET[c - 1]
        previous = c
    return text


def read_text(image_bgr: np.ndarray) -> list[tuple[str, float]]:
    """Every piece of writing found in the picture, as (what it says, how sure the finder is it is writing), top to bottom."""
    if not available():
        return []
    boxes, confidences = _finder().detect(image_bgr)
    found = []
    target = np.array([[0, 31], [0, 0], [99, 0], [99, 31]], np.float32)
    for quad, confidence in zip(boxes, confidences):
        quad = np.array(quad, np.float32)
        crop = cv2.warpPerspective(image_bgr, cv2.getPerspectiveTransform(quad, target), (100, 32))
        text = _read_crop(crop)
        if text:
            found.append((text, float(confidence), float(quad[:, 1].mean())))
    return [(t, c) for t, c, _ in sorted(found, key=lambda f: f[2])]


def match_name(words: list[tuple[str, float]], names: list[str]) -> tuple[str | None, str]:
    """(the known name the writing says, what was read) : the known name that a reading is closest to (at least MATCH close), or None; the second part is the text read, joined, for showing."""
    shown = " ".join(t for t, _ in words)
    best, best_score = None, 0.0
    for text, _ in words:
        text = re.sub(r"[^a-z0-9]", "", text.lower())
        for name in names:
            score = difflib.SequenceMatcher(None, text, name.lower()).ratio()
            if score > best_score:
                best, best_score = name, score
    return (best if best_score >= MATCH else None), shown
