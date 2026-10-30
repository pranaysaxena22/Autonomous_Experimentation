"""Scores the trained tablet network on the VALIDATION and TEST photographs again, through the app's own reading path (cellpoc.vision.tablet: the same padding and resizing the cell's tablet check uses), and writes the result into
data/vision_models/tablet_report.json in place of the scores tools/train_tablet.py printed (which used the training script's own, slightly different, resizing). The threshold stays where it was fixed before any result existed (0.5);
the table of what other thresholds would have done on the test photographs is information for a decision, not a tuning.

    .venv\\Scripts\\python.exe tools\\score_tablet.py
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.vision import tablet  # noqa: E402

ZIP = ROOT / "data" / "public" / "pharmavision" / "pharmavision.zip"


def read(split: str) -> tuple[np.ndarray, np.ndarray]:
    probs, truth = [], []
    with zipfile.ZipFile(ZIP) as z:
        for name in sorted(z.namelist()):
            parts = name.split("/")
            if len(parts) < 3 or parts[-3] != split or not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            image = cv2.imdecode(np.frombuffer(z.read(name), np.uint8), cv2.IMREAD_COLOR)
            probs.append(tablet.probability(image))
            truth.append(parts[-2] == "defective")
    return np.array(probs), np.array(truth)


def scores(prob: np.ndarray, truth: np.ndarray, threshold: float) -> dict:
    p = prob >= threshold
    tp, tn, fp, fn = int((p & truth).sum()), int((~p & ~truth).sum()), int((p & ~truth).sum()), int((~p & truth).sum())
    ranks = np.empty(len(prob))
    ranks[np.argsort(prob)] = np.arange(1, len(prob) + 1)
    auc = (ranks[truth].sum() - truth.sum() * (truth.sum() + 1) / 2) / (truth.sum() * (~truth).sum())
    return {"photographs": int(len(truth)), "accuracy": (tp + tn) / len(truth), "defective_found": tp / max(1, tp + fn), "normal_passed": tn / max(1, tn + fp),
            "false_alarms": fp, "missed_defects": fn, "true_defective": tp, "true_normal": tn, "auc": float(auc)}


def main() -> int:
    if not ZIP.exists() or not tablet.available() or tablet.report() is None:
        print("Run tools\\download_pharmavision.py and tools\\train_tablet.py first.")
        return 1
    record = tablet.report()
    val_p, val_t = read("validation")
    test_p, test_t = read("test")
    record["validation"], record["test"] = scores(val_p, val_t, tablet.THRESHOLD), scores(test_p, test_t, tablet.THRESHOLD)
    record["scored_with"] = "the app's own reading path (cellpoc.vision.tablet), by tools/score_tablet.py"
    record["other_thresholds_on_test"] = {str(t): {"defective_found": scores(test_p, test_t, t)["defective_found"], "false_alarms": scores(test_p, test_t, t)["false_alarms"]} for t in (0.5, 0.4, 0.3, 0.2, 0.1)}
    record["other_thresholds_note"] = "Information for a decision, not a tuning: the threshold used is 0.5, fixed before any result existed. Lowering it finds more defective tablets and raises false alarms."
    tablet.REPORT.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({"test": record["test"], "other_thresholds_on_test": record["other_thresholds_on_test"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
