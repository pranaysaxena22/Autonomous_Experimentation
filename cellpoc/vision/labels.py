"""The stickers on each ingredient bottle: a NAME sticker (the ingredient's name in capitals) and a BARCODE sticker (an EAN-13, the common 13-digit product barcode, carrying the bottle's ID), and the reading of the barcode from a photograph.

Colour cannot tell two ingredients apart (two different powders can sit in the same coloured bottle), so the cell identifies a bottle by what is printed on it: it scans the barcode (OpenCV's own barcode reader) and reads the name (cellpoc.vision.text); either one
identifies the bottle, and when both are read they must agree. The simulation has no camera, so the stickers are put onto the photograph here, on the bottle: paper stickers that follow the curve of the glass, with shaded edges and a soft shadow.
The IDs are demonstration ones, built in the number range that the barcode standard keeps for in-house use (200 to 299); a real site would use its own. OpenCV's reader handles the EAN and UPC families only: a site that labels its bottles in Code 128 or Data Matrix
would need another reader added (with approval).
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import INGREDIENT_SOLUTIONS

# the standard EAN-13 patterns (1 = bar, 0 = space) for a digit: left side set A (odd parity), left side set B (even parity), right side
_L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
_G = ("0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111")
_R = ("1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100")
_FIRST = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")      # which set each of the six left digits uses, by the first digit
QUIET = 11                     # empty modules each side of the bars, so a reader can find where the bars begin
MODULE_PX = 2                  # pixels per module (the narrowest bar) before the label is stuck on the photograph (OpenCV's reader finds bars of about this width best; it is also tried at other picture sizes)
BAR_PX = 70                    # the bars' height in pixels


def check_digit(first12: str) -> str:
    """The thirteenth digit: alternate weights 1 and 3 over the first twelve, then the amount that rounds the sum up to a multiple of ten."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def bottle_label(ingredient_id: str) -> str:
    """The 13-digit ID on the bottle that holds this ingredient: 200 (in-house range), the ingredient's number, a lot number, and the check digit."""
    names = list(INGREDIENT_SOLUTIONS)
    number = names.index(ingredient_id) + 1 if ingredient_id in names else 99
    first12 = f"200{number:02d}0000001"
    return first12 + check_digit(first12)


def bottle_name(ingredient_id: str) -> str:
    """The name printed on the bottle's name sticker: the ingredient's name in capitals, for example DRUG."""
    return ingredient_id.removesuffix("_pct").upper()


def ingredient_for_label(code: str | None) -> str | None:
    """The ingredient (for example drug_pct) whose bottle carries this ID, or None for an ID that is not one of this cell's bottles."""
    return next((i for i in INGREDIENT_SOLUTIONS if bottle_label(i) == code), None)


def modules(code: str) -> str:
    """The 95 modules of the barcode, as a string of 1 (bar) and 0 (space)."""
    if len(code) != 13 or not code.isdigit() or check_digit(code[:12]) != code[12]:
        raise ValueError(f"{code!r} is not a valid 13-digit barcode")
    sets = _FIRST[int(code[0])]
    left = "".join((_L if s == "L" else _G)[int(d)] for s, d in zip(sets, code[1:7]))
    right = "".join(_R[int(d)] for d in code[7:])
    return "101" + left + "01010" + right + "101"


def label_card(code: str, smudged: bool = False) -> np.ndarray:
    """The printed label: the barcode with its digits written underneath, on white. `smudged` spoils it the way a wet or scratched label would be."""
    bars = np.array([int(m) for m in modules(code)], np.uint8)
    row = np.full((bars.size + 2 * QUIET) * MODULE_PX, 255, np.uint8)
    row[QUIET * MODULE_PX:(QUIET + bars.size) * MODULE_PX] = np.repeat(np.where(bars == 1, 0, 255).astype(np.uint8), MODULE_PX)
    card = np.full((BAR_PX + 34, row.size), 255, np.uint8)
    card[:BAR_PX] = row[None, :]                              # the bars stop above the digits
    card = np.repeat(card[:, :, None], 3, axis=2)
    cv2.putText(card, f"{code[0]}  {code[1:7]}  {code[7:]}", (QUIET * MODULE_PX, BAR_PX + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    if smudged:
        left = card.shape[1] // 3
        cv2.rectangle(card, (left, 0), (left + card.shape[1] // 5, BAR_PX + 4), (150, 150, 150), -1)
        card = cv2.GaussianBlur(card, (0, 0), 2.5)
    return card


PAPER = (246, 247, 247)          # the stickers' paper colour (BGR)


def _paper(card: np.ndarray) -> np.ndarray:
    """A printed card on a sticker of paper: a little margin, a faint grain and a thin edge."""
    h, w = card.shape[:2]
    out = np.full((h + 14, w + 14, 3), PAPER, np.uint8)
    out[7:7 + h, 7:7 + w] = card
    out = np.where(out > 200, np.clip(out.astype(np.int16) + np.random.default_rng(3).integers(-3, 4, out.shape[:2])[:, :, None], 0, 255), out).astype(np.uint8)
    cv2.rectangle(out, (0, 0), (out.shape[1] - 1, out.shape[0] - 1), (190, 190, 190), 1)
    return out


def name_sticker(name: str, smudged: bool = False) -> np.ndarray:
    """The name sticker: the ingredient's name in bold capitals on paper. `smudged` spoils it the way a wet or scratched sticker would be."""
    card = np.full((64, 300, 3), 255, np.uint8)
    scale = 1.9
    while cv2.getTextSize(name, cv2.FONT_HERSHEY_DUPLEX, scale, 3)[0][0] > 276 and scale > 0.5:
        scale -= 0.05
    (tw, th), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_DUPLEX, scale, 3)
    cv2.putText(card, name, ((300 - tw) // 2, (64 + th) // 2), cv2.FONT_HERSHEY_DUPLEX, scale, (25, 25, 25), 3, cv2.LINE_AA)
    sticker = _paper(card)
    if smudged:
        cv2.rectangle(sticker, (0, 18), (sticker.shape[1], 52), (150, 150, 150), -1)
        sticker = cv2.GaussianBlur(sticker, (0, 0), 4)
    return sticker


def _wrap(sticker: np.ndarray, bend: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """The sticker as it looks stuck round a bottle: the middle faces us, the edges turn away (narrower and darker). Returns (the picture, how much of each pixel is sticker, 0 to 1)."""
    h, w = sticker.shape[:2]
    p = (np.arange(w) - (w - 1) / 2) / ((w - 1) / 2)                        # where each output column is across the sticker, -1 to 1
    q = np.arcsin(p * np.sin(bend)) / bend                                  # which column of the flat sticker is seen there
    map_x = np.tile(((q + 1) * (w - 1) / 2).astype(np.float32), (h, 1))
    map_y = np.tile(np.arange(h, dtype=np.float32)[:, None], (1, w))
    out = cv2.remap(sticker, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    out *= (1.0 - 0.2 * p ** 2)[None, :, None]
    return out, np.ones((h, w), np.float32)


def _put(image: np.ndarray, sticker: np.ndarray, centre_x: float, top: float, angle: float) -> None:
    """Stick one sticker (slightly turned, with a soft shadow) onto the picture, in place."""
    pic, alpha = _wrap(sticker)
    h, w = pic.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    pic = cv2.warpAffine(pic, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    alpha = cv2.warpAffine(alpha, matrix, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    left, top = int(round(centre_x - w / 2)), int(round(top))
    left, top = int(np.clip(left, 0, max(0, image.shape[1] - w))), int(np.clip(top, 0, max(0, image.shape[0] - h)))
    y1, x1 = min(image.shape[0], top + h), min(image.shape[1], left + w)
    hh, ww = y1 - top, x1 - left
    region = image[top:y1, left:x1].astype(np.float32)
    shadow = cv2.GaussianBlur(alpha[:hh, :ww], (0, 0), 3)
    shifted = np.zeros_like(shadow)
    shifted[3:, 2:] = shadow[:-3, :-2]
    region *= (1.0 - 0.4 * shifted)[:, :, None]
    a = alpha[:hh, :ww, None]
    image[top:y1, left:x1] = np.clip(region * (1 - a) + pic[:hh, :ww] * a, 0, 255).astype(np.uint8)


def stick_labels(image: np.ndarray, box: tuple[int, int, int, int], code: str | None, name: str | None, barcode_smudged: bool = False, name_smudged: bool = False) -> np.ndarray:
    """A copy of the photograph with the stickers on the vessel's body (box = x, y, width, height of the vessel): the name sticker above, the barcode sticker below. Pass None for a sticker that is not there."""
    out = image.copy()
    x, y, w, h = box
    width = int(min(max(w * 0.9, 190), out.shape[1] - 8))
    barcode = _paper(label_card(code, barcode_smudged)) if code else None
    heights = {}
    if barcode is not None:
        barcode = cv2.resize(barcode, (width, int(barcode.shape[0] * width / barcode.shape[1])), interpolation=cv2.INTER_AREA)
        heights["barcode"] = barcode.shape[0]
    label = None
    if name:
        label = name_sticker(name, name_smudged)
        label = cv2.resize(label, (int(width * 0.8), int(label.shape[0] * width * 0.8 / label.shape[1])), interpolation=cv2.INTER_AREA)
        heights["name"] = label.shape[0]
    total = sum(heights.values()) + (6 if len(heights) == 2 else 0)
    top = y + (h - total) / 2 + 0.06 * h
    centre = x + w / 2
    if label is not None:
        _put(out, label, centre, top, -1.2)
        top += label.shape[0] + 6
    if barcode is not None:
        _put(out, barcode, centre, top, 0.8)
    return out


def stick_label(image: np.ndarray, box: tuple[int, int, int, int], code: str, smudged: bool = False) -> np.ndarray:
    """A copy of the photograph with just the barcode sticker on the vessel."""
    return stick_labels(image, box, code, None, barcode_smudged=smudged)


def read_label(image: np.ndarray) -> str | None:
    """The 13-digit ID of a barcode in the photograph, or None if there is none or it cannot be read (the reader checks the check digit, so a damaged barcode is refused, not guessed)."""
    detector = cv2.barcode.BarcodeDetector()
    for scale in (1.0, 0.75, 0.5, 1.5, 2.0):
        view = image if scale == 1.0 else cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        try:
            found, texts, _kinds, _corners = detector.detectAndDecodeWithType(view)
        except cv2.error:
            continue
        for text in (texts or ()) if found else ():
            if len(text) == 13 and text.isdigit() and check_digit(text[:12]) == text[12]:
                return text
    return None
