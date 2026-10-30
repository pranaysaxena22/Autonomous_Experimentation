"""The vision check the cell makes when the arm picks up an ingredient bottle: a photograph of the bottle in, which bottle it is and which solution it holds and how full it is out, and whether it is the bottle the plan asked for.

In the simulation there is no camera, so the photograph is a real one (or a drawn one) of a bottle of the right colour of liquid, and the bottle's stickers are put onto it. The reading is done by the vision part exactly as it would be on a photograph from a real camera,
and the verdict compares what it read with what the plan expected. Nothing here changes the run.

Colour alone cannot prove which ingredient a bottle holds (two ingredients can share a colour), so each bottle carries two stickers: a NAME sticker (the ingredient's name in capitals) and a BARCODE sticker (an EAN-13 carrying the bottle's ID). The cell scans the barcode
(a standard barcode reader) and reads the name (a trained text reader); either one identifies the bottle, and when both are read they must agree. The colour and the level of the liquid are a second look. `overall` combines the readings: the stickers decide which bottle it is,
and the colour confirms (or questions) it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2

from . import text
from .analyse import Analysis, analyse
from .config import INGREDIENT_SOLUTIONS, VesselType
from .labels import bottle_label, bottle_name, ingredient_for_label, read_label, stick_labels
from .synthetic import bottle_photo, make_scene

ENOUGH_LEVEL_PCT = 15.0         # below this the bottle is nearly empty and the check says to refill it
ZOOM_VESSEL_PX = 220            # a drawn scene is small; it is enlarged until the bottle is about this wide before the stickers go on, as a camera held up close would see it


@dataclass
class BottleCheck:
    ingredient: str
    expected_colour: str
    read_colour: str | None
    level_pct: float | None
    engine: str
    source: str                  # "real photograph" or "drawn photograph"
    verdict: str                 # the liquid only: "right bottle", "wrong bottle", "bottle not seen"
    detail: str
    jpeg: bytes
    label_expected: str = ""         # the barcode the plan expects on this bottle
    label_read: str | None = None    # the barcode read from the sticker (None: no sticker, or unreadable)
    overall: str = ""                # "right bottle", "wrong bottle", "check bottle" (stickers right but liquid not as expected, or the two stickers disagree) or "label not read"
    label_detail: str = ""
    label_name: str | None = None    # the ingredient whose bottle carries the barcode that was read (None: not one of this cell's bottles, or not read)
    name_expected: str = ""          # the name the plan expects printed on this bottle, in capitals
    name_read: str | None = None     # the name read from the sticker, in capitals (None: no sticker, unreadable, or not one of this cell's names)
    name_reader: bool = True         # False when the text models are not on this computer (the bottle is then identified by its barcode alone)


DEMO_CASES = ("", "wrong", "unreadable", "blank", "liquid")       # what a presenter can put in front of the camera: nothing unusual, another ingredient's stickers, a smudged barcode (the name still identifies it), no stickers at all, a liquid that is not this ingredient's


def demo_settings(ingredient_id: str, case: str) -> dict:
    """The arguments of `check` that make a demonstration case: the real bottle stays as planned, only what the camera is shown changes."""
    others = [i for i in INGREDIENT_SOLUTIONS if i != ingredient_id]
    if case == "wrong":
        return {"labelled_as": others[0]}
    if case == "unreadable":
        return {"label_state": "barcode_smudged"}
    if case == "blank":
        return {"label_state": "missing"}
    if case == "liquid":
        expected = INGREDIENT_SOLUTIONS.get(ingredient_id)
        return {"photographed": next(c for c in ("orange", "purple") if c != expected)}
    return {}


def level_for(trial: int) -> float:
    """The illustrative level of a bottle at a trial: nearly full at the start, a little lower with each trial (never below 10%)."""
    return max(10.0, 92.0 - 2.5 * (trial - 1))


def _zoom(image, box, annotated):
    """A drawn scene is wide and the bottle in it small: cut out the bottle's surroundings and enlarge them until the bottle is ZOOM_VESSEL_PX wide. Returns the enlarged clean picture, the enlarged annotated picture and the bottle's box in them."""
    x, y, w, h = box
    factor = ZOOM_VESSEL_PX / max(1, w)
    x0, x1 = max(0, int(x - 0.9 * w)), min(image.shape[1], int(x + 1.9 * w))
    y0, y1 = max(0, int(y - 0.1 * h)), min(image.shape[0], int(y + 1.12 * h))
    big = lambda img: cv2.resize(img[y0:y1, x0:x1], None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)       # noqa: E731
    return big(image), big(annotated), (int((x - x0) * factor), int((y - y0) * factor), int(w * factor), int(h * factor))


def _identify(label_read, name_read, label_expected, name_expected, name_reader):
    """('identified' | 'wrong' | 'conflict' | 'not read', what to say): what the two stickers together say about which bottle this is."""
    said = [v for v in (None if label_read is None else label_read == label_expected, None if name_read is None else name_read == name_expected) if v is not None]
    if not said:
        return "not read", ("Neither the barcode nor the name could be read, so the bottle is NOT confirmed: colour alone cannot tell two ingredients apart." if name_reader
                            else "The barcode could not be read (and the text reader is not installed on this computer), so the bottle is NOT confirmed: colour alone cannot tell two ingredients apart.")
    if all(said):
        if label_read is not None and name_read is not None:
            return "identified", f"Barcode {label_read} and the name {name_read} both match the plan."
        if label_read is not None:
            return "identified", f"Barcode {label_read} matches the plan" + (" (the name could not be read)." if name_reader else ".")
        return "identified", f"The barcode could not be read, but the name {name_read} matches the plan."
    if not any(said):
        owner = ingredient_for_label(label_read)
        who = f"the barcode {label_read} (the {owner.removesuffix('_pct')} bottle)" if label_read is not None else ""
        who += (" and " if label_read is not None and name_read is not None else "") + (f"the name {name_read}" if name_read is not None else "")
        return "wrong", f"The stickers say {who}, but the plan expected the {name_expected.lower()} bottle ({label_expected})."
    return "conflict", f"The barcode says {label_read} and the name says {name_read}: the two disagree, so check the bottle."


def check(ingredient_id: str, trial: int, label: str = "", engine: str = "auto", level_pct: float | None = None, photographed: str | None = None, real: bool = True, labelled_as: str | None = None, label_state: str = "ok") -> BottleCheck:
    """Photograph the bottle, read it, and compare with what the plan expected. With `real` (the default) and the demo photographs made (tools/pick_bottle_photos.py), the photograph is a REAL one of a real beaker or flask holding that colour of liquid, read by
    the trained model; otherwise it is drawn (and the level is the illustrative one for the trial). `photographed` puts a different solution in the bottle than the plan expects (a wrong bottle in the rack), to show what the check does then.
    `labelled_as` puts the stickers of a different ingredient on the bottle; `label_state` is "ok", "barcode_smudged" (the barcode cannot be read, the name can), "smudged" (neither can be read) or "missing" (no stickers)."""
    expected = INGREDIENT_SOLUTIONS.get(ingredient_id, "blue")
    shown = photographed or expected
    image = bottle_photo(shown) if real else None
    source = "real photograph"
    if image is not None and engine in ("auto", "model"):
        from . import learned
        if not learned.available():
            image = None
    if image is None:
        level = level_pct if level_pct is not None else level_for(trial)
        image, _ = make_scene([(-0.95, 0.0, level / 100.0, shown)], seed=1000 + trial, noise=3.0)
        source = "drawn photograph"
    found: Analysis = analyse(image, VesselType(), engine=engine)             # the liquid is read from the clean photograph
    h_img, w_img = image.shape[:2]
    box = found.vessels[0].box if found.vessels else (int(w_img * 0.35), int(h_img * 0.3), int(w_img * 0.3), int(h_img * 0.5))
    seen, shown_picture = image, found.annotated
    if source == "drawn photograph" and found.vessels:
        seen, shown_picture, box = _zoom(image, box, found.annotated)
    label_expected, name_expected = bottle_label(ingredient_id), bottle_name(ingredient_id)
    on_bottle = labelled_as or ingredient_id
    if label_state != "missing":                                              # what the camera sees, with the stickers on the bottle
        args = dict(code=bottle_label(on_bottle), name=bottle_name(on_bottle), barcode_smudged=label_state in ("smudged", "barcode_smudged"), name_smudged=label_state == "smudged")
        seen, shown_picture = stick_labels(seen, box, **args), stick_labels(shown_picture, box, **args)
    label_read = read_label(seen)
    name_reader = text.available()
    names = [i.removesuffix("_pct") for i in INGREDIENT_SOLUTIONS]
    matched = text.match_name(text.read_text(seen), names)[0] if name_reader else None
    name_read = matched.upper() if matched else None
    if found.vessels:
        vessel = found.vessels[0]
        read, read_level = vessel.colour, vessel.fill_pct
        verdict = "right bottle" if read == expected else "wrong bottle"
        detail = (f"Read as {read} at {read_level:.0f}% (expected {expected})." + (" Level is low: refill soon." if read_level < ENOUGH_LEVEL_PCT else ""))
        crop = shown_picture
    else:
        read = read_level = None
        verdict, detail = "bottle not seen", "The camera could not see the bottle's liquid."
        crop = cv2.resize(shown_picture, None, fx=0.4, fy=0.4)
    state, label_detail = _identify(label_read, name_read, label_expected, name_expected, name_reader)
    if state == "identified":
        overall = "right bottle" if verdict == "right bottle" else "check bottle"
        label_detail += "" if overall == "right bottle" else " But the liquid is not what that ingredient should look like: check it."
    else:
        overall = {"wrong": "wrong bottle", "conflict": "check bottle", "not read": "label not read"}[state]
    ok, data = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return BottleCheck(label or ingredient_id, expected, read, read_level, found.engine, source, verdict, detail, data.tobytes() if ok else b"", label_expected, label_read, overall, label_detail, ingredient_for_label(label_read),
                       name_expected, name_read, name_reader)
