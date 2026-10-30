"""Health check for the vision part (the Vision page): a picture of a bench in, the coloured liquids out: which solution (by colour), how full, where each stands for the arm, and whether the arm can reach it.

In plain words it checks that, on drawn scenes whose answer is known in advance: every vessel is found and each level is read within 6 percentage points of the truth (in three sample scenes and in harder light, with noise and blur); every colour is named correctly (eight colours); with the four printed markers in view each
vessel's position is found to within 15 mm and the arm's reach is judged right (a vessel moved out of reach is flagged, one in reach is not); a scene read with a deliberately wrong answer, a picture with nothing in it, a very dark one, an empty file and a file that is not a picture each get a plain answer, never a crash or an invented vessel; a planted wrong reading is caught by the same comparison, so the comparison can fail;
the Vision page draws (sample scene, a photo through the upload, a bad file) with the illustrative sentence once; real photographs dropped into data/vision_samples are read without error; and the vision part imports nothing from the project and touches no network. The drawn scenes are NOT proof that a real photo reads as well: a real camera, glass and light need their own try. Nothing is written into the project.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from cellpoc.vision import tablet as tablet_part  # noqa: E402
from cellpoc.vision import text as text_part  # noqa: E402
from cellpoc.vision.bottle_check import _identify  # noqa: E402
from cellpoc.vision.labels import bottle_label, check_digit, label_card, modules, read_label, stick_label  # noqa: E402
from cellpoc.vision import COLOUR_HUES, Calibration, VesselType, VisionError, analyse, analyse_bytes, bottle_check, make_scene, model_available, model_status, real_photos, scene_set  # noqa: E402
from cellpoc.vision import learned  # noqa: E402
from cellpoc.vision.config import INGREDIENT_SOLUTIONS  # noqa: E402
from checks import architecture  # noqa: E402
from checks.app_check import all_text, run_app, sentence_count, PLATFORM  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

LEVEL_TOLERANCE = 6.0           # percentage points
POSITION_TOLERANCE_M = 0.015
# floors for the trained model: a retraining that scores worse than these is a regression. Set on 2026-10-23 just under the first full training's recorded scores (photographs 0.70 and 0.71, drawn scenes 0.54, level error 3.7 points; see data/vision_models/report.json).
MODEL_FLOORS = {"vessel_photos": 0.65, "contents_photos": 0.65, "vessel_drawn": 0.50, "contents_drawn": 0.50, "level_error": 6.0, "bottles_right": 5, "sample_colours": 0.80}


def worst_level_error(analysis, truth) -> float:
    return max(abs(v.fill_pct - t["fill_pct"]) for v, t in zip(analysis.vessels, truth))


def main() -> int:
    cl = Checklist("VISION: a picture of a bench in, the coloured liquids out (solution, level, position for the arm, reach)")
    before = project_files()

    # ---------------------------------------------------------------- levels and colours on the sample scenes
    rows, names_ok = [], True
    for index, (name, vials) in enumerate(scene_set()):
        image, truth = make_scene(vials, seed=index)
        found = analyse(image)
        same_count = len(found.vessels) == len(truth)
        names_ok = names_ok and same_count and all(v.colour == t["colour"] for v, t in zip(found.vessels, truth))
        rows.append((name, len(found.vessels), len(truth), round(worst_level_error(found, truth), 1) if same_count else None))
    cl.record(all(r[1] == r[2] and r[3] is not None and r[3] <= LEVEL_TOLERANCE for r in rows),
              f"On the three sample scenes (four solutions in a row, six vials in two rows, a nearly empty set) every vessel is found and every level is read within {LEVEL_TOLERANCE:g} percentage points of the known level", "; ".join(f"{n}: {a}/{b} found, worst error {e} points" for n, a, b, e in rows))
    cl.record(names_ok, "...and every solution is named by the right colour")
    colours = list(COLOUR_HUES)
    image, truth = make_scene([(-1.14 + 0.1 * (i % 4), 0.07 if i < 4 else -0.07, 0.3 + 0.07 * i, c) for i, c in enumerate(colours)], seed=9)
    every = analyse(image)
    cl.record(len(every.vessels) == 8 and [v.colour for v in every.vessels] == [t["colour"] for t in truth] or sorted(v.colour for v in every.vessels) == sorted(colours),
              "All eight colours (red, orange, yellow, green, teal, blue, purple, pink) are told apart in one picture", f"read {[v.colour for v in every.vessels]}")
    hard = []
    for label, kwargs in (("dim light", {"brightness": 0.6}), ("bright light", {"brightness": 1.25}), ("noisy", {"noise": 12.0}), ("a little out of focus", {"blur": 5}), ("dim, noisy and soft", {"brightness": 0.7, "noise": 9.0, "blur": 3})):
        image, truth = make_scene(scene_set()[0][1], seed=3, **kwargs)
        found = analyse(image)
        hard.append((label, len(found.vessels) == len(truth) and worst_level_error(found, truth) <= LEVEL_TOLERANCE + 2 and all(v.colour == t["colour"] for v, t in zip(found.vessels, truth))))
    cl.record(all(ok for _, ok in hard), f"In harder conditions (dim, bright, noisy, out of focus, and all three together) the same four solutions are still found, named right, and read within {LEVEL_TOLERANCE + 2:g} points", ", ".join(f"{label}: {'ok' if ok else 'FAILED'}" for label, ok in hard))

    # ---------------------------------------------------------------- the shape setting
    image, truth = make_scene([(-1.1, 0.0, 0.5, "green")], seed=1, aspect=6.0)
    right, wrong = analyse(image, VesselType(6.0)), analyse(image, VesselType(4.5))
    cl.record(abs(right.vessels[0].fill_pct - 50) <= LEVEL_TOLERANCE and abs(wrong.vessels[0].fill_pct - 50) > 8,
              "The level is read against the vessel shape that was set: a tall tube (height 6 times width) read with the right setting is within tolerance and with the default shape is clearly off, which is why the page has a shape setting", f"right {right.vessels[0].fill_pct:.0f}%, default {wrong.vessels[0].fill_pct:.0f}% (truth 50%)")

    # ---------------------------------------------------------------- positions for the arm
    errors, calibrated = [], True
    for index, (name, vials) in enumerate(scene_set()):
        image, truth = make_scene(vials, seed=index)
        found = analyse(image)
        calibrated = calibrated and found.calibrated and found.markers_found == 4
        for v, t in zip(found.vessels, truth):
            errors.append(float(np.hypot((v.table_xy_m or (9, 9))[0] - t["x_m"], (v.table_xy_m or (9, 9))[1] - t["y_m"])))
    cl.record(calibrated and max(errors) <= POSITION_TOLERANCE_M,
              f"With the four printed markers in view every vessel's position on the bench, in the arm's own frame, is found to within {POSITION_TOLERANCE_M * 1000:.0f} mm (a tilted camera, 13 vessels in all)", f"worst {max(errors) * 1000:.1f} mm; mean {sum(errors) / len(errors) * 1000:.1f} mm")
    image, truth = make_scene(scene_set()[0][1], seed=0)
    near = analyse(image, calibration=Calibration(reach_m=1.5))
    far = analyse(image, calibration=Calibration(reach_m=1.0))
    beyond = sum(1 for t in truth if float(np.hypot(t["x_m"], t["y_m"])) > 1.0)
    cl.record(all(v.reachable for v in near.vessels) and near.summary()["reachable"] == 4 and far.summary()["unreachable"] == beyond and 0 < beyond < 4 and all((v.reachable is False) == (float(np.hypot(*v.table_xy_m)) > 1.0) for v in far.vessels),
              "The arm's reach is judged: with a reach of 1.5 m every vessel is reachable; with 1.0 m exactly the vessels that stand more than 1.0 m from the arm's base (known from the scene) are flagged out of reach and the others are not", f"{near.summary()['reachable']} reachable at 1.5 m; {far.summary()['unreachable']} out of reach at 1.0 m (known: {beyond})")
    nomark, _ = make_scene(scene_set()[0][1], seed=0, markers=False), None
    found = analyse(nomark[0])
    cl.record(len(found.vessels) == 4 and not found.calibrated and all(v.table_xy_m is None and v.reachable is None for v in found.vessels) and any("markers" in n for n in found.notes),
              "Without the markers the levels and colours are still read, but no position is invented: the picture says positions need the four markers", "; ".join(found.notes))

    # ---------------------------------------------------------------- odd pictures get plain answers
    blank = np.full((480, 640, 3), 200, np.uint8)
    dark = (make_scene(scene_set()[0][1], seed=2, brightness=0.04, noise=1.0)[0])
    empty = analyse(blank)
    darkest = analyse(dark)
    tiny = analyse(make_scene([(-1.1, 0.0, 0.02, "red")], seed=1)[0])
    cl.record(not empty.vessels and empty.notes and not darkest.vessels and not tiny.vessels,
              "A picture with nothing in it, a nearly black one, and a vessel with only 2% of liquid give no vessels (nothing is invented), with a note that says what to do", f"{empty.notes[:1]}")
    refusals = []
    for label, data in (("an empty file", b""), ("text that is not a picture", b"hello, this is not a picture"), ("a broken picture", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)):
        try:
            analyse_bytes(data)
            refusals.append(f"{label}: NOT REFUSED")
        except VisionError as error:
            refusals.append("ok" if len(str(error)) > 20 and "Traceback" not in str(error) else f"{label}: not plain")
    big = cv2.resize(make_scene(scene_set()[0][1], seed=0)[0], (3200, 1800))
    cl.record(refusals == ["ok", "ok", "ok"] and len(analyse(big).vessels) == 4, "A file that is not a picture (empty, text, broken) is refused in plain words, and a very large picture (3200 pixels wide) is shrunk and read the same", f"{refusals}; large picture: {len(analyse(big).vessels)} vessels")

    # ---------------------------------------------------------------- the comparison can fail
    image, truth = make_scene(scene_set()[0][1], seed=0)
    honest = analyse(image)
    shifted = analyse(image)
    for v in shifted.vessels:
        v.fill_pct += 15
    cl.record(worst_level_error(honest, truth) <= LEVEL_TOLERANCE and worst_level_error(shifted, truth) > LEVEL_TOLERANCE,
              "Self-test: the same comparison catches a reading that is 15 points too high (and does not flag the honest one), so the level check can fail", f"honest {worst_level_error(honest, truth):.1f}; planted {worst_level_error(shifted, truth):.1f}")

    # ---------------------------------------------------------------- the cell's check of an ingredient bottle (rule-based reader, so the answer is the same on every computer)
    verdicts = []
    for ingredient, expected in INGREDIENT_SOLUTIONS.items():
        for trial in (1, 12, 30):
            found = bottle_check(ingredient, trial, ingredient, engine="rules", real=False)
            decoded = cv2.imdecode(np.frombuffer(found.jpeg, np.uint8), cv2.IMREAD_COLOR)
            verdicts.append(found.verdict == "right bottle" and found.read_colour == expected and abs(found.level_pct - max(10.0, 92.0 - 2.5 * (trial - 1))) <= LEVEL_TOLERANCE and decoded is not None and decoded.shape[1] > 100)
    wrong = bottle_check("drug_pct", 3, "drug", engine="rules", photographed="red", real=False)
    low = bottle_check("filler_pct", 30, "filler", engine="rules", level_pct=8.0)
    cl.record(all(verdicts) and wrong.verdict == "wrong bottle" and "red" in wrong.detail and "refill" in bottle_check("filler_pct", 30, "filler", engine="rules", level_pct=12.0, real=False).detail.lower(),
              "The cell's vision check of an ingredient bottle: for all five bottles (blue, yellow, green, orange, purple) at three points in a run the drawn photograph is read as the right solution at about the right level and comes back as a picture; a bottle holding a different solution than the plan expects is called 'wrong bottle' and says what it saw; a nearly empty bottle says to refill",
              f"{sum(verdicts)} of {len(verdicts)} right; wrong bottle -> '{wrong.verdict}': {wrong.detail}")

    # ---------------------------------------------------------------- the bottle's barcode (EAN-13): the identity (colour alone cannot tell two ingredients apart)
    labelled = [(i, t, bottle_check(i, t, i, engine="rules", real=False)) for i in INGREDIENT_SOLUTIONS for t in (1, 12, 30)]
    ids = {i: bottle_label(i) for i in INGREDIENT_SOLUTIONS}
    same_colour = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, labelled_as="filler_pct")      # the liquid is the drug's colour; the label belongs to the filler
    smudged = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, label_state="smudged")
    missing = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, label_state="missing")
    odd_liquid = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, photographed="red")
    cl.record(len(set(ids.values())) == 5 and all(b.label_read == ids[i] == b.label_expected and b.overall == "right bottle" for i, _, b in labelled),
              "Each of the five ingredient bottles carries its own barcode (EAN-13, five different IDs), and reading it back from the photograph gives that bottle's ID for every bottle at three points in a run: label and colour agree, so 'right bottle'", f"{[b.label_read for _, _, b in labelled[::3]]}")
    cl.record(same_colour.verdict == "right bottle" and same_colour.overall == "wrong bottle" and same_colour.label_read == ids["filler_pct"] and ids["filler_pct"] in same_colour.label_detail and ids["drug_pct"] in same_colour.label_detail,
              "A bottle whose liquid is exactly the colour the plan expects but whose label belongs to another ingredient is called 'wrong bottle' and says which label it read and which the plan expected (the case colour alone could never catch)", f"colour verdict {same_colour.verdict}; overall {same_colour.overall}; {same_colour.label_detail}")
    cl.record(smudged.overall == "label not read" and smudged.label_read is None and missing.overall == "label not read" and "NOT confirmed" in missing.label_detail and odd_liquid.overall == "check bottle" and odd_liquid.label_read == ids["drug_pct"],
              "An unreadable (smudged) or missing label is never accepted as 'right bottle': it says 'label not read' and that the bottle is not confirmed; a correct label on a liquid of the wrong colour says 'check bottle'", f"smudged {smudged.overall}; missing {missing.overall}; odd liquid {odd_liquid.overall}")
    blank = np.full((300, 520, 3), 255, np.uint8)
    binder = bottle_label("binder_pct")
    try:
        modules(binder[:12] + str((int(binder[12]) + 1) % 10))
        refuses_bad_digit = False
    except ValueError:
        refuses_bad_digit = True
    cl.record(check_digit("400638133393") == "1" and all(len(c) == 13 and check_digit(c[:12]) == c[12] and c.startswith("200") for c in ids.values()) and refuses_bad_digit,
              "The barcode maker follows the standard: the check digit it computes for a published example barcode (4006381333931) is the published one, every bottle's ID is 13 digits in the in-house range (200 to 299) with a correct check digit, and a barcode with a wrong check digit is refused", f"{list(ids.values())}")
    cl.record(read_label(blank) is None and read_label(label_card(ids["drug_pct"])) == ids["drug_pct"] and read_label(stick_label(blank, (200, 60, 60, 120), binder)) == binder and read_label(stick_label(blank, (200, 60, 60, 120), binder, smudged=True)) is None,
              "Self-test of the barcode reader: a blank picture has no barcode, a printed one is read, one stuck on a picture is read, and a smudged one is refused (not guessed), so the reading can fail", "")

    # ---------------------------------------------------------------- the name sticker, read by the text reader (skipped on a computer that does not have the text models)
    expected_names = {i: i.removesuffix("_pct").upper() for i in INGREDIENT_SOLUTIONS}
    table = [("identified", _identify("2000100000014", "DRUG", "2000100000014", "DRUG", True)[0]), ("identified", _identify(None, "DRUG", "2000100000014", "DRUG", True)[0]), ("identified", _identify("2000100000014", None, "2000100000014", "DRUG", True)[0]),
             ("wrong", _identify("2000200000013", "FILLER", "2000100000014", "DRUG", True)[0]), ("wrong", _identify(None, "FILLER", "2000100000014", "DRUG", True)[0]), ("conflict", _identify("2000200000013", "DRUG", "2000100000014", "DRUG", True)[0]),
             ("conflict", _identify("2000100000014", "FILLER", "2000100000014", "DRUG", True)[0]), ("not read", _identify(None, None, "2000100000014", "DRUG", True)[0]), ("not read", _identify(None, None, "2000100000014", "DRUG", False)[0])]
    cl.record(all(want == got for want, got in table),
              "The rule for combining the two stickers: either one identifies the bottle when the other cannot be read; when both are read they must agree (a barcode and a name that disagree say 'check the bottle'); another ingredient's sticker is a wrong bottle; neither readable is never accepted", f"{[(w, g) for w, g in table if w != g] or 'all nine cases as expected'}")
    if text_part.available():
        two = [(i, t, bottle_check(i, t, i, engine="rules", real=False)) for i in INGREDIENT_SOLUTIONS for t in (1, 12, 30)]
        rescued = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, label_state="barcode_smudged")
        blank_check = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, label_state="missing")
        both_bad = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, label_state="smudged")
        other = bottle_check("drug_pct", 3, "drug", engine="rules", real=False, labelled_as="binder_pct")
        cl.record(all(b.name_read == expected_names[i] == b.name_expected and b.label_read == ids[i] and b.overall == "right bottle" and b.name_reader for i, _, b in two),
                  "The name sticker is read by the text reader: for every ingredient bottle at three points in a run the name read is the bottle's own name (DRUG, FILLER, BINDER, DISINTEGRANT, LUBRICANT) and agrees with the barcode, so 'right bottle'", f"{[b.name_read for _, _, b in two[::3]]}")
        cl.record(rescued.label_read is None and rescued.name_read == "DRUG" and rescued.overall == "right bottle" and "name DRUG matches" in rescued.label_detail
                  and both_bad.name_read is None and both_bad.label_read is None and both_bad.overall == "label not read" and blank_check.overall == "label not read" and other.overall == "wrong bottle" and other.name_read == "BINDER" and "BINDER" in other.label_detail,
                  "With the barcode smudged the name still identifies the bottle (right bottle, and it says it was the name); with both smudged or no stickers at all the bottle is NOT accepted ('label not read'); another ingredient's two stickers are a wrong bottle that names the name it read",
                  f"barcode smudged: {rescued.overall} ({rescued.label_detail}); both smudged: {both_bad.overall}; none: {blank_check.overall}; other's: {other.overall}")
        words = [("dnug", 0.9)], [("cenialy", 0.9), ("producerculations", 0.9)], [("fil1er", 0.9)], [("binder", 0.9)]
        names = list(expected_names.values())
        got = [text_part.match_name(w, [n.lower() for n in names])[0] for w in words]
        cl.record(text_part.read_text(np.full((300, 520, 3), 255, np.uint8)) == [] and got == ["drug", None, "filler", "binder"],
                  "Self-test of the name reader: a blank picture has no writing, a reading a letter or two wrong is still taken for the right name, and writing that is not one of this cell's names (a caption in the photograph) is not taken for one, so the reading can fail", f"{got}")
    else:
        cl.skip("The name sticker read by the text reader", "the text-reading models are not on this computer: run tools\\download_ocr_models.py")

    # ---------------------------------------------------------------- the tablet inspection (skipped on a computer that does not have its weights or the demonstration photographs)
    TABLET_FLOORS = {"accuracy": 0.75, "defective_found": 0.55, "normal_passed": 0.90, "auc": 0.85}          # regression floors, set well under what it scored, so a broken network fails and an ordinary retraining does not
    normals, defectives = tablet_part.demo_photos("normal"), tablet_part.demo_photos("defective")
    if tablet_part.available() and tablet_part.report() and normals and defectives:
        rec = tablet_part.report()["test"]
        cl.record(rec["photographs"] >= 100 and all(rec[k] >= v for k, v in TABLET_FLOORS.items()),
                  "The trained tablet network's record is there and, on test photographs it never saw, it is at or above the floors set for it (accuracy, share of defective tablets found, share of normal tablets passed, ranking score)",
                  f"{rec['photographs']} photographs: accuracy {rec['accuracy']:.3f}, defective found {rec['defective_found']:.2f}, normal passed {rec['normal_passed']:.2f}, ranking score {rec['auc']:.3f} (floors {TABLET_FLOORS})")
        read = {kind: [tablet_part.inspect(cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)) for p in photos] for kind, photos in (("normal", normals), ("defective", defectives))}
        plain_ok = all(np.array_equal(r.picture, cv2.resize(tablet_part.square(cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)), r.picture.shape[1::-1], interpolation=cv2.INTER_AREA)) for r, p in zip(read["normal"], normals))
        marked = [int(((r.picture[:, :, 2] > 200) & (r.picture[:, :, 1] < 80) & (r.picture[:, :, 0] < 80)).sum()) for r in read["defective"]]
        cl.record(all(r.label == "normal" for r in read["normal"]) and all(r.label == "defective" for r in read["defective"]) and plain_ok and all(m > 50 for m in marked),
                  "The demonstration photographs: every normal tablet is read as normal and comes back untouched, every defective one is read as defective and comes back with the part the network looked at outlined in red", f"{len(normals)} normal, {len(defectives)} defective; outline pixels {marked}")
        check_a, check_b = tablet_part.check(1), tablet_part.check(1, "defective")
        cl.record(check_a.verdict == "tablet ok" and "hardness gauge" in check_a.action and check_b.verdict == "defective tablet" and "discard bin" in check_b.action and check_a.jpeg[:2] == b"\xff\xd8" and tablet_part.check(1).photo == check_a.photo and tablet_part.check(2).photo != check_a.photo,
                  "The cell's tablet check: a normal tablet is 'tablet ok' and goes on to the hardness gauge, a defective one is 'defective tablet' and would be sent to the discard bin, the answer is a picture, the same trial always gets the same photograph and the next trial a different one", f"{check_a.verdict}: {check_a.action} / {check_b.verdict}: {check_b.action}")
    else:
        cl.skip("The tablet inspection (the trained network's record and scores, the demonstration photographs, the cell's tablet check)", "the trained tablet network or its demonstration photographs are not on this computer: run tools\\download_pharmavision.py, tools\\train_tablet.py, tools\\score_tablet.py and tools\\pick_tablet_photos.py")

    # ---------------------------------------------------------------- the trained model (skipped on a computer that does not have its weights)
    if model_available():
        report = learned.report()
        status = model_status()
        photos, drawn, levels = report["iou_on_unseen_photographs"], report["iou_on_unseen_drawn_scenes"], report["level_reading_on_drawn_scenes"]
        cl.record(report["data"]["real_test"] >= 400 and report["data"]["real_train"] >= 1500 and photos and status["rows"] and status["available"],
                  "The trained model exists and says how it was made: trained on real photographs (LabPics, MIT licence) and drawn scenes, scored on photographs it never trained on, and the page can show that", f"{report['data']}; {len(status['rows'])} rows")
        cl.record(photos["vessel"] >= MODEL_FLOORS["vessel_photos"] and photos["contents"] >= MODEL_FLOORS["contents_photos"] and drawn["vessel"] >= MODEL_FLOORS["vessel_drawn"] and drawn["contents"] >= MODEL_FLOORS["contents_drawn"],
                  "The model's overlap with the hand-drawn outlines on pictures it never trained on is above the floor set for it (regression floors, so a worse retraining is noticed): vessel and contents, on real photographs and on drawn scenes",
                  f"photographs: vessel {photos['vessel']:.2f}, contents {photos['contents']:.2f}; drawn: vessel {drawn['vessel']:.2f}, contents {drawn['contents']:.2f}; floors {MODEL_FLOORS}")
        cl.record(levels["mean_error_points"] <= MODEL_FLOORS["level_error"], "The model's level reading on unseen drawn scenes is within the floor set for it (average error, in percentage points)", f"average error {levels['mean_error_points']:.1f} points (floor {MODEL_FLOORS['level_error']}); {levels['within_10_points_pct']:.0f}% within 10 points")
        by_model = [bottle_check(i, 5, i, engine="model") for i in INGREDIENT_SOLUTIONS]
        sample_hits = 0
        for index, (name, vials) in enumerate(scene_set()):
            image, truth = make_scene(vials, seed=index)
            found = analyse(image, engine="model")
            sample_hits += sum(1 for v, t in zip(found.vessels, truth) if v.colour == t["colour"]) if len(found.vessels) == len(truth) else 0
        total = sum(len(v) for _, v in scene_set())
        cl.record(sum(b.verdict == "right bottle" for b in by_model) >= MODEL_FLOORS["bottles_right"] and sample_hits / total >= MODEL_FLOORS["sample_colours"],
                  "Read by the trained model, the five ingredient bottles come back right and the sample scenes' solutions are named correctly at or above the floor set for it", f"bottles right: {sum(b.verdict == 'right bottle' for b in by_model)} of 5 (floor {MODEL_FLOORS['bottles_right']}); sample solutions right: {sample_hits} of {total}; engine {by_model[0].engine}")
        real_checks = [bottle_check(i, 5, i, engine="model") for i in INGREDIENT_SOLUTIONS]
        wrong_real = bottle_check("drug_pct", 5, "drug", engine="model", photographed="orange")
        if all(b.source == "real photograph" for b in real_checks):
            cl.record(all(b.verdict == "right bottle" and b.level_pct is not None and 20 <= b.level_pct <= 100 for b in real_checks) and wrong_real.verdict == "wrong bottle" and wrong_real.source == "real photograph" and "orange" in wrong_real.detail,
                      "With the five real demo photographs (a real beaker, jar or flask of each colour, from photographs the model never trained on) the trained model reads the right solution for every ingredient bottle and says 'right bottle'; put the orange photograph where the drug bottle should be and it says 'wrong bottle' and what it saw",
                      f"{[(b.expected_colour, b.read_colour, round(b.level_pct)) for b in real_checks]}; wrong: {wrong_real.verdict} ({wrong_real.detail})")
        else:
            cl.skip("The five real demo photographs read by the trained model", "the demo photographs are not on this computer: run tools\\pick_bottle_photos.py after tools\\download_labpics.py")
        photos_read = [(name, len(analyse(image, engine="model").vessels)) for name, image in real_photos()]
        cl.record(all(isinstance(n, int) for _, n in photos_read), "A real image file in data/vision_samples is read by the trained model without error", ", ".join(f"{name}: {n}" for name, n in photos_read))
    else:
        cl.skip("The trained model (its scores, its readings, the bottle check through it)", "its weights are not on this computer: run tools\\train_vision.py (about an hour); the colour-rule reader is used meanwhile")

    # ---------------------------------------------------------------- real photographs, if any were dropped in
    photos = real_photos()
    if photos:
        results = [(name, len(analyse(image).vessels)) for name, image in photos]
        cl.record(True, f"Real photographs in data/vision_samples ({len(photos)}) are read without error", ", ".join(f"{n}: {c} vessel(s)" for n, c in results))
    else:
        cl.skip("Real photographs in data/vision_samples", "none dropped in yet: put JPG or PNG photos of coloured liquids there to see them in the page's sample list")

    # ---------------------------------------------------------------- the page
    page = run_app(PLATFORM, "Vision")
    text = " ".join(all_text(page.main))
    cl.record(not page.exception and sentence_count(all_text(page.main)) == 1 and len(page.dataframe) >= 1 and "Vessels found" in " ".join(m.label for m in page.metric),
              "The Vision page draws with no error on a sample scene: the picture, the counts (vessels found, markers seen, reach) and the table, with the illustrative sentence once", f"metrics {[(m.label, m.value) for m in page.metric]}; exceptions {[str(e.value)[:80] for e in page.exception]}")
    page.radio[0].set_value("Photo").run()
    cl.record(not page.exception and len(page.get("file_uploader")) == 1, "...and offers the upload for a photo (and the camera, in the same way) without error", f"exceptions {[str(e.value)[:80] for e in page.exception]}")

    # ---------------------------------------------------------------- the part keeps to the rules
    part = ROOT / "cellpoc" / "vision"
    imports = [line for p in part.glob("*.py") for line in p.read_text(encoding="utf-8").splitlines() if line.startswith(("import ", "from ")) and ("cellpoc" in line or line.startswith("from .."))]
    users = sorted({p.relative_to(ROOT).as_posix() for p in (ROOT / "cellpoc").rglob("*.py") if "vision" not in p.parts and re.search(r"cellpoc\.vision|from \.\.vision|import vision\b", p.read_text(encoding="utf-8", errors="replace"))})
    cl.record(architecture.ALLOWED["vision"] == set() and not imports and users == ["cellpoc/live/server.py", "cellpoc/shell/vision_page.py"], "The vision part imports nothing from the project, and only the Vision page and the live server (for the cell's bottle check) use it", f"{len(list(part.glob('*.py')))} files; used by {users}")
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    os.environ.pop("CELLPOC_RECORD", None)
    sys.exit(main())
