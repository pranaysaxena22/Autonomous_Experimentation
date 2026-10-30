"""Trains the cell's tablet-inspection network (normal or defective) on the public PharmaVision photographs.

    .venv\\Scripts\\python.exe tools\\download_pharmavision.py     (once)
    .venv\\Scripts\\python.exe tools\\train_tablet.py

It starts from a MobileNetV3-Large that already learned to see everyday photographs, teaches it this one question on the CPU (a few minutes), keeps the pass that did best on the VALIDATION photographs, and only then scores it once on the TEST photographs
(which it never saw in any way) and writes data/vision_models/tablet.pt and tablet_report.json. Nothing here is part of the running app; the app reads the weights and the report.

What the scores do NOT show: the same tablet products appear in the training, validation and test photographs (the data has no product labels to hold products out), so the test scores are likely to be better than on a tablet the network has never seen.
"""
from __future__ import annotations

import json
import random
import sys
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.vision import tablet  # noqa: E402

ZIP = ROOT / "data" / "public" / "pharmavision" / "pharmavision.zip"
EPOCHS = 20
BATCH = 32
SEED = 7


def load(split: str) -> tuple[list[np.ndarray], list[int]]:
    """Every photograph of a split (train, validation, test), padded square and resized, with its label (1 = defective)."""
    images, labels = [], []
    with zipfile.ZipFile(ZIP) as z:
        for name in sorted(z.namelist()):
            parts = name.split("/")
            if len(parts) < 3 or parts[-3] != split or not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            image = cv2.imdecode(np.frombuffer(z.read(name), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue
            images.append(cv2.resize(tablet.square(image), (256, 256), interpolation=cv2.INTER_AREA))
            labels.append(1 if parts[-2] == "defective" else 0)
    return images, labels


def augment(image: np.ndarray, rng: random.Random) -> np.ndarray:
    """A random change that keeps a defect a defect: turn it (a tablet can lie any way), flip it, crop a little, change the light a little (colour only slightly: discolouration is itself a defect)."""
    h, w = image.shape[:2]
    angle = rng.uniform(0, 360)
    scale = rng.uniform(1.0, 1.25)
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    matrix[:, 2] += (rng.uniform(-8, 8), rng.uniform(-8, 8))
    out = cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if rng.random() < 0.5:
        out = out[:, ::-1]
    out = out.astype(np.float32) * rng.uniform(0.85, 1.15) + rng.uniform(-12, 12)
    return np.clip(out, 0, 255).astype(np.uint8)


def batch(images: list[np.ndarray], train: bool, rng: random.Random):
    import torch
    out = []
    for image in images:
        view = augment(image, rng) if train else image
        small = cv2.resize(view, (tablet.SIZE, tablet.SIZE), interpolation=cv2.INTER_AREA)
        out.append(((cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0 - tablet.MEAN) / tablet.STD).transpose(2, 0, 1))
    return torch.from_numpy(np.stack(out))


def probabilities(model, images: list[np.ndarray]) -> np.ndarray:
    import torch
    model.eval()
    found = []
    with torch.no_grad():
        for i in range(0, len(images), 64):
            found.append(torch.softmax(model(batch(images[i:i + 64], False, random.Random(0))), dim=1)[:, 1].numpy())
    return np.concatenate(found)


def scores(prob: np.ndarray, truth: list[int]) -> dict:
    y, p = np.array(truth), prob >= tablet.THRESHOLD
    tp, tn, fp, fn = int(((y == 1) & p).sum()), int(((y == 0) & ~p).sum()), int(((y == 0) & p).sum()), int(((y == 1) & ~p).sum())
    order = np.argsort(prob)
    ranks = np.empty(len(prob))
    ranks[order] = np.arange(1, len(prob) + 1)
    auc = (ranks[y == 1].sum() - (y == 1).sum() * ((y == 1).sum() + 1) / 2) / ((y == 1).sum() * (y == 0).sum())
    return {"photographs": len(truth), "accuracy": (tp + tn) / len(truth), "defective_found": tp / max(1, tp + fn), "normal_passed": tn / max(1, tn + fp),
            "false_alarms": fp, "missed_defects": fn, "true_defective": tp, "true_normal": tn, "auc": float(auc)}


def main() -> int:
    import torch
    if not ZIP.exists():
        print("The tablet photographs are not there yet: run tools\\download_pharmavision.py first.")
        return 1
    torch.manual_seed(SEED)
    rng = random.Random(SEED)
    train_x, train_y = load("train")
    val_x, val_y = load("validation")
    test_x, test_y = load("test")
    print(f"photographs: train {len(train_y)}, validation {len(val_y)}, test {len(test_y)}", flush=True)
    model = tablet.build_model(pretrained=True)
    optimiser = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=1e-4)
    steps = EPOCHS * -(-len(train_y) // BATCH)
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=4e-4, total_steps=steps, pct_start=0.2)
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.05)
    started = time.time()
    best = (-1.0, 1e9, None, 0)
    for epoch in range(1, EPOCHS + 1):
        model.train()
        order = list(range(len(train_y)))
        rng.shuffle(order)
        total = 0.0
        for i in range(0, len(order), BATCH):
            ids = order[i:i + BATCH]
            x = batch([train_x[k] for k in ids], True, rng)
            y = torch.tensor([train_y[k] for k in ids])
            loss = loss_fn(model(x), y)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            schedule.step()
            total += float(loss) * len(ids)
        prob = probabilities(model, val_x)
        accuracy = float(((prob >= tablet.THRESHOLD) == np.array(val_y)).mean())
        val_loss = float(-np.mean(np.where(np.array(val_y) == 1, np.log(np.clip(prob, 1e-6, 1)), np.log(np.clip(1 - prob, 1e-6, 1)))))
        print(f"pass {epoch:2d}: training loss {total / len(order):.3f}, validation accuracy {accuracy:.3f}, validation loss {val_loss:.3f}, {time.time() - started:.0f} s", flush=True)
        if (accuracy, -val_loss) > (best[0], -best[1]):
            best = (accuracy, val_loss, {k: v.clone() for k, v in model.state_dict().items()}, epoch)
    model.load_state_dict(best[2])
    test = scores(probabilities(model, test_x), test_y)
    val = scores(probabilities(model, val_x), val_y)
    tablet.MODEL_FOLDER.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), tablet.WEIGHTS)
    record = {"network": "MobileNetV3-Large classifier (normal, defective), started from weights learned on everyday photographs", "torch": torch.__version__,
              "data": "PharmaVision (640 smartphone photographs of tablets, 224 x 224; use confirmed by the project owner on 2026-10-23; its own licence text was not readable to me)",
              "train_photographs": len(train_y), "validation_photographs": len(val_y), "test_photographs": len(test_y), "passes": EPOCHS, "kept_pass": best[3],
              "minutes": round((time.time() - started) / 60, 1), "threshold": tablet.THRESHOLD, "validation": val, "test": test,
              "caution": "The same tablet products appear in the training, validation and test photographs, so these scores are likely better than on a tablet the network has never seen."}
    tablet.REPORT.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({"kept_pass": best[3], "test": test}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
